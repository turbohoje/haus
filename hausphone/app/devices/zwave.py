"""Z-Wave JS backend for the PWA.

Speaks the zwave-js-server WebSocket JSON protocol directly over aiohttp
(ws://127.0.0.1:3001) — the same raw approach as zwavejs/zwq.py / zjs.py, so there
is no zwave-js-server-python version/schema matching to worry about. Exposes the
interface main.py expects (connect / register_broadcast / refresh_state /
set_power / attic timers).

Push-based: the driver emits `value updated` events over the same socket, so
_state stays live and refresh_state() just recomputes from the cached node values
(no network round-trip).

Command classes per device:
  - switches (attic fans, fireplaces, reading lights, water pump):
        Binary Switch (0x25) — read currentValue, write targetValue
  - garage door opener (Nortek NGD00Z):
        Barrier Operator (0x66) — read currentState (255=open), write targetState

The garage also runs an auto-close watcher: once the door reports anything but
fully closed it counts down 15 minutes, then makes up to two close attempts a
minute apart before giving up (see "garage auto-close" below).
"""
import asyncio
import itertools
import json
import logging
import os
import time

log = logging.getLogger(__name__)

# host 3001 → container 3000 (see zwavejs compose). hausphone is network_mode:host.
ZWAVE_WS_URL = os.environ.get("ZWAVE_WS_URL", "ws://127.0.0.1:3001")

BINARY_SWITCH_CC = 37    # 0x25
BARRIER_CC = 102         # 0x66 — garage door opener
CENTRAL_SCENE_CC = 91    # 0x5B — remote button presses (WallMote, node 13)
DOOR_LOCK_CC = 98        # 0x62 — Allegion deadbolts (S0-secured)

# key -> device. node_id/endpoint from the zwave-js migration
# (see zwavejs/MIGRATION_CHECKLIST.md). `kind` defaults to "switch"; "barrier" is
# the garage door opener (different command class). Multi-channel ZW140s expose
# their relays on endpoints 1/2 (the root endpoint 0 has no switch).
DEVICES = {
    "light_west": {"node_id": 17, "endpoint": 1, "label": "Light West"},
    "light_east": {"node_id": 17, "endpoint": 2, "label": "Light East"},
    "attic1":     {"node_id": 16, "endpoint": 1, "label": "Attic1"},
    "attic2":     {"node_id": 16, "endpoint": 2, "label": "Attic2"},
    "ld_floor":   {"node_id": 24, "label": "LD Floor"},
    "garage":     {"node_id": 6, "kind": "barrier", "label": "Garage"},
    "l_fire":     {"node_id": 14, "label": "Living Fire", "auto_off_minutes": 90},
    # ZW140 dual-relay fireplace on endpoint 1 (root has no switch). If the fire
    # doesn't respond to a toggle, switch this to endpoint 2.
    "m_fire":     {"node_id": 10, "endpoint": 1, "label": "Master Fire", "auto_off_minutes": 90},
}

# Door locks (Allegion BE469, S0-secured). Kept separate from DEVICES because they
# aren't on/off switches: read Door Lock CC `currentMode` (255 Secured / 0 Unsecured /
# 254 Unknown), write `targetMode`. Dict order is the card's display order.
# back_door is node 25 (re-included after a failed interview, so it's out of sequence).
LOCKS = {
    "front_door":   {"node_id": 19, "label": "Front"},
    "back_door":    {"node_id": 25, "label": "Back"},
    "garage_lock":  {"node_id": 5,  "label": "Garage"},
    "balcony_lock": {"node_id": 7,  "label": "Balcony"},
}
DOOR_LOCK_SECURED = 255
DOOR_LOCK_UNSECURED = 0


# ── per-device value-id / on-state helpers ───────────────────────────────────
def _read_vid(dev):
    """(commandClass, endpoint, property, propertyKey) used to READ device state."""
    ep = dev.get("endpoint", 0)
    if dev.get("kind") == "barrier":
        return (BARRIER_CC, ep, "currentState", None)
    return (BINARY_SWITCH_CC, ep, "currentValue", None)


