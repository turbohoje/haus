"""Ecobee thermostat (Main Floor) over the ecobee cloud API.

Replaces the `ecobee/humidifier.py` cron jobs. Three jobs:

* **Status** — poll every POLL_SECONDS for temperature, setpoints, and which
  equipment is running (fan / heat / cool / humidifier). ecobee only exposes
  this through its cloud, and asks clients not to poll faster than 3 minutes.
* **Temporary hold** — +/- on the card sets a 2 h `holdHours` hold.
* **Peak shutoff** — on weekdays inside the configurable peak window (default
  17:00–21:00) the HVAC mode, humidifier and fan min-on-time are all switched
  off and any hold is cancelled; when the window ends they are put back the
  way they were. The pre-peak settings are written to disk, so a restart
  mid-window still restores correctly.

Auth: ecobee's PIN flow. The card offers a "Link" button when the token is
missing or rejected; the refresh token rotates on every use, so it is saved
(atomically) after each refresh.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.push import DATA_DIR

log = logging.getLogger(__name__)

API_KEY = "SukJ7Wfaw3TnPuKrlX2xDf3NHIwDmAxU"
THERMOSTAT_ID = "319279437236"
API = "https://api.ecobee.com"
TOKEN_PATH = DATA_DIR / "ecobee_token.json"
AUTO_PATH = DATA_DIR / "ecobee_auto.json"
TZ = ZoneInfo(os.environ.get("HAUS_TZ", "America/Denver"))

POLL_SECONDS = 180
TICK_SECONDS = 30            # peak-window check
HOLD_HOURS = 2
PEAK_DAYS = range(0, 5)      # Mon–Fri

_SELECTION = {"selectionType": "thermostats", "selectionMatch": THERMOSTAT_ID}

_http: httpx.AsyncClient = None
_lock = asyncio.Lock()
_broadcast_cb = None

_token = {}                  # {"access_token", "refresh_token"}
_status = {
    "ok": False,             # last API round-trip succeeded
    "auth": "unlinked",      # ok | unlinked | expired
    "error": "",
    "last_update": None,     # epoch seconds of last good read
}
_therm = {}                  # parsed thermostat snapshot (see _parse)
_auto = {
    "peak_start": "17:00",
    "peak_end": "21:00",
    "skip_date": None,       # ISO date the shutoff is skipped for
    "saved": None,           # pre-peak {hvacMode, humidifierMode, fanMinOnTime}; set while shed
}
_off_applied = False          # off command confirmed for the current peak
_peak_lock = asyncio.Lock()
_auto_error = ""             # last peak shutoff/restore failure, cleared on success
_link = None                 # {"pin", "code", "expires"} while a PIN link is pending
_link_task = None


def register_broadcast(cb):
    global _broadcast_cb
    _broadcast_cb = cb


async def _broadcast():
    if _broadcast_cb:
        try:
            await _broadcast_cb({"ecobee": get_state()})
        except Exception as e:
            log.warning("Ecobee broadcast error: %s", e)


# ── persistence ───────────────────────────────────────────────────────────
def _write_json(path, data):
    """Write via rename: the cron script truncated token.json on a failed run,
    which is how it silently stopped working."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
    except Exception as e:
        log.warning("Could not save %s: %s", path, e)


def _load():
    global _token
    try:
        _token = json.loads(TOKEN_PATH.read_text())
        _status["auth"] = "ok" if _token.get("refresh_token") else "unlinked"
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Could not read %s: %s", TOKEN_PATH, e)
    try:
        saved = json.loads(AUTO_PATH.read_text())
        for k in _auto:
            if k in saved:
                _auto[k] = saved[k]
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Could not read %s: %s", AUTO_PATH, e)


# ── API plumbing ──────────────────────────────────────────────────────────
class AuthError(Exception):
    pass


