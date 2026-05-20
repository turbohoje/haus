# hausphone — Design Context

## Purpose
Phone-optimized home automation PWA. Replaces `ffmpeg/webserver` on port 3000.
App-free experience: install via browser "Add to Home Screen" on Android and iOS.
One-hand operable on phone; large well-spaced controls.

---

## Host / Deployment
- **Target host:** Intel NUC at `10.22.14.2`
- **Port:** `3000`
- **Deployment:** Docker container (`restart: unless-stopped`)
- **Old service:** `ffmpeg-webserver.service` — keep old code in `ffmpeg/webserver/`

### Running via Docker (production)
```bash
docker compose up -d --build
docker logs hausphone          # check startup
docker compose down            # stop
```

### Running locally (dev/test)
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
IMAGE_PATH=/home/turbohoje/haus/ffmpeg/imgproc/output.jpg \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```
If `IMAGE_PATH` doesn't exist the file watcher is skipped and a placeholder image is served — that's fine for dev.

---

## Tech Stack
- **Backend:** Python + FastAPI
- **WebSockets:** FastAPI native WebSocket
- **File watching:** `watchdog`
- **Fan control:** `aiobafi6` (async, direct-by-IP)
- **Z-Wave:** HTTP REST to Vera hub at `http://10.22.14.4:3480`
- **WeMo:** `pywemo` direct-by-IP
- **Frontend:** Vanilla HTML/CSS/JS; dark theme; no framework
- **PWA:** Web App Manifest + Service Worker

---

## Image Feed
- Source: `/home/turbohoje/haus/ffmpeg/imgproc/output.jpg` (written by ffmpeg ~every second, owned by root)
- Pushed to clients via WebSocket `image_refresh` message when file changes (watchdog, rate-limited ≤5/sec)
- The watchdog handles `on_modified`, `on_created`, AND `on_moved` — ffmpeg may atomically replace the file via rename, which triggers `on_created`/`on_moved` not `on_modified`
- Docker bind mount: `/home/turbohoje/haus/ffmpeg/imgproc:/imgproc:ro`

---

## Devices & Controls

### Big Ass Fan — Haiku (10.22.14.20)
- Protocol: i6 / protobuf (firmware 3.0+); library: `aiobafi6`
- **UI label:** M.Fan (fan) / M.Light (light) — shown as a single paired card
- Fan + light toggles share one card row; sliders expand full card width below

#### aiobafi6 API (v0.9.0) — IMPORTANT
The API changed significantly from older versions. Do NOT use the old `Device(ip=...)` pattern.

```python
from aiobafi6 import Device, OffOnAuto, PORT, Service

service = Service(ip_addresses=[FAN_IP], port=PORT)
device = Device(service)
device.async_run()                                    # starts background connection loop; no need to store the future
await asyncio.wait_for(device.async_wait_available(), timeout=10)

# Read state
fan_on     = device.fan_mode == OffOnAuto.ON          # fan_mode is OffOnAuto enum (OFF/ON/AUTO)
fan_speed  = device.speed_percent                     # 0–100 (READ-ONLY)
light_on   = device.light_mode == OffOnAuto.ON
brightness = device.light_brightness_percent          # 0–100

# Write state (synchronous property assignment — sends to device immediately)
device.fan_mode = OffOnAuto.ON
device.speed = 4                # 0–7 discrete (speed_percent is read-only — map pct→0-7)
device.light_mode = OffOnAuto.OFF
device.light_brightness_percent = 75
```

### Vera Z-Wave Hub (10.22.14.4)
- REST API: `http://10.22.14.4:3480/data_request`
- Service ID: `urn:upnp-org:serviceId:SwitchPower1`
- State query: `?id=variableget&DeviceNum=N&serviceId=...&Variable=Status`
- Control: `?id=action&DeviceNum=N&serviceId=...&action=SetTarget&newTargetValue=0|1`

#### Current devices (`app/devices/vera.py`)
| Key | Device ID | UI Label |
|-----|-----------|----------|
| `light_west` | 39 | Lght W |
| `light_east` | 40 | Lght E |
| `attic1` | 68 | Attic1 (multi-channel endpoint e1 of master 67) |
| `attic2` | 69 | Attic2 (multi-channel endpoint e2 of master 67) |
| `garage` | 36 | Garage (slide-to-activate) |

To add a new Vera device: add an entry to `DEVICES` in `vera.py`. No other changes needed — the REST wrapper, state polling, and API endpoint handle all keys generically.

### WeMo Smart Plugs
- Controlled via `pywemo` direct-by-IP
- Config: `wemo_config.json`
- **Water Feature** (10.22.14.100): on/off + auto-off after 2 hours, countdown timer in UI

#### pywemo API (v1.2.0) — IMPORTANT
`device_from_description()` takes only 1 positional argument (the URL). Do NOT pass a second `None` argument.
```python
device = pywemo.discovery.device_from_description(f"http://{ip}:49153/setup.xml")
```
Discovery takes ~1 second per device; always call via `loop.run_in_executor`.