def _write_vid(dev) -> dict:
    """ValueID dict used to WRITE (set) the device."""
    ep = dev.get("endpoint", 0)
    if dev.get("kind") == "barrier":
        return {"commandClass": BARRIER_CC, "endpoint": ep, "property": "targetState"}
    return {"commandClass": BINARY_SWITCH_CC, "endpoint": ep, "property": "targetValue"}


def _raw_to_on(dev, raw):
    if raw is None:
        return None
    if dev.get("kind") == "barrier":
        # Barrier Operator: 0 = fully closed. Everything else counts as open —
        # 255 open, 254 opening, 252 closing, 253 stopped, 1-99 partly open.
        # A door stopped half-way is exactly what auto-close is for.
        return raw != 0
    return bool(raw)


def _on_to_write(dev, on):
    if dev.get("kind") == "barrier":
        return 255 if on else 0           # 255 = open, 0 = close
    return bool(on)


# reverse index (node_id, endpoint, cc, property) -> device key, for value events
_read_index = {}
for _k, _d in DEVICES.items():
    _cc, _ep, _prop, _pk = _read_vid(_d)
    _read_index[(_d["node_id"], _ep, _cc, _prop)] = _k

# node_id -> lock key, for routing Door Lock currentMode events
_lock_by_node = {_lk["node_id"]: _k for _k, _lk in LOCKS.items()}


# ── module state ─────────────────────────────────────────────────────────────
_state: dict = {k: None for k in DEVICES}
_lock_state: dict = {k: "unknown" for k in LOCKS}
_timer_end: dict = {k: None for k in DEVICES}
_timers: dict = {}          # device_key -> asyncio.Task
_last_refresh: float = 0.0
_broadcast_cb = None
_notify_cb = None

# ── raw WS client handles ────────────────────────────────────────────────────
_session = None             # aiohttp.ClientSession
_ws = None                  # aiohttp ClientWebSocketResponse
_listen_task = None
_values: dict = {}          # (node_id, endpoint, cc, property, propertyKey) -> value
_pending: dict = {}         # messageId -> asyncio.Future (command results)
_msg_id = itertools.count(1)
_connect_lock = asyncio.Lock()


def register_broadcast(cb):
    """main.py registers an async callback so push events broadcast state."""
    global _broadcast_cb
    _broadcast_cb = cb


def register_notify(cb):
    """main.py registers an async cb(title, body, tag) for user-facing alerts."""
    global _notify_cb
    _notify_cb = cb


# ── connection lifecycle ─────────────────────────────────────────────────────
async def connect():
    """Open the WS, hydrate state, subscribe. Call once at startup."""
    await _ensure_connected()


async def _ensure_connected():
    """Open (or reopen) the WS if not currently connected. Self-heals after drops."""
    global _session, _ws, _listen_task
    async with _connect_lock:
        if _ws is not None and not _ws.closed:
            return
        import aiohttp
        if _session is not None:
            try:
                await _session.close()
            except Exception:
                pass
        _session = aiohttp.ClientSession()
        _ws = await _session.ws_connect(ZWAVE_WS_URL, heartbeat=20,
                                        max_msg_size=16 * 1024 * 1024)
        state = await _handshake(_ws)
        _hydrate(state)
        _listen_task = asyncio.create_task(_listen_loop(_ws))
        log.info("Z-Wave connected: %s (%d nodes)", ZWAVE_WS_URL, len(state.get("nodes", [])))