async def _refresh_token():
    r = await _http.post(f"{API}/token", data={
        "grant_type": "refresh_token",
        "refresh_token": _token.get("refresh_token", ""),
        "client_id": API_KEY,
    })
    if r.status_code != 200:
        _status["auth"] = "expired"
        raise AuthError(f"token refresh rejected ({r.status_code}): {r.text[:120]}")
    body = r.json()
    _token.update(access_token=body["access_token"], refresh_token=body["refresh_token"])
    _write_json(TOKEN_PATH, _token)
    _status["auth"] = "ok"


async def _api(method: str, body: dict) -> dict:
    """One API call, refreshing the access token once if ecobee says it expired."""
    if not _token.get("refresh_token"):
        _status["auth"] = "unlinked"
        raise AuthError("not linked")
    if not _token.get("access_token"):
        await _refresh_token()
    for attempt in (0, 1):
        headers = {"Authorization": f"Bearer {_token['access_token']}"}
        if method == "GET":
            r = await _http.get(f"{API}/1/thermostat", headers=headers,
                                params={"format": "json", "body": json.dumps(body)})
        else:
            r = await _http.post(f"{API}/1/thermostat", headers=headers,
                                 params={"format": "json"}, json=body)
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
        code = (data.get("status") or {}).get("code", 0)
        if code == 14 and attempt == 0:         # access token expired
            await _refresh_token()
            continue
        if code in (14, 16):                    # 16 = app deauthorized
            _status["auth"] = "expired"
            raise AuthError(data["status"].get("message", "auth rejected"))
        if code != 0:
            raise RuntimeError(f"ecobee {code}: {data['status'].get('message')}")
        return data
    raise RuntimeError("unreachable")


def _fail(e: Exception):
    _status["ok"] = False
    if isinstance(e, AuthError):
        _status["error"] = ("Ecobee not linked" if _status["auth"] == "unlinked"
                            else "Ecobee login expired") + " — re-link in Settings"
    else:
        _status["error"] = f"Can't reach ecobee: {e or type(e).__name__}"
    log.warning("Ecobee: %s", e)


# ── read ──────────────────────────────────────────────────────────────────
def _f(tenths):
    return None if tenths is None else tenths / 10.0


def _parse(t: dict) -> dict:
    rt = t.get("runtime") or {}
    st = t.get("settings") or {}
    eq = set(filter(None, (t.get("equipmentStatus") or "").split(",")))
    hold = next((e for e in t.get("events") or []
                 if e.get("running") and e.get("type") == "hold"), None)
    return {
        "connected": bool(rt.get("connected")),
        "temp": _f(rt.get("actualTemperature")),
        "humidity": rt.get("actualHumidity"),
        "heat_sp": _f(rt.get("desiredHeat")),
        "cool_sp": _f(rt.get("desiredCool")),
        "hvac_mode": st.get("hvacMode"),
        "humidifier_mode": st.get("humidifierMode"),
        "fan_min_on_time": st.get("fanMinOnTime"),
        "min_delta": _f(st.get("heatCoolMinDelta")) or 5.0,
        "running": {
            "fan": "fan" in eq,
            "heat": any(x.startswith(("heatPump", "auxHeat")) for x in eq),
            "cool": any(x.startswith("compCool") for x in eq),
            "humidifier": "humidifier" in eq,
        },
        "hold_until": (hold.get("endTime") or "")[:5] if hold else None,
    }


async def refresh_state():
    async with _lock:
        try:
            data = await _api("GET", {"selection": {
                **_SELECTION,
                "includeRuntime": True, "includeSettings": True,
                "includeEquipmentStatus": True, "includeEvents": True,
            }})
            _therm.clear()
            _therm.update(_parse(data["thermostatList"][0]))
            _status.update(ok=True, error="", last_update=time.time())
            if not _therm["connected"]:
                _status["error"] = "Thermostat is offline from ecobee's cloud"
        except Exception as e:
            _fail(e)


# ── write ─────────────────────────────────────────────────────────────────
async def _post(body: dict):
    async with _lock:
        try:
            await _api("POST", {"selection": _SELECTION, **body})
        except Exception as e:
            _fail(e)
            raise