#### `wemo_config.json` schema
```json
{
  "devices": [
    {
      "name": "water_feature",
      "label": "Water Feature",
      "ip": "10.22.14.100",
      "auto_off_minutes": 120
    }
  ]
}
```
The `name` field is used as the API key (e.g. `/api/wemo/water_feature/power`) — use snake_case.

---

## UI Layout

### Card structure
Cards use a dark surface with rounded corners. There are two card patterns:

**Single card** — one device per card:
```html
<div class="card">
  <div class="card-header">
    <span class="status-dot" id="..."></span>
    <span class="card-label">Name</span>
    <button class="toggle-btn" id="...">OFF</button>
  </div>
</div>
```

**Paired card** — two devices side by side in one card row, optional full-width sliders below:
```html
<div class="card">
  <div class="card-pair">
    <div class="card-half">
      <div class="card-header">...<button class="expand-btn">⌄</button></div>
    </div>
    <div class="card-pair-divider"></div>
    <div class="card-half">
      <div class="card-header">...</div>
    </div>
  </div>
  <!-- Sliders live OUTSIDE .card-pair so they expand full card width -->
  <div class="card-detail" id="...">
    <div class="slider-row">...</div>
  </div>
</div>
```

### Current card order (top to bottom)
1. **M.Fan / M.Light** — paired card, fan speed + brightness sliders
2. **Lght E / Lght W** — paired card, no sliders (E on left, W on right)
3. **Attic1 / Attic2** — paired card, no sliders
4. **Water Feature** — single card, auto-off countdown timer
5. **Garage** — single card, slide-to-activate (prevents pocket-dial)

---

## PWA / Service Worker
- Cache key is `"haus-vN"` in `sw.js` — **bump N whenever any static file changes** so phones receive the updated files
- Current version: `haus-v20`
- Keep the version label in `index.html` (`#app-version`) in sync with the cache key — it's shown in the top bar so you can verify which build a phone is running.
- Network-first strategy for app shell (always fetches from server when online, falls back to cache)
- Never caches `/image`, `/api/*`, or `/ws`
- `skipWaiting()` + `clients.claim()` means new SW activates immediately on install

---

## FastAPI — Body Parsing
All POST endpoints that accept a JSON body **must** use `Body(...)` explicitly:
```python
from fastapi import Body

@app.post("/api/fan/power")
async def fan_power(body: dict = Body(...)):
    ...
```
Without `= Body(...)`, FastAPI may not parse the JSON body correctly.

---

## WebSocket Protocol (server → client)
- `{"type": "image_refresh"}` — new camera frame available, client sets `img.src = "/image?t=" + Date.now()`
- `{"type": "state", "data": {...}}` — full or partial state snapshot; sent on WS connect and after every control action

## REST API Endpoints (client → server)
```
GET  /                              — serve PWA shell
GET  /image                         — current JPEG (no-cache)
GET  /api/state                     — full device state snapshot
POST /api/fan/power                 { "on": true|false }
POST /api/fan/speed                 { "percent": 0-100 }
POST /api/light/power               { "on": true|false }
POST /api/light/brightness          { "percent": 0-100 }
POST /api/vera/{device_key}/power   { "on": true|false }
POST /api/wemo/{device_name}/power  { "on": true|false }
POST /api/vera/system/zwave-reset   (no body) — soft-reboot the Z-Wave chip (keeps pairings)
POST /api/vera/system/reload-engine (no body) — reload Luup engine
POST /api/vera/system/reboot        (no body) — reboot the entire Vera (WiFi drops)
```

Vera system actions live in the settings overlay (gear icon), not in the main controls panel.

Device state is cached in-memory on the server; re-polled from hardware every 60 seconds. On WebSocket connect (i.e. app load) Vera state is refreshed from hardware if the cache is older than 3 seconds — this catches switches flipped externally. Other device types still serve cached state on connect.

---

## File Structure
```
hausphone/
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── wemo_config.json
├── app/
│   ├── main.py             ← FastAPI app, WebSocket, watchdog, background poller
│   ├── devices/
│   │   ├── fan.py          ← aiobafi6 wrapper
│   │   ├── vera.py         ← Vera REST wrapper
│   │   └── wemo.py         ← pywemo wrapper + auto-off timer
│   └── static/
│       ├── index.html      ← PWA shell
│       ├── manifest.json
│       ├── sw.js           ← service worker (bump cache version on deploy)
│       ├── app.js
│       └── style.css
```

---

## Future / Out of Scope Now
- Tailscale hostname/IP for the NUC — add to offline banner when known
- Security camera analysis + push notifications
- Desktop dashboard verbose layout
- Additional Vera devices, TVs, thermostats
- Auto/whoosh fan modes
- Re-poll fan/wemo on WebSocket connect (Vera is already re-polled; fan is push-based via aiobafi6, wemo less critical)
