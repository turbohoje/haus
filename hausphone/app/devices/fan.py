"""Big Ass Fan Haiku — aiobafi6 wrapper (i6 protobuf protocol, firmware 3.0+)."""
import asyncio
import logging

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
        from aiobafi6 import Device, OffOnAuto, PORT, Service
    except ImportError:
        log.warning("aiobafi6 not installed — fan controls disabled")
        return False
    try:
        service = Service(ip_addresses=[FAN_IP], port=PORT)
        _device = Device(service)
        _device.async_run()
        await asyncio.wait_for(_device.async_wait_available(), timeout=10)
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
        from aiobafi6 import OffOnAuto
        _state["fan_on"] = _device.fan_mode == OffOnAuto.ON if _device.fan_mode is not None else None
        _state["fan_speed"] = _device.speed_percent
        _state["light_on"] = _device.light_mode == OffOnAuto.ON if _device.light_mode is not None else None
        _state["light_brightness"] = _device.light_brightness_percent
    except Exception as e:
        log.warning("Fan state refresh error: %s", e)
    return _state


def get_state() -> dict:
    return dict(_state)


async def set_fan_power(on: bool) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    from aiobafi6 import OffOnAuto
    _device.fan_mode = OffOnAuto.ON if on else OffOnAuto.OFF
    _state["fan_on"] = on
    return get_state()


async def set_fan_speed(percent: int) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    from aiobafi6 import OffOnAuto
    pct = max(0, min(100, percent))
    _device.speed_percent = pct
    _state["fan_speed"] = pct
    if pct > 0:
        _device.fan_mode = OffOnAuto.ON
        _state["fan_on"] = True
    return get_state()


async def set_light_power(on: bool) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    from aiobafi6 import OffOnAuto
    _device.light_mode = OffOnAuto.ON if on else OffOnAuto.OFF
    _state["light_on"] = on
    return get_state()


async def set_light_brightness(percent: int) -> dict:
    if _device is None:
        raise RuntimeError("Fan not connected")
    from aiobafi6 import OffOnAuto
    pct = max(0, min(100, percent))
    _device.light_brightness_percent = pct
    _state["light_brightness"] = pct
    if pct > 0:
        _device.light_mode = OffOnAuto.ON
        _state["light_on"] = True
    return get_state()
