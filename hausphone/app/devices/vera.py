"""Vera Z-Wave hub — HTTP REST wrapper, with optional auto-off timer."""
import asyncio
import logging
import time
import httpx

log = logging.getLogger(__name__)

VERA_BASE = "http://10.22.14.4:3480/data_request"
SVC = "urn:upnp-org:serviceId:SwitchPower1"

DEVICES = {
    "light_west": {"id": 39, "label": "Light West"},
    "light_east": {"id": 40, "label": "Light East"},
    "attic1": {"id": 68, "label": "Attic1"},
    "attic2": {"id": 69, "label": "Attic2"},
    "ld_floor": {"id": 192, "label": "LD Floor"},
    "garage": {"id": 36, "label": "Garage"},
    "l_fire": {"id": 142, "label": "Living Fire", "auto_off_minutes": 90},
    "m_fire": {"id": 85, "label": "Master Fire", "auto_off_minutes": 90},
}

_state: dict = {k: None for k in DEVICES}
_timer_end: dict = {k: None for k in DEVICES}
_timers: dict = {}  # device_key -> asyncio.Task
_last_refresh: float = 0.0

# ── Vera system actions ──────────────────────────────────────────────────
async def soft_reset_zwave() -> dict:
    """Reboot the Z-Wave chip (does NOT factory-reset / lose pairings)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(VERA_BASE, params={
            "id": "lu_action",
            "serviceId": "urn:micasaverde-com:serviceId:ZWaveNetwork1",
            "action": "SoftReset",
            "DeviceNum": 1,
        })
    log.info("Vera Z-Wave soft reset: HTTP %s", r.status_code)
    return {"ok": r.status_code == 200, "status": r.status_code}


async def reload_engine() -> dict:
    """Reload the LuaUPnP engine."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(VERA_BASE, params={"id": "reload"})
    log.info("Vera engine reload: HTTP %s", r.status_code)
    return {"ok": r.status_code == 200, "status": r.status_code}


async def reboot_vera() -> dict:
    """Reboot the entire Vera unit (network + WiFi will drop)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(VERA_BASE, params={"id": "reboot"})
    log.info("Vera reboot: HTTP %s", r.status_code)
    return {"ok": r.status_code == 200, "status": r.status_code}


# ── Attic shared timers ──────────────────────────────────────────────────
ATTIC_FANS = ("attic1", "attic2")
_attic_delay_on = {"armed": False, "fans": [], "duration_seconds": 0, "expires_at": None}
_attic_off_timer = {"armed": False, "duration_seconds": 0, "expires_at": None}
_attic_delay_on_task = None
_attic_off_timer_task = None
_broadcast_cb = None


def register_broadcast(cb):
    """main.py registers an async callback so timer-fire events can push state."""
    global _broadcast_cb
    _broadcast_cb = cb


def _build_state() -> dict:
    now = time.time()
    result = {}
    for key in DEVICES:
        end = _timer_end.get(key)
        remaining = max(0, int(end - now)) if end is not None else None
        result[key] = {"on": _state[key], "timer_remaining": remaining}
    return result


async def refresh_state() -> dict:
    global _last_refresh
    async with httpx.AsyncClient(timeout=5.0) as client:
        for key, dev in DEVICES.items():
            try:
                r = await client.get(VERA_BASE, params={
                    "id": "variableget",
                    "DeviceNum": dev["id"],
                    "serviceId": SVC,
                    "Variable": "Status",
                })
                val = r.text.strip()
                on = val == "1"
                _state[key] = on
                # If a timer device was switched off externally, drop the timer
                if not on and _timer_end.get(key) is not None:
                    _cancel_timer(key)
                    _timer_end[key] = None
            except Exception as e:
                log.warning("Vera state error for %s: %s", key, e)
    _last_refresh = time.monotonic()
    return _build_state()


async def refresh_if_stale(max_age: float = 3.0) -> dict:
    if time.monotonic() - _last_refresh > max_age:
        return await refresh_state()
    return get_state()


def get_state() -> dict:
    return _build_state()


async def set_power(device_key: str, on: bool) -> dict:
    dev = DEVICES.get(device_key)
    if dev is None:
        raise ValueError(f"Unknown vera device: {device_key}")
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.get(VERA_BASE, params={
            "id": "action",
            "DeviceNum": dev["id"],
            "serviceId": SVC,
            "action": "SetTarget",
            "newTargetValue": "1" if on else "0",
        })
    _state[device_key] = on

    auto_off = dev.get("auto_off_minutes")
    if on and auto_off:
        _timer_end[device_key] = time.time() + auto_off * 60
        _schedule_auto_off(device_key, auto_off * 60)
    elif not on:
        _cancel_timer(device_key)
        _timer_end[device_key] = None

    return get_state()


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
        log.info("Vera auto-off timer fired for %s", device_key)
        try:
            await set_power(device_key, False)
        except Exception as e:
            log.warning("Vera auto-off failed for %s: %s", device_key, e)

    task = asyncio.create_task(_auto_off())
    _timers[device_key] = task


# ── Attic shared timers ──────────────────────────────────────────────────
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
        await _broadcast_cb({"vera": get_state(), "attic_timers": get_attic_timers()})
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
