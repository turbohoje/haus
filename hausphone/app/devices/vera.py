"""Vera Z-Wave hub — HTTP REST wrapper."""
import logging
import httpx

log = logging.getLogger(__name__)

VERA_BASE = "http://10.22.14.4:3480/data_request"
SVC = "urn:upnp-org:serviceId:SwitchPower1"

DEVICES = {
    "light_west": {"id": 39, "label": "Light West"},
    "light_east": {"id": 40, "label": "Light East"},
}

_state: dict = {k: None for k in DEVICES}


async def refresh_state() -> dict:
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
    return dict(_state)


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