async def _handshake(ws):
    import aiohttp
    ver = None
    while ver is None:
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            d = json.loads(msg.data)
            if d.get("type") == "version":
                ver = d
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise RuntimeError("socket closed during handshake")
    await ws.send_str(json.dumps({"messageId": str(next(_msg_id)),
                                  "command": "set_api_schema",
                                  "schemaVersion": ver["maxSchemaVersion"]}))
    sl = str(next(_msg_id))
    await ws.send_str(json.dumps({"messageId": sl, "command": "start_listening"}))
    while True:
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            d = json.loads(msg.data)
            if d.get("type") == "result" and d.get("messageId") == sl:
                if not d.get("success"):
                    raise RuntimeError("start_listening failed: %r" % d)
                return d["result"]["state"]
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise RuntimeError("socket closed waiting for state")


def _hydrate(state):
    """Populate the value cache + _state from the initial start_listening dump."""
    _values.clear()
    for node in state.get("nodes", []):
        nid = node["nodeId"]
        for v in node.get("values", []):
            _values[(nid, v.get("endpoint", 0) or 0, v.get("commandClass"),
                     v.get("property"), v.get("propertyKey"))] = v.get("value")
    _recompute_state()
    _recompute_locks()
    _sync_garage_auto()


def _recompute_state():
    for k, dev in DEVICES.items():
        cc, ep, prop, pk = _read_vid(dev)
        raw = _values.get((dev["node_id"], ep, cc, prop, pk))
        _state[k] = _raw_to_on(dev, raw)


# ── door locks ───────────────────────────────────────────────────────────────
def _lock_status(raw):
    """Door Lock CC currentMode → 'locked' | 'unlocked' | 'unknown'."""
    if raw is None or raw == 254:
        return "unknown"
    if raw == DOOR_LOCK_SECURED:
        return "locked"
    return "unlocked"          # 0/1/16/17/32/33 — any unsecured variant


def _recompute_locks():
    for k, lk in LOCKS.items():
        raw = _values.get((lk["node_id"], 0, DOOR_LOCK_CC, "currentMode", None))
        _lock_state[k] = _lock_status(raw)


def get_locks_state() -> dict:
    return {k: {"label": LOCKS[k]["label"], "status": _lock_state[k]} for k in LOCKS}


async def set_lock(lock_key: str, locked: bool) -> dict:
    lk = LOCKS.get(lock_key)
    if lk is None:
        raise ValueError(f"Unknown lock: {lock_key}")
    await _send_command({
        "command": "node.set_value",
        "nodeId": lk["node_id"],
        "valueId": {"commandClass": DOOR_LOCK_CC, "endpoint": 0, "property": "targetMode"},
        "value": DOOR_LOCK_SECURED if locked else DOOR_LOCK_UNSECURED,
    })
    # optimistic; the real state is confirmed by the currentMode notification
    _lock_state[lock_key] = "locked" if locked else "unlocked"
    return get_locks_state()


async def _listen_loop(ws):
    """Receive loop: route command results to their futures, apply value events."""
    global _ws
    import aiohttp
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                _dispatch(json.loads(msg.data))
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break
    except Exception as e:
        log.warning("Z-Wave listen loop ended: %s", e)
    finally:
        for fut in list(_pending.values()):
            if not fut.done():
                fut.set_exception(RuntimeError("Z-Wave connection closed"))
        _pending.clear()
        _ws = None
        log.warning("Z-Wave WS disconnected (will reconnect on next call)")


def _dispatch(d):
    t = d.get("type")
    if t == "result":
        fut = _pending.pop(d.get("messageId"), None)
        if fut is not None and not fut.done():
            fut.set_result(d)
    elif t == "event":
        _handle_event(d.get("event") or {})


