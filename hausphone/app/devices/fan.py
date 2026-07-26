"""Big Ass Fan Haiku — aiobafi6 wrapper (i6 protobuf protocol, firmware 3.0+)."""
import asyncio
import logging

log = logging.getLogger(__name__)

FAN_IP = "10.22.14.20"
CONNECT_TIMEOUT = 10  # seconds to wait for async_wait_available

_device = None
_connect_lock = asyncio.Lock()
_state: dict = {
    "fan_on": None,
    "fan_speed": None,
    "light_on": None,
    "light_brightness": None,
}


async def _ensure_connected() -> bool:
    """Return True if the fan device is connected; attempt (re)connect if not.

    Safe to call repeatedly — uses a lock so concurrent callers don't race to
    create multiple Device instances. Re-runs connect when the previous device
    object is gone OR its background loop reports unavailable.
    """
    global _device
    if _device is not None and getattr(_device, "available", False):
        return True
    async with _connect_lock:
        if _device is not None and getattr(_device, "available", False):
            return True
        try:
            from aiobafi6 import Device, PORT, Service
        except ImportError:
            log.warning("aiobafi6 not installed — fan controls disabled")
            return False
        try:
            service = Service(ip_addresses=[FAN_IP], port=PORT)
            new_device = Device(service)
            new_device.async_run()
            await asyncio.wait_for(new_device.async_wait_available(), timeout=CONNECT_TIMEOUT)
            _device = new_device
            log.info("Fan connected at %s", FAN_IP)
            return True
        except Exception as e:
            log.warning("Fan connect failed: %s", e or type(e).__name__)
            return False


async def connect() -> bool:
    """Initial connect at app startup. Non-fatal — reconnect is retried lazily."""
    ok = await _ensure_connected()
    if ok:
        await refresh_state()
    return ok


async def refresh_state() -> dict:
    """Pull latest state; opportunistically reconnect if the device dropped."""
    if not await _ensure_connected():
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


async def _require_device():
    if not await _ensure_connected():
        raise RuntimeError("Fan not connected")


async def set_fan_power(on: bool) -> dict:
    await _require_device()
    from aiobafi6 import OffOnAuto
    _device.fan_mode = OffOnAuto.ON if on else OffOnAuto.OFF
    _state["fan_on"] = on
    return get_state()


async def set_fan_speed(percent: int) -> dict:
    await _require_device()
    from aiobafi6 import OffOnAuto
    # Haiku has 7 discrete speed levels; speed_percent is read-only.
    pct = max(0, min(100, percent))
    speed = round(pct * 7 / 100)
    _device.speed = speed
    _state["fan_speed"] = round(speed * 100 / 7)
    if speed > 0:
        _device.fan_mode = OffOnAuto.ON
        _state["fan_on"] = True
    return get_state()


async def set_light_power(on: bool) -> dict:
    await _require_device()
    from aiobafi6 import OffOnAuto
    _device.light_mode = OffOnAuto.ON if on else OffOnAuto.OFF
    _state["light_on"] = on
    return get_state()


async def set_light_brightness(percent: int) -> dict:
    await _require_device()
    from aiobafi6 import OffOnAuto
    pct = max(0, min(100, percent))
    _device.light_brightness_percent = pct
    _state["light_brightness"] = pct
    if pct > 0:
        _device.light_mode = OffOnAuto.ON
        _state["light_on"] = True
    return get_state()
