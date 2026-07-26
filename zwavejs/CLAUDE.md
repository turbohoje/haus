# zwavejs — Design Context

## Purpose
Replace the Vera hub (`10.22.14.4`) as the Z-Wave controller for the house.
Runs **zwave-js-ui** (formerly zwavejs2mqtt) which bundles three things in one container:

1. **Z-Wave JS driver** — talks to the Zooz 800 USB stick.
2. **Web control panel** (`:8091`) — inclusion/exclusion, healing, naming, firmware, logs.
3. **zwave-js-server WebSocket** (`:3000` in-container → `:3001` on host) — the programmatic
   interface the phone app drives.

The **hausphone** PWA connects directly to the WebSocket via `zwave-js-server-python`.
No MQTT broker, no separate REST shim — hausphone's existing `vera.py` wrapper is swapped
for an interface-compatible `zwave.py`.

```
Zooz 800 stick ──USB──> zwave-js-ui ──WS(:3001)──> hausphone (app/devices/zwave.py) ──> PWA
                          (:8091 UI)
```

---

## Host / Deployment
- **Host:** Intel NUC at `10.22.14.2` (same box as hausphone)
- **Stick:** Zooz 800 Z-Wave Stick — `/dev/serial/by-id/usb-Zooz_800_Z-Wave_Stick_533D004242-if00`
- **Ports:** UI `8091`, WS server `3001` (host) → `3000` (container)
- **Store:** named docker volume `zwave-js-ui-store` (network state **and** security keys — treat as secret)

### Running
```bash
cp .env.example .env      # then fill in SESSION_SECRET + generated keys
docker compose up -d
docker logs zwave-js-ui   # watch driver start + "controller ready"
```

---

## Port conflict — read this
hausphone runs `network_mode: host` and binds host port **3000**. zwave-js-server's default
port is also 3000. The compose publishes the WS as **host 3001 → container 3000** to avoid the
clash. So hausphone connects to `ws://127.0.0.1:3001`, and the UI's WS Server setting stays at
its default port 3000 (that's the *container-internal* port).

---

## First-run setup (in the `:8091` UI)
1. **Settings → Z-Wave**
   - Serial port: `/dev/ttyACM0` (the in-container path the compose maps the stick to;
     the dropdown may not list it, so type it in).
   - Security Keys: paste the four `openssl rand -hex 16` values from `.env`. **Save these keys
     somewhere safe** — losing them means re-including every S2 device.
2. **Settings → Home Assistant** (this is where the WS server lives)
   - Enable **WS Server**, port `3000`. Save + restart the driver.
3. Confirm the WS is up: `docker logs zwave-js-ui | grep -i "listening"` and from the host
   `nc -z 127.0.0.1 3001 && echo ok`.

---

## Migrating devices off Vera
The Vera owns its own Z-Wave radio and all current pairings. There is **no clean NVM transfer**
from a Vera to a Zooz stick, so every device gets **excluded from Vera and re-included into
zwave-js**. Node IDs are assigned fresh — they will NOT match the Vera `DeviceNum`s.

> **Why no backup import (confirmed 2026-07-25):** this Vera is a **VeraPlus** (Sercomm G450),
> Z-Wave dongle **v6.01 = 500-series** chip. The Zooz stick is **800-series**. NVM formats are
> incompatible across those generations, so neither the Vera backup file nor a raw NVM dump can
> be restored onto the Zooz. Over-the-air controller shift is theoretically possible but flaky on
> VeraPlus and does not transfer S2 keys — re-inclusion is the reliable path.

Per device:
1. Vera UI → remove/exclude the device (or just factory-reset the device per its manual).
2. zwave-js-ui → **Manage nodes → Include**, choose Security S2 when prompted, trigger the
   device's pairing action. Prefer **S2** for anything that supports it (all the current
   switches should); fall back to S0 or no-security only if inclusion fails.
3. Note the new **node ID** shown in the nodes table and give it a friendly name/location.
4. Record `key → node_id` in `hausphone/app/devices/zwave.py` `DEVICES`.

### Old Vera map (source of truth for what to re-pair) — from `hausphone/app/devices/vera.py`
| Key | Vera DeviceNum | Label | Notes |
|-----|----------------|-------|-------|
| `light_west` | 39 | Light West | |
| `light_east` | 40 | Light East | |
| `attic1` | 68 | Attic1 | multi-channel endpoint e1 of master 67 |
| `attic2` | 69 | Attic2 | multi-channel endpoint e2 of master 67 |
| `ld_floor` | 192 | LD Floor | |
| `garage` | 36 | Garage | slide-to-activate in UI |
| `l_fire` | 142 | Living Fire | auto_off 90 min |
| `m_fire` | 85 | Master Fire | auto_off 90 min |