def _handle_event(ev):
    if ev.get("event") not in ("value updated", "value notification"):
        return
    nid = ev.get("nodeId")
    a = ev.get("args") or {}
    ep = a.get("endpoint", 0) or 0
    cc = a.get("commandClass")
    prop = a.get("property")
    pk = a.get("propertyKey")
    new = a.get("newValue", a.get("value"))
    _values[(nid, ep, cc, prop, pk)] = new

    # Remote button presses (WallMote) arrive as Central Scene notifications,
    # not device state — hand them to the scene engine and stop.
    if cc == CENTRAL_SCENE_CC and prop == "scene":
        _handle_scene_notification(nid, pk, new)
        return

    # Door lock state change → update that lock and push to clients.
    if cc == DOOR_LOCK_CC and prop == "currentMode":
        lkey = _lock_by_node.get(nid)
        if lkey is not None:
            _lock_state[lkey] = _lock_status(new)
            if _broadcast_cb is not None:
                asyncio.create_task(_broadcast_cb({"locks": get_locks_state()}))
        return

    key = _read_index.get((nid, ep, cc, prop))
    if key is None:
        return
    on = _raw_to_on(DEVICES[key], new)
    if _state.get(key) == on:
        return
    _state[key] = on
    if on is False and _timer_end.get(key) is not None:
        _cancel_timer(key)
        _timer_end[key] = None
    if key == GARAGE_KEY:
        _sync_garage_auto()
    if _broadcast_cb is not None:
        asyncio.create_task(_broadcast_cb({"zwave": get_state(),
                                           "garage_auto": get_garage_auto()}))


async def _send_command(payload: dict):
    await _ensure_connected()
    mid = str(next(_msg_id))
    fut = asyncio.get_event_loop().create_future()
    _pending[mid] = fut
    try:
        await _ws.send_str(json.dumps({"messageId": mid, **payload}))
        d = await asyncio.wait_for(fut, timeout=10)
    finally:
        _pending.pop(mid, None)
    if not d.get("success"):
        raise RuntimeError("Z-Wave command failed: %r" % (d.get("errorCode") or d))
    return d.get("result")


# ── state ────────────────────────────────────────────────────────────────────
def _build_state() -> dict:
    now = time.time()
    result = {}
    for key in DEVICES:
        end = _timer_end.get(key)
        remaining = max(0, int(end - now)) if end is not None else None
        result[key] = {"on": _state[key], "timer_remaining": remaining}
    return result


def get_state() -> dict:
    return _build_state()


async def refresh_state() -> dict:
    """Recompute _state from the driver's cached values (kept live by events)."""
    global _last_refresh
    try:
        await _ensure_connected()
    except Exception as e:
        log.warning("Z-Wave refresh connect error: %s", e)
        return _build_state()
    _recompute_state()
    _recompute_locks()
    for key in DEVICES:
        if _state.get(key) is False and _timer_end.get(key) is not None:
            _cancel_timer(key)
            _timer_end[key] = None
    _sync_garage_auto()
    _last_refresh = time.monotonic()
    return _build_state()


async def refresh_if_stale(max_age: float = 3.0) -> dict:
    if time.monotonic() - _last_refresh > max_age:
        return await refresh_state()
    return get_state()


async def set_power(device_key: str, on: bool) -> dict:
    dev = DEVICES.get(device_key)
    if dev is None:
        raise ValueError(f"Unknown zwave device: {device_key}")

    await _send_command({
        "command": "node.set_value",
        "nodeId": dev["node_id"],
        "valueId": _write_vid(dev),
        "value": _on_to_write(dev, on),
    })
    # Barriers report their real currentState as the door travels (opening →
    # open, closing → closed), so let the value events set it. Writing it
    # optimistically would show CLOSED for the ~15 s of travel, and would fool
    # the auto-close verify check into thinking the door had already shut.
    if dev.get("kind") != "barrier":
        _state[device_key] = bool(on)

    auto_off = dev.get("auto_off_minutes")
    if on and auto_off:
        _timer_end[device_key] = time.time() + auto_off * 60
        _schedule_auto_off(device_key, auto_off * 60)
    elif not on:
        _cancel_timer(device_key)
        _timer_end[device_key] = None

    return get_state()