async def _settle_and_refresh():
    """ecobee takes a moment to reflect a write in runtime."""
    await asyncio.sleep(3)
    await refresh_state()
    await _broadcast()


def _f_to_c(f):
    return (f - 32) * 5 / 9


def _c_to_f(c):
    return c * 9 / 5 + 32


def _step_c(f, delta_c):
    """°F setpoint moved by `delta_c` °C, landing on a 0.5 °C mark so the card
    (which leads with °C) moves in clean steps. ecobee itself works in °F."""
    return _c_to_f(round((_f_to_c(f) + delta_c) * 2) / 2)


async def adjust_hold(delta_c: float) -> dict:
    """Shift the active setpoint(s) by `delta_c` °C as a 2 h hold."""
    if in_peak():
        raise ValueError("peak hours — thermostat is off")
    mode = _therm.get("hvac_mode")
    heat, cool, gap = _therm.get("heat_sp"), _therm.get("cool_sp"), _therm.get("min_delta", 5.0)
    if heat is None or cool is None or mode in (None, "off"):
        raise ValueError("thermostat is off or state unknown")
    if mode in ("heat", "auxHeatOnly"):
        heat = _step_c(heat, delta_c)
        cool = max(cool, heat + gap)
    elif mode == "cool":
        cool = _step_c(cool, delta_c)
        heat = min(heat, cool - gap)
    else:                                   # auto: move the band
        heat = _step_c(heat, delta_c)
        cool = _step_c(cool, delta_c)
    await _post({"functions": [{"type": "setHold", "params": {
        "holdType": "holdHours", "holdHours": HOLD_HOURS,
        "heatHoldTemp": int(round(heat * 10)), "coolHoldTemp": int(round(cool * 10)),
    }}]})
    _therm.update(heat_sp=round(heat, 1), cool_sp=round(cool, 1))   # optimistic until the re-read lands
    asyncio.create_task(_settle_and_refresh())
    return get_state()


# ── peak shutoff ──────────────────────────────────────────────────────────
def _hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def in_peak(now=None) -> bool:
    now = now or datetime.now(TZ)
    if now.weekday() not in PEAK_DAYS or _auto["skip_date"] == now.date().isoformat():
        return False
    return _hm(_auto["peak_start"]) <= (now.hour, now.minute) < _hm(_auto["peak_end"])


async def _shed():
    """Save the current settings (once), then everything off and cancel holds."""
    global _off_applied
    if _auto["saved"] is None:
        await refresh_state()
        if not _status["ok"]:
            raise RuntimeError(_status["error"])
        # Persist before switching off: if we die between the two, restore still knows.
        _auto["saved"] = {"hvacMode": _therm["hvac_mode"],
                          "humidifierMode": _therm["humidifier_mode"],
                          "fanMinOnTime": _therm["fan_min_on_time"]}
        _write_json(AUTO_PATH, _auto)
    # Separate calls: sent together, ecobee answered 200 but left hvacMode on heat.
    await _post({"functions": [{"type": "resumeProgram", "params": {"resumeAll": True}}]})
    off = {"hvacMode": "off", "humidifierMode": "off", "fanMinOnTime": 0}
    await _post({"thermostat": {"settings": off}})
    await _verify(off)
    _off_applied = True
    log.info("Peak shutoff: off (saved %s)", _auto["saved"])


async def _verify(want: dict):
    """A 200 from ecobee doesn't mean the setting stuck — read it back."""
    await asyncio.sleep(3)
    await refresh_state()
    if not _status["ok"]:
        raise RuntimeError(_status["error"])
    have = {"hvacMode": _therm["hvac_mode"], "humidifierMode": _therm["humidifier_mode"],
            "fanMinOnTime": _therm["fan_min_on_time"]}
    bad = {k: have[k] for k in want if have[k] != want[k]}
    if bad:
        raise RuntimeError(f"ecobee accepted but still reads {bad}")


