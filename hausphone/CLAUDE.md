# hausphone — Design Context

## Purpose
Phone-optimized home automation PWA. Replaces `ffmpeg/webserver` on port 3000.
App-free experience: install via browser "Add to Home Screen" on Android and iOS.
One-hand operable on phone; large well-spaced controls.

---

## Host / Deployment
- **Target host:** Intel NUC, same machine running `ffmpeg/webserver`
- **Static LAN IP:** `10.22.14.2`
- **Port:** `3000` (replaces existing Flask service)
- **Deployment:** Docker container
- **Dev/test:** Runs locally on macOS laptop; image placeholder used when `output.jpg` is unavailable
- **Old service:** `ffmpeg-webserver.service` — to be stopped/disabled once hausphone is stable; keep old code in `ffmpeg/webserver/`

---

## Tech Stack
- **Backend:** Python + FastAPI
- **WebSockets:** FastAPI native WebSocket (or `python-socketio` if Socket.IO client needed)
- **File watching:** `watchdog` (same as old service)
- **Fan control:** `aiobafi6` (async, connects direct-by-IP, no mDNS discovery)
- **Z-Wave:** HTTP REST to Vera hub at `http://10.22.14.4:3480`
- **WeMo:** `pywemo` via subprocess call to `wemo/wemo.sh`, or direct `pywemo` import
- **Frontend:** Vanilla HTML/CSS/JS; dark theme; no framework required
- **PWA:** Web App Manifest + Service Worker; installable on Android and iOS

---

## Image Feed
- Source: `/home/turbohoje/haus/ffmpeg/imgproc/output.jpg` (same file as old webserver)
- Push updates via WebSocket when file is modified (watchdog, rate-limited ≤5/sec)
- On laptop dev: serve a placeholder image (gray box or static JPEG) if path unavailable
- Image displayed at top of page, full-width, same as existing app

---

## Devices & Controls

### Big Ass Fan — Haiku (10.22.14.20)
- Protocol: i6 / protobuf (firmware 3.0+); library: `aiobafi6` (PyPI)
- Connect direct-by-IP (no mDNS discovery)
- **Fan:** on/off toggle (primary, large) + speed slider (0–100%, secondary/collapsible)
- **Light:** on/off toggle (primary, large) + brightness slider (0–100%, secondary/collapsible)
- No auto/whoosh mode needed

### Vera Z-Wave Hub (10.22.14.4)
- REST API: `http://10.22.14.4:3480/data_request`
- **Device 39 — Light West:** on/off switch (dry contact, no dimming)
- **Device 40 — Light East:** on/off switch (dry contact, no dimming)
- Service ID for switching: `urn:upnp-org:serviceId:SwitchPower1`
- State query: `?id=variableget&DeviceNum=N&serviceId=...&Variable=Status`
- Control: `?id=action&DeviceNum=N&serviceId=...&action=SetTarget&newTargetValue=0|1`

### WeMo Smart Plugs
- Controlled via `pywemo` (direct-by-IP, fast path)
- Config file: `hausphone/wemo_config.json` — list of devices with name, IP, and optional timer settings
- **Water Feature** (10.22.14.100):
  - On/off toggle
  - Auto-off after **2 hours** when turned on
  - Countdown timer displayed in UI
  - User can cancel early (manual off clears countdown)
  - Timer start time saved to `wemo_config.json` so it survives... actually in-memory is fine; restarts are rare
  - Timer is specific to this device; configured in `wemo_config.json` as `"auto_off_minutes": 120`
- Future WeMos: add to `wemo_config.json` with name + IP; non-timer devices get simple on/off toggle

#### `wemo_config.json` schema
```json
{
  "devices": [
    {
      "name": "Water Feature",
      "ip": "10.22.14.100",
      "auto_off_minutes": 120
    }
  ]
}
```

---

## UI Layout

### Phone (viewport width < ~768px, CSS media query)
- Full-width live camera image at top
- Large, well-spaced touch buttons below image
- Each device card: prominent toggle button
- Sliders (fan speed, light brightness) hidden by default, revealed by tapping a "adjust" chevron/expander
- WeMo Water Feature shows countdown timer when active

### Desktop / wide viewport
- Same layout, slightly denser
- More verbose state labels
- (Future: richer dashboard — not a priority now)

---

## PWA Behavior
- Web App Manifest: `manifest.json` — name, icons, `display: standalone`, dark theme color
- Service Worker: caches app shell; on new deploy, activates on next app open (safe, not mid-session)
- Install prompt: shown if PWA not already installed
- iOS: "Add to Home Screen" instructions shown if Safari detected and not standalone

### Offline / Off-Network Handling
- On load, app checks reachability of `10.22.14.2:3000`
- If unreachable: show banner — "Not on home network. Connect to home WiFi or Tailscale to use controls."
- Tailscale suggestion: generic for now (no specific Tailscale IP configured yet)
- Controls are disabled/grayed when offline; image feed shows last cached frame or placeholder

---

## WebSocket Protocol (server → client)
- `image_refresh` — new camera frame available, client reloads `/image`
- `device_state` — broadcast updated state for any device after a control action
  ```json
  { "device": "fan", "property": "power", "value": true }
  ```

## REST API Endpoints (client → server)
```
GET  /               — serve PWA shell
GET  /image          — current JPEG (no-cache)
GET  /api/state      — full device state snapshot
POST /api/fan/power          { "on": true|false }
POST /api/fan/speed          { "percent": 0-100 }
POST /api/light/power        { "on": true|false }
POST /api/light/brightness   { "percent": 0-100 }
POST /api/vera/{device_id}/power   { "on": true|false }
POST /api/wemo/{device_name}/power { "on": true|false }
GET  /api/wemo/{device_name}/timer — returns remaining seconds if active
```

---

## File Structure (planned)
```
hausphone/
├── CLAUDE.md               ← this file
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── wemo_config.json        ← WeMo device definitions
├── app/
│   ├── main.py             ← FastAPI app, WebSocket, watchdog
│   ├── devices/
│   │   ├── fan.py          ← aiobafi6 wrapper
│   │   ├── vera.py         ← Vera REST wrapper
│   │   └── wemo.py         ← pywemo wrapper + timer logic
│   └── static/
│       ├── index.html      ← PWA shell
│       ├── manifest.json
│       ├── sw.js           ← service worker
│       ├── app.js
│       └── style.css
```

---

## Open Questions (pending answers)
- Tailscale hostname/IP for the NUC — to be added to offline banner
- PWA update strategy confirmed: **activate on next app open** (not immediate mid-session reload)
- WeMo config format: **JSON**
- Docker bind mount for image file: mount host path `/home/turbohoje/haus/ffmpeg/imgproc/` into container

---

## Future / Out of Scope Now
- Security camera still-frame analysis + package detection notifications (push via PWA Notification API)
- Desktop dashboard verbose layout
- Additional Vera devices, TVs, thermostats
- Auto/whoosh fan modes