# ── auto-off timers (transport-agnostic) ─────────────────────────────────────
def _cancel_timer(device_key: str):
    task = _timers.pop(device_key, None)
    if task and not task.done():
        task.cancel()


def _schedule_auto_off(device_key: str, delay_seconds: float):
    _cancel_timer(device_key)

    async def _auto_off():
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        log.info("Z-Wave auto-off timer fired for %s", device_key)
        try:
            await set_power(device_key, False)
        except Exception as e:
            log.warning("Z-Wave auto-off failed for %s: %s", device_key, e)

    _timers[device_key] = asyncio.create_task(_auto_off())


# ── garage auto-close ────────────────────────────────────────────────────────
# The garage is the one device where "left on" is a security problem, so it gets
# a watcher instead of a plain auto-off timer: the moment the barrier reports
# anything but fully closed we count down, then try to close it, then verify.
#
#   open detected ──15 min──> attempt 1 ──60 s──> attempt 2 ──60 s──> give up
#
# Every attempt is verified against the door's own currentState rather than
# assumed, because a door that reverses on an obstruction still ACKs the
# command. Detecting the door closed at any point resets everything, including
# the disable flag — so "disable" only ever suppresses the current opening.
GARAGE_KEY = "garage"
GARAGE_COUNTDOWN_SECONDS = 15 * 60   # open -> first close attempt
GARAGE_VERIFY_SECONDS = 60           # attempt -> check it actually closed
GARAGE_MAX_ATTEMPTS = 2

# phase: "idle" (closed, or disabled) | "counting" | "closing" | "failed"
_garage_auto = {"enabled": True, "phase": "idle", "deadline": None, "attempts": 0}
_garage_auto_task = None
_garage_was_open = None              # last observed open/closed, for edge detection


def get_garage_auto() -> dict:
    a = _garage_auto
    remaining = None
    if a["deadline"] is not None:
        remaining = max(0, int(a["deadline"] - time.time()))
    return {
        "enabled": a["enabled"],
        "phase": a["phase"],
        "attempts": a["attempts"],
        "max_attempts": GARAGE_MAX_ATTEMPTS,
        "remaining": remaining,
        "countdown_seconds": GARAGE_COUNTDOWN_SECONDS,
    }


def _cancel_garage_task():
    global _garage_auto_task
    task, _garage_auto_task = _garage_auto_task, None
    if task and not task.done():
        task.cancel()