async def _restore():
    saved = _auto["saved"]
    await _post({"thermostat": {"settings": saved}})
    await _verify(saved)
    _auto["saved"] = None
    _write_json(AUTO_PATH, _auto)
    log.info("Peak over: restored %s", saved)


async def _peak_tick():
    """`saved` (on disk) holds the pre-peak settings; `_off_applied` (memory)
    says the off command went through. Anything that fails is retried on the
    next tick. After a restart mid-peak the off command is re-sent once."""
    global _auto_error, _off_applied
    async with _peak_lock:
        peak = in_peak()
        try:
            if peak and not _off_applied:
                await _shed()
            elif not peak and _auto["saved"] is not None:
                _off_applied = False
                await _restore()
            else:
                if not peak:
                    _off_applied = False
                return
            _auto_error = ""
        except Exception as e:
            _auto_error = ("Peak shutoff" if peak else "Restore after peak") + f" failed, retrying: {e}"
            log.warning(_auto_error)
    await _settle_and_refresh()


async def _runner():
    last_poll = 0.0
    while True:
        try:
            await _peak_tick()
            if time.monotonic() - last_poll >= POLL_SECONDS:
                last_poll = time.monotonic()
                await refresh_state()
                await _broadcast()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Ecobee runner error: %s", e)
        await asyncio.sleep(TICK_SECONDS)


async def set_auto(peak_start=None, peak_end=None, skip_today=None) -> dict:
    for k, v in (("peak_start", peak_start), ("peak_end", peak_end)):
        if v is not None:
            _hm(v)                          # validates HH:MM
            _auto[k] = v
    if skip_today is not None:
        _auto["skip_date"] = datetime.now(TZ).date().isoformat() if skip_today else None
    _write_json(AUTO_PATH, _auto)
    asyncio.create_task(_peak_tick())       # apply immediately (e.g. skip mid-peak restores)
    return get_state()


# ── PIN linking ───────────────────────────────────────────────────────────
async def start_link() -> dict:
    global _link, _link_task
    r = await _http.get(f"{API}/authorize", params={
        "response_type": "ecobeePin", "client_id": API_KEY, "scope": "smartWrite"})
    r.raise_for_status()
    body = r.json()
    _link = {"pin": body["ecobeePin"], "code": body["code"],
             "expires": time.time() + int(body.get("expires_in", 15)) * 60,
             "interval": int(body.get("interval", 30))}
    if _link_task is None or _link_task.done():
        _link_task = asyncio.create_task(_link_poll())
    return get_state()


async def _link_poll():
    """Wait for the PIN to be entered at ecobee.com → My Apps."""
    global _link
    while _link and time.time() < _link["expires"]:
        await asyncio.sleep(_link["interval"])
        try:
            r = await _http.post(f"{API}/token", data={
                "grant_type": "ecobeePin", "code": _link["code"], "client_id": API_KEY})
        except Exception as e:
            log.warning("Ecobee link poll: %s", e)
            continue
        if r.status_code == 200:
            body = r.json()
            _token.update(access_token=body["access_token"], refresh_token=body["refresh_token"])
            _write_json(TOKEN_PATH, _token)
            _status["auth"] = "ok"
            log.info("Ecobee linked")
            break
    _link = None
    await refresh_state()
    await _broadcast()


# ── public ────────────────────────────────────────────────────────────────
def get_state() -> dict:
    return {
        **_status,
        **_therm,
        "in_peak": in_peak(),
        "peak_start": _auto["peak_start"],
        "peak_end": _auto["peak_end"],
        "skip_today": _auto["skip_date"] == datetime.now(TZ).date().isoformat(),
        "shed": _auto["saved"] is not None,
        "auto_error": _auto_error,
        "link_pin": _link["pin"] if _link else None,
        "hold_hours": HOLD_HOURS,
    }


async def connect():
    global _http
    _http = httpx.AsyncClient(timeout=15)
    _load()
    await refresh_state()
    asyncio.create_task(_runner())
