#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.devices import fan, vera, wemo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("main")

IMAGE_PATH = os.environ.get(
    "IMAGE_PATH",
    "/home/turbohoje/haus/ffmpeg/imgproc/output.jpg",
)
STATIC_DIR = Path(__file__).parent / "static"
PLACEHOLDER = STATIC_DIR / "placeholder.jpg"
STATE_POLL_INTERVAL = 60  # seconds

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --------------------------------------------------------------------------
# WebSocket connection manager
# --------------------------------------------------------------------------
_ws_clients: Set[WebSocket] = set()


async def broadcast(msg: dict):
    dead = set()
    payload = json.dumps(msg)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    log.info("WS client connected (total: %d)", len(_ws_clients))
    try:
        # Send full state immediately on connect
        await ws.send_text(json.dumps({"type": "state", "data": _collect_state()}))
        while True:
            await ws.receive_text()  # keep alive; ignore client messages for now
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
        log.info("WS client disconnected (total: %d)", len(_ws_clients))


# --------------------------------------------------------------------------
# Image serving
# --------------------------------------------------------------------------
def _image_path() -> Path:
    p = Path(IMAGE_PATH)
    return p if p.exists() else PLACEHOLDER


@app.get("/image")
async def serve_image():
    p = _image_path()
    return FileResponse(str(p), media_type="image/jpeg", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


# --------------------------------------------------------------------------
# PWA routes
# --------------------------------------------------------------------------
@app.get("/manifest.json")
async def manifest():
    return FileResponse(str(STATIC_DIR / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(str(STATIC_DIR / "sw.js"), media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# --------------------------------------------------------------------------
# State aggregation
# --------------------------------------------------------------------------
def _collect_state() -> dict:
    return {
        "fan": fan.get_state(),
        "vera": vera.get_state(),
        "wemo": wemo.get_state(),
    }


@app.get("/api/state")
async def get_state():
    return _collect_state()


# --------------------------------------------------------------------------
# Fan control
# --------------------------------------------------------------------------
@app.post("/api/fan/power")
async def fan_power(body: dict):
    state = await fan.set_fan_power(bool(body.get("on")))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/fan/speed")
async def fan_speed(body: dict):
    state = await fan.set_fan_speed(int(body.get("percent", 0)))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/light/power")
async def light_power(body: dict):
    state = await fan.set_light_power(bool(body.get("on")))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/light/brightness")
async def light_brightness(body: dict):
    state = await fan.set_light_brightness(int(body.get("percent", 0)))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


# --------------------------------------------------------------------------
# Vera control
# --------------------------------------------------------------------------
@app.post("/api/vera/{device_key}/power")
async def vera_power(device_key: str, body: dict):
    state = await vera.set_power(device_key, bool(body.get("on")))
    await broadcast({"type": "state", "data": {"vera": state}})
    return state


# --------------------------------------------------------------------------
# WeMo control
# --------------------------------------------------------------------------
@app.post("/api/wemo/{device_name}/power")
async def wemo_power(device_name: str, body: dict):
    state = await wemo.set_power(device_name, bool(body.get("on")))
    await broadcast({"type": "state", "data": {"wemo": state}})
    return state


# --------------------------------------------------------------------------
# Watchdog — image file monitoring
# --------------------------------------------------------------------------
class ImageChangeHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self._last_emit = 0.0

    def on_modified(self, event):
        if event.src_path != IMAGE_PATH:
            return
        now = time.monotonic()
        if now - self._last_emit < 0.2:
            return
        self._last_emit = now
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "image_refresh"}),
            _loop,
        )


# --------------------------------------------------------------------------
# Background polling — device state every 60s
# --------------------------------------------------------------------------
async def _poll_loop():
    await asyncio.sleep(5)  # let startup settle
    while True:
        try:
            await fan.refresh_state()
            await vera.refresh_state()
            await wemo.refresh_state()
            await broadcast({"type": "state", "data": _collect_state()})
            log.info("Device state polled")
        except Exception as e:
            log.warning("Poll error: %s", e)
        await asyncio.sleep(STATE_POLL_INTERVAL)


# --------------------------------------------------------------------------
# Startup / shutdown
# --------------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop = None
_observer: Observer = None


@app.on_event("startup")
async def startup():
    global _loop, _observer
    _loop = asyncio.get_event_loop()

    wemo.load_config()

    # Connect to fan (non-fatal if unavailable)
    try:
        await fan.connect()
    except Exception as e:
        log.warning("Fan startup error: %s", e)

    # Initial state poll
    try:
        await vera.refresh_state()
        await wemo.refresh_state()
    except Exception as e:
        log.warning("Initial poll error: %s", e)

    # File watcher (skip gracefully if image dir missing — dev/test mode)
    image_dir = Path(IMAGE_PATH).parent
    if image_dir.exists():
        _observer = Observer()
        _observer.schedule(ImageChangeHandler(), str(image_dir), recursive=False)
        _observer.start()
        log.info("Watching %s", IMAGE_PATH)
    else:
        log.warning("Image dir %s not found — file watcher disabled (dev mode)", image_dir)

    # Background poller
    asyncio.create_task(_poll_loop())
    log.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    if _observer is not None:
        _observer.stop()
        _observer.join()
