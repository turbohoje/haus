#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Set

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.devices import fan, wemo
from app.devices import zwave

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
        # Sanity check: refresh device state on app load so externally-flipped
        # switches show their true state, not the cached value from the last poll.
        # Rate-limited inside refresh_if_stale to protect the hub from rapid reconnects.
        try:
            await zwave.refresh_if_stale()
        except Exception as e:
            log.warning("WS connect refresh error: %s", e)
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


@app.get("/cert.crt")
async def serve_cert():
    cert = Path("/certs/cert.pem")
    if not cert.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Certificate not found")
    return FileResponse(
        str(cert),
        media_type="application/x-x509-ca-cert",
        filename="haus-ca.crt",
    )


# --------------------------------------------------------------------------
# State aggregation
# --------------------------------------------------------------------------
def _collect_state() -> dict:
    return {
        "fan": fan.get_state(),
        "zwave": zwave.get_state(),
        "attic_timers": zwave.get_attic_timers(),
        "locks": zwave.get_locks_state(),
        "wemo": wemo.get_state(),
    }


@app.get("/api/state")
async def get_state():
    return _collect_state()


# --------------------------------------------------------------------------
# Fan control
# --------------------------------------------------------------------------
@app.post("/api/fan/power")
async def fan_power(body: dict = Body(...)):
    state = await fan.set_fan_power(bool(body.get("on")))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/fan/speed")
async def fan_speed(body: dict = Body(...)):
    state = await fan.set_fan_speed(int(body.get("percent", 0)))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/light/power")
async def light_power(body: dict = Body(...)):
    state = await fan.set_light_power(bool(body.get("on")))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


@app.post("/api/light/brightness")
async def light_brightness(body: dict = Body(...)):
    state = await fan.set_light_brightness(int(body.get("percent", 0)))
    await broadcast({"type": "state", "data": {"fan": state}})
    return state


# --------------------------------------------------------------------------
# Z-Wave control
# --------------------------------------------------------------------------
@app.post("/api/zwave/{device_key}/power")
async def zwave_power(device_key: str, body: dict = Body(...)):
    state = await zwave.set_power(device_key, bool(body.get("on")))
    await broadcast({"type": "state", "data": {"zwave": state}})
    return state


# --------------------------------------------------------------------------
# Door locks (S0-secured Allegion deadbolts)
# --------------------------------------------------------------------------
@app.post("/api/lock/{lock_key}")
async def lock_set(lock_key: str, body: dict = Body(...)):
    state = await zwave.set_lock(lock_key, bool(body.get("locked")))
    await broadcast({"type": "state", "data": {"locks": state}})
    return state


# --------------------------------------------------------------------------
# Attic timers (delay-on, off-timer)
# --------------------------------------------------------------------------

@app.post("/api/attic/delay-on")
async def attic_delay_on(body: dict = Body(...)):
    state = await zwave.set_attic_delay_on(
        bool(body.get("armed")),
        body.get("fans") or [],
        int(body.get("duration_seconds") or 0),
    )
    await broadcast({"type": "state", "data": {"attic_timers": state}})
    return state


@app.post("/api/attic/off-timer")
async def attic_off_timer(body: dict = Body(...)):
    state = await zwave.set_attic_off_timer(
        bool(body.get("armed")),
        int(body.get("duration_seconds") or 0),
    )
    await broadcast({"type": "state", "data": {"attic_timers": state}})
    return state


# --------------------------------------------------------------------------
# WeMo control
# --------------------------------------------------------------------------
@app.post("/api/wemo/{device_name}/power")
async def wemo_power(device_name: str, body: dict = Body(...)):
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

    def _maybe_emit(self, path: str):
        if path != IMAGE_PATH:
            return
        now = time.monotonic()
        if now - self._last_emit < 0.2:
            return
        self._last_emit = now
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "image_refresh"}),
            _loop,
        )

    def on_modified(self, event):
        self._maybe_emit(event.src_path)

    def on_created(self, event):
        self._maybe_emit(event.src_path)

    def on_moved(self, event):
        self._maybe_emit(event.dest_path)


# --------------------------------------------------------------------------
# Background polling — device state every 60s
# --------------------------------------------------------------------------
async def _poll_loop():
    await asyncio.sleep(5)  # let startup settle
    while True:
        try:
            await fan.refresh_state()
            await zwave.refresh_state()
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

    # Let zwave push state updates when its background timers fire
    zwave.register_broadcast(lambda data: broadcast({"type": "state", "data": data}))

    # Connect to fan (non-fatal if unavailable)
    try:
        await fan.connect()
    except Exception as e:
        log.warning("Fan startup error: %s", e)

    # Connect to Z-Wave JS (non-fatal if unavailable; refresh_state self-heals)
    try:
        await zwave.connect()
    except Exception as e:
        log.warning("Z-Wave startup error: %s", e)

    # Initial state poll
    try:
        await zwave.refresh_state()
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
