"""WeMo smart plug control — pywemo direct-by-IP, with optional auto-off timer."""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "wemo_config.json"

# Runtime state: { device_name: {"on": bool, "timer_end": float|None} }
_state: dict = {}
_config: list = []
_timers: dict = {}  # name -> asyncio.Task


def load_config():
    global _config
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    _config = data.get("devices", [])
    for dev in _config:
        _state[dev["name"]] = {"on": None, "timer_end": None, "label": dev.get("label", dev["name"])}
    log.info("WeMo config loaded: %s", [d["name"] for d in _config])


def _get_device(ip: str):
    try:
        import pywemo
    except ImportError:
        raise RuntimeError("pywemo not installed — wemo controls disabled")
    url = f"http://{ip}:49153/setup.xml"
    return pywemo.discovery.device_from_description(url)


def get_state() -> dict:
    now = time.time()
    result = {}
    for name, s in _state.items():
        remaining = None
        if s["timer_end"] is not None:
            remaining = max(0, int(s["timer_end"] - now))
        result[name] = {
            "on": s["on"],
            "timer_remaining": remaining,
            "label": s["label"],
        }
    return result


async def refresh_state() -> dict:
    loop = asyncio.get_event_loop()
    for dev in _config:
        name = dev["name"]
        ip = dev["ip"]
        try:
            device = await loop.run_in_executor(None, _get_device, ip)
            raw = await loop.run_in_executor(None, device.get_state)
            _state[name]["on"] = bool(raw)
        except Exception as e:
            log.warning("WeMo state error for %s: %s", name, e)
    return get_state()


async def set_power(device_name: str, on: bool) -> dict:
    dev_conf = next((d for d in _config if d["name"] == device_name), None)
    if dev_conf is None:
        raise ValueError(f"Unknown wemo device: {device_name}")

    loop = asyncio.get_event_loop()
    device = await loop.run_in_executor(None, _get_device, dev_conf["ip"])
    if on:
        await loop.run_in_executor(None, device.on)
    else:
        await loop.run_in_executor(None, device.off)

    _state[device_name]["on"] = on

    # Handle auto-off timer
    if on and dev_conf.get("auto_off_minutes"):
        minutes = dev_conf["auto_off_minutes"]
        _state[device_name]["timer_end"] = time.time() + minutes * 60
        _schedule_auto_off(device_name, minutes * 60)
    elif not on:
        _cancel_timer(device_name)
        _state[device_name]["timer_end"] = None

    return get_state()


def _cancel_timer(device_name: str):
    task = _timers.pop(device_name, None)
    if task and not task.done():
        task.cancel()


def _schedule_auto_off(device_name: str, delay_seconds: float):
    _cancel_timer(device_name)

    async def _auto_off():
        await asyncio.sleep(delay_seconds)
        log.info("Auto-off timer fired for %s", device_name)
        try:
            await set_power(device_name, False)
        except Exception as e:
            log.warning("Auto-off failed for %s: %s", device_name, e)

    task = asyncio.create_task(_auto_off())
    _timers[device_name] = task


def get_timer_remaining(device_name: str) -> Optional[int]:
    s = _state.get(device_name)
    if s is None or s["timer_end"] is None:
        return None
    remaining = int(s["timer_end"] - time.time())
    return max(0, remaining)
