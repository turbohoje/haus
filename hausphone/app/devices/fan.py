"""Big Ass Fan Haiku — aiobafi6 wrapper (i6 protobuf protocol, firmware 3.0+)."""
import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

FAN_IP = "10.22.14.20"

_device = None
_state: dict = {
    "fan_on": None,
    "fan_speed": None,
    "light_on": None,
    "light_brightness": None,
}


async def connect() -> bool:
    global _device
    try:
        from aiobafi6 import Device  # noqa: F401 — optional dep
    except ImportError:
        log.warning("aiobafi6 not installed — fan controls disabled")
        return False
    try:
        _device = Device(ip=FAN_IP)
        await _device.async_run()
        await refresh_state()
        log.info("Fan connected at %s", FAN_IP)
        return True
    except Exception as e:
        log.warning("Fan connect failed: %s", e)
        _device = None
        return False


async def refresh_state() -> dict:
    if _device is None:
        return _state
    try:
        _state["fan_on"] = bool(_device.fan_on)
        _state["fan_speed"] = _device.fan_speed
        _state["light_on"] = bool(_device.light_on)
        _state["light_brightness"] = _device.light_brightness_level
    except Exception as e:
        log.warning("Fan state refresh error: %s", e)
    return _state


def get_state() -> dict:
    return dict(_state)


async def set_fan_power(on: bool) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    await _device.async_set_fan_on(on)
    _state["fan_on"] = on
    return get_state()


async def set_fan_speed(percent: int) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    pct = max(0, min(100, percent))
    await _device.async_set_fan_speed(pct)
    _state["fan_speed"] = pct
    if pct > 0:
        _state["fan_on"] = True
    return get_state()


async def set_light_power(on: bool) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    await _device.async_set_light_on(on)
    _state["light_on"] = on
    return get_state()


async def set_light_brightness(percent: int) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    pct = max(0, min(100, percent))
    await _device.async_set_light_brightness_level(pct)
    _state["light_brightness"] = pct
    if pct > 0:
        _state["light_on"] = True
    return get_state()