def _start_garage_countdown():
    """Arm a fresh 15-minute countdown. No-op while auto-close is disabled."""
    global _garage_auto_task
    if not _garage_auto["enabled"]:
        _garage_auto.update({"phase": "idle", "deadline": None, "attempts": 0})
        return
    _cancel_garage_task()
    _garage_auto.update({
        "phase": "counting",
        "deadline": time.time() + GARAGE_COUNTDOWN_SECONDS,
        "attempts": 0,
    })
    _garage_auto_task = asyncio.create_task(_garage_auto_runner())
    log.info("Garage open — auto-close in %d min", GARAGE_COUNTDOWN_SECONDS // 60)


def _reset_garage_auto():
    """Door is closed: stand everything down, including the disable flag."""
    _cancel_garage_task()
    _garage_auto.update({"enabled": True, "phase": "idle", "deadline": None, "attempts": 0})


def _sync_garage_auto():
    """Drive the watcher off the garage's open/closed state. Edge-triggered, so
    it is safe to call from every event and every poll."""
    global _garage_was_open
    is_open = _state.get(GARAGE_KEY)
    if is_open is None or is_open == _garage_was_open:
        return
    _garage_was_open = is_open
    if is_open:
        _start_garage_countdown()
    else:
        _reset_garage_auto()


async def _broadcast_garage_auto():
    if _broadcast_cb is None:
        return
    try:
        await _broadcast_cb({"zwave": get_state(), "garage_auto": get_garage_auto()})
    except Exception as e:
        log.warning("Garage auto-close broadcast error: %s", e)


async def _garage_auto_runner():
    """Countdown, then up to GARAGE_MAX_ATTEMPTS verified close attempts.

    Cancelled by _reset_garage_auto() as soon as the door reports closed, so the
    happy path never reaches the end of this coroutine.
    """
    try:
        await asyncio.sleep(GARAGE_COUNTDOWN_SECONDS)
        while _garage_auto["attempts"] < GARAGE_MAX_ATTEMPTS:
            attempt = _garage_auto["attempts"] + 1
            _garage_auto.update({
                "phase": "closing",
                "attempts": attempt,
                "deadline": time.time() + GARAGE_VERIFY_SECONDS,
            })
            log.info("Garage auto-close attempt %d/%d", attempt, GARAGE_MAX_ATTEMPTS)
            await _broadcast_garage_auto()
            try:
                await set_power(GARAGE_KEY, False)
            except Exception as e:
                log.warning("Garage auto-close attempt %d could not be sent: %s", attempt, e)
            await asyncio.sleep(GARAGE_VERIFY_SECONDS)
            if _state.get(GARAGE_KEY) is False:
                return                       # closed; the value event resets us
        _garage_auto.update({"phase": "failed", "deadline": None})
        log.warning("Garage auto-close gave up after %d attempts — door still open",
                    GARAGE_MAX_ATTEMPTS)
        await _broadcast_garage_auto()
        if _notify_cb is not None:
            try:
                await _notify_cb(
                    "Garage still open",
                    f"Auto-close failed after {GARAGE_MAX_ATTEMPTS} attempts.",
                    "garage-auto-close",
                )
            except Exception as e:
                log.warning("Garage auto-close notification failed: %s", e)
    except asyncio.CancelledError:
        raise


async def set_garage_auto_close(enabled: bool) -> dict:
    """Enable/disable auto-close for the current opening. Disabling drops the
    countdown; re-enabling while the door is still open starts a fresh one."""
    _garage_auto["enabled"] = bool(enabled)
    if enabled and _state.get(GARAGE_KEY):
        _start_garage_countdown()
    else:
        _cancel_garage_task()
        _garage_auto.update({"phase": "idle", "deadline": None, "attempts": 0})
        log.info("Garage auto-close %s", "enabled" if enabled else "disabled")
    return get_garage_auto()


# ── attic shared timers (transport-agnostic) ─────────────────────────────────
ATTIC_FANS = ("attic1", "attic2")
_attic_delay_on = {"armed": False, "fans": [], "duration_seconds": 0, "expires_at": None}
_attic_off_timer = {"armed": False, "duration_seconds": 0, "expires_at": None}
_attic_delay_on_task = None
_attic_off_timer_task = None


def _attic_delay_on_payload() -> dict:
    s = _attic_delay_on
    remaining = None
    if s["armed"] and s["expires_at"] is not None:
        remaining = max(0, int(s["expires_at"] - time.time()))
    return {
        "armed": s["armed"],
        "fans": list(s["fans"]),
        "duration_seconds": s["duration_seconds"],
        "remaining": remaining,
    }


def _attic_off_timer_payload() -> dict:
    s = _attic_off_timer
    remaining = None
    if s["armed"] and s["expires_at"] is not None:
        remaining = max(0, int(s["expires_at"] - time.time()))
    return {
        "armed": s["armed"],
        "duration_seconds": s["duration_seconds"],
        "remaining": remaining,
    }


def get_attic_timers() -> dict:
    return {
        "delay_on": _attic_delay_on_payload(),
        "off_timer": _attic_off_timer_payload(),
    }


async def _broadcast_attic_state():
    if _broadcast_cb is None:
        return
    try:
        await _broadcast_cb({"zwave": get_state(), "attic_timers": get_attic_timers()})
    except Exception as e:
        log.warning("Attic broadcast error: %s", e)


async def set_attic_delay_on(armed: bool, fans, duration_seconds: int) -> dict:
    global _attic_delay_on_task
    valid_fans = [f for f in (fans or []) if f in ATTIC_FANS]
    duration_seconds = int(duration_seconds or 0)
    if armed and (not valid_fans or duration_seconds <= 0):
        armed = False

    if _attic_delay_on_task and not _attic_delay_on_task.done():
        _attic_delay_on_task.cancel()
    _attic_delay_on_task = None

    if armed:
        _attic_delay_on.update({
            "armed": True,
            "fans": valid_fans,
            "duration_seconds": duration_seconds,
            "expires_at": time.time() + duration_seconds,
        })
        _attic_delay_on_task = asyncio.create_task(_attic_delay_on_runner(duration_seconds))
    else:
        _attic_delay_on.update({
            "armed": False, "fans": [], "duration_seconds": 0, "expires_at": None,
        })

    return get_attic_timers()


async def _attic_delay_on_runner(delay_seconds: float):
    try:
        await asyncio.sleep(delay_seconds)
    except asyncio.CancelledError:
        return
    fans = list(_attic_delay_on["fans"])
    log.info("Attic delay-on timer fired for %s", fans)
    try:
        for key in fans:
            if not _state.get(key):
                await set_power(key, True)
    except Exception as e:
        log.warning("Attic delay-on action failed: %s", e)
    _attic_delay_on.update({
        "armed": False, "fans": [], "duration_seconds": 0, "expires_at": None,
    })
    await _broadcast_attic_state()


async def set_attic_off_timer(armed: bool, duration_seconds: int) -> dict:
    global _attic_off_timer_task
    duration_seconds = int(duration_seconds or 0)
    if armed and duration_seconds <= 0:
        armed = False

    if _attic_off_timer_task and not _attic_off_timer_task.done():
        _attic_off_timer_task.cancel()
    _attic_off_timer_task = None

    if armed:
        _attic_off_timer.update({
            "armed": True,
            "duration_seconds": duration_seconds,
            "expires_at": time.time() + duration_seconds,
        })
        _attic_off_timer_task = asyncio.create_task(_attic_off_timer_runner(duration_seconds))
    else:
        _attic_off_timer.update({
            "armed": False, "duration_seconds": 0, "expires_at": None,
        })

    return get_attic_timers()


async def _attic_off_timer_runner(delay_seconds: float):
    try:
        await asyncio.sleep(delay_seconds)
    except asyncio.CancelledError:
        return
    log.info("Attic off-timer fired")
    try:
        for key in ATTIC_FANS:
            if _state.get(key):
                await set_power(key, False)
    except Exception as e:
        log.warning("Attic off-timer action failed: %s", e)
    _attic_off_timer.update({
        "armed": False, "duration_seconds": 0, "expires_at": None,
    })
    await _broadcast_attic_state()


# ── scene engine: remote button presses → scenes ─────────────────────────────
# The master remote (node 13, Aeotec WallMote Quad / ZW130) reports each button
# as a Central Scene notification: property 'scene', propertyKey '001'..'004'
# (the four pads), value = key attribute (0 KeyPressed / 1 KeyReleased /
# 2 KeyHeldDown). We map (node, button, press-kind) → a named scene; a scene is
# an ordered list of actions applied to DEVICES. This is driven entirely by the
# existing listen loop — no route or frontend wiring needed.
#
# Press kinds:  "short" = a tap (KeyPressed),  "long" = a hold (KeyHeldDown).
#
# ── EDIT BELOW TO CONFIGURE ──────────────────────────────────────────────────
# A scene is a list of actions. Today an action turns a DEVICES key on/off:
#     {"device": "l_fire", "on": True}
# The action dict is intentionally open-ended so timers can be added later
# without restructuring, e.g. {"device": "attic1", "on": True, "off_after_seconds": 10800}.
# (off_after_seconds is NOT implemented yet — it would hook _schedule_auto_off.)
SCENES = {
    "attic_fans_off": [
        {"device": "attic1", "on": False},
        {"device": "attic2", "on": False},
    ],
    "attic_fan2_on":  [{"device": "attic2", "on": True}],
    "light_east_off": [{"device": "light_east", "on": False}],
    "light_east_on":  [{"device": "light_east", "on": True}],
    "m_fire_off":     [{"device": "m_fire", "on": False}],
    "m_fire_on":      [{"device": "m_fire", "on": True}],
    "light_west_off": [{"device": "light_west", "on": False}],
    "light_west_on":  [{"device": "light_west", "on": True}],
}

# (remote node_id, button propertyKey, press kind) → scene name.
# WallMote Quad pads: "001" top-left, "002" top-right, "003" bottom-left,
# "004" bottom-right (confirm physical layout with a live capture if unsure).
REMOTE_BINDINGS = {
    (13, "001", "short"): "attic_fans_off",   # pad 1 tap  → both attic fans off
    (13, "001", "long"):  "attic_fan2_on",    # pad 1 hold → attic fan 2 on
    (13, "002", "short"): "light_east_off",   # pad 2 tap  → light east off
    (13, "002", "long"):  "light_east_on",    # pad 2 hold → light east on
    (13, "003", "short"): "m_fire_off",       # pad 3 tap  → master fireplace off
    (13, "003", "long"):  "m_fire_on",        # pad 3 hold → master fireplace on
    (13, "004", "short"): "light_west_off",   # pad 4 tap  → light west off
    (13, "004", "long"):  "light_west_on",    # pad 4 hold → light west on
}
# ── END CONFIG ───────────────────────────────────────────────────────────────

_KEY_PRESSED = 0
_KEY_RELEASED = 1
_KEY_HELD = 2
_HOLD_REPEAT_WINDOW = 2.0        # s; ignore repeated KeyHeldDown within one hold
_hold_last: dict = {}            # (node_id, button) -> last KeyHeldDown time


def _handle_scene_notification(node_id, button_key, attribute):
    """Central Scene notification → fire the bound scene (deduping held repeats)."""
    if button_key is None:
        return
    button = str(button_key)
    now = time.time()
    if attribute == _KEY_RELEASED:
        _hold_last.pop((node_id, button), None)
        return
    if attribute == _KEY_HELD:
        last = _hold_last.get((node_id, button))
        _hold_last[(node_id, button)] = now
        if last is not None and now - last < _HOLD_REPEAT_WINDOW:
            return                       # same hold still repeating; ignore
        kind = "long"
    elif attribute == _KEY_PRESSED:
        _hold_last.pop((node_id, button), None)
        kind = "short"
    else:
        return

    scene = REMOTE_BINDINGS.get((node_id, button, kind))
    if scene is None:
        log.info("Remote %s button %s %s press — no scene bound", node_id, button, kind)
        return
    log.info("Remote %s button %s %s press → scene %r", node_id, button, kind, scene)
    asyncio.create_task(run_scene(scene))


async def run_scene(name: str):
    """Apply every action in a named scene, then broadcast fresh state."""
    actions = SCENES.get(name)
    if not actions:
        log.warning("Scene %r is not defined", name)
        return
    log.info("Running scene %r (%d actions)", name, len(actions))
    for action in actions:
        try:
            await _apply_scene_action(action)
        except Exception as e:
            log.warning("Scene %r action %r failed: %s", name, action, e)
    if _broadcast_cb is not None:
        try:
            await _broadcast_cb({"zwave": get_state()})
        except Exception as e:
            log.warning("Scene %r broadcast failed: %s", name, e)


async def _apply_scene_action(action: dict):
    device = action.get("device")
    if device in DEVICES and "on" in action:
        await set_power(device, bool(action["on"]))
        return
    raise ValueError(f"unrecognized scene action: {action!r}")
