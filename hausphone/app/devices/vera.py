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
    "attic1": {"id": 67, "label": "Attic1"},
    "attic2": {"id": 68, "label": "Attic2"},
    "ld_floor": {"id": 192, "label": "LD Floor"},
    "garage": {"id": 36, "label": "Garage"},
    "l_fire": {"id": 142, "label": "Living Fire", "auto_off_minutes": 90},
    "m_fire": {"id": 85, "label": "Master Fire", "auto_off_minutes": 90},
}

_state: dict = {k: None for k in DEVICES}
_timer_end: dict = {k: None for k in DEVICES}
_timers: dict = {}  # device_key -> asyncio.Task
_last_refresh: float = 0.0


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
