"""Vera Z-Wave hub — HTTP REST wrapper."""
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
    "garage": {"id": 36, "label": "Garage"},
}

_state: dict = {k: None for k in DEVICES}
_last_refresh: float = 0.0


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
                _state[key] = val == "1"
            except Exception as e:
                log.warning("Vera state error for %s: %s", key, e)
    _last_refresh = time.monotonic()
    return dict(_state)


async def refresh_if_stale(max_age: float = 3.0) -> dict:
    if time.monotonic() - _last_refresh > max_age:
        return await refresh_state()
    return get_state()


def get_state() -> dict:
    return dict(_state)


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
    return get_state()