> **Multi-channel gotcha (attic1/attic2):** on Vera these were two endpoints (e1/e2) of one
> physical device (master node 67). In zwave-js they show up as **endpoints on a single node**
> (`endpoint 1` / `endpoint 2`), not two separate nodes. `zwave.py` `DEVICES` therefore needs
> both a `node_id` and an `endpoint` for these two keys. See the stub's TODO.

---

## hausphone integration — the swap
`vera.py` already hides the hub behind a clean interface. `zwave.py` mirrors it exactly, so the
migration is a near-zero-diff alias in `main.py`.

### Public interface `zwave.py` must preserve (what `main.py` calls today)
```
connect()                                  # NEW — open the WS + start listen loop (like fan.connect())
register_broadcast(cb)
refresh_state() -> dict
refresh_if_stale(max_age=3.0) -> dict
get_state() -> dict                        # { key: {"on": bool|None, "timer_remaining": int|None} }
set_power(device_key, on) -> dict
get_attic_timers() -> dict
set_attic_delay_on(armed, fans, duration_seconds) -> dict
set_attic_off_timer(armed, duration_seconds) -> dict
soft_reset_zwave() -> dict
reload_engine() -> dict
reboot_vera() -> dict
```

### `main.py` edits (minimal-diff path — keeps all `/api/vera/...` routes + the PWA unchanged)
```python
# 1) import the new module under the old name so nothing downstream changes:
from app.devices import fan, wemo
from app.devices import zwave as vera          # was: ... vera, ...

# 2) open the WS at startup (add alongside the existing fan.connect() call):
try:
    await vera.connect()
except Exception as e:
    log.warning("Z-Wave startup error: %s", e)
```
The `/api/vera/*` URLs, the `"vera"` state key, `app.js`, and the service-worker cache version
all stay as-is. Rename to `/api/zwave/*` later if desired — that's cosmetic and needs a frontend
change + an `sw.js` cache bump (`haus-vN`).

### `requirements.txt`
```
zwave-js-server-python
```
(pulls in `aiohttp`). No MQTT client, no extra service.

---

## System actions — Vera → zwave-js mapping
The PWA's gear/settings overlay has three buttons. Their backends change meaning:

| Endpoint (unchanged) | Vera behavior | zwave-js equivalent |
|----------------------|---------------|---------------------|
| `/api/vera/system/zwave-reset`   | SoftReset the Z-Wave chip | Driver **soft reset** of the controller (keeps network). See stub TODO. |
| `/api/vera/system/reload-engine` | Reload LuaUPnP engine | No analog — map to a driver restart, or drop the button. |
| `/api/vera/system/reboot`        | Reboot whole Vera unit | `docker restart zwave-js-ui` — not reachable from inside hausphone; leave as a stub / remove. |

---

## Polling vs push — behavioral note
Vera was **poll-based** (`refresh_state()` HTTP-GETs every device every 60s). zwave-js is
**event-driven**: the driver pushes `value updated` events, so `zwave.py` keeps `_state` current
in real time and `refresh_state()` just reads the driver's already-cached node values (no network
round-trip). `refresh_if_stale()` on WS-connect becomes cheap. The 60s poll in `main.py` can stay
as a harmless safety net or be relaxed later.

---

## Cutover checklist
- [ ] `docker compose up -d`, driver reaches "controller ready"
- [ ] Enable WS server (:3000), reachable on host `:3001`
- [ ] Re-include all 8 devices; fill `node_id` (+ `endpoint` for attic1/2) in `zwave.py` `DEVICES`
- [ ] `pip install zwave-js-server-python`; local-run hausphone against the stick, verify toggles
- [ ] Flip `main.py` import to `zwave as vera`; rebuild hausphone container
- [ ] Decommission the Vera hub (remove from `10.22.14.4`)

---

## Out of scope now
- MQTT gateway (zwave-js-ui can also publish MQTT if another consumer ever needs it)
- Multilevel dimmers / thermostats / sensors — current devices are all binary switches
- Home Assistant (the WS server is HA-compatible if that's ever wanted)
