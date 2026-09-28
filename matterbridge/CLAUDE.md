# matterbridge — Design Context

## Purpose
Exposes a subset of the hausphone PWA's Z-Wave switches to **Google Home** as Matter devices,
so they can be voice-controlled and put in Google routines. Five devices today: Attic Fan 1,
Attic Fan 2, Lady Den Floor, Living Room Fireplace, Master Fireplace.

Nothing else in the house is bridged. Locks, the garage door and the Big Ass Fan stay
hausphone-only on purpose — see *Deliberately not bridged* below.

---

## Architecture

```
Google Home  ──Matter/mDNS──>  matterbridge container  ──HTTPS/WSS──>  hausphone  ──>  zwave-js
   (app,          (:5540,           (this stack)          (:3000)       (:3000)      (:3001)
    speakers)      IPv6)
```

**This plugin never talks to zwave-js.** It drives `POST /api/zwave/{key}/power`, the same route
the PWA uses. That is the whole point of the design:

- A fireplace turned on by Google still gets hausphone's **90-minute auto-off**.
- LD Floor still honours its **warm window** and **occupancy** automation.
- The attic delay-on / off-timer logic keeps working.
- hausphone stays the single writer, so there is no second opinion about device state.

State flows back over hausphone's existing `/ws` socket. Z-Wave state there is push-based, so a
switch thrown at the **master remote** (node 13 WallMote) or by a scene reaches Google Home
without anyone polling. hausphone also re-broadcasts full state every 60 s on its own poll loop,
which doubles as this plugin's safety net against a dropped message.

### Which devices get bridged is decided in hausphone
`DEVICES` in `hausphone/app/devices/zwave.py` carries an optional `matter` block:

```python
"attic1": {"node_id": 16, "endpoint": 1, "label": "Attic1",
           "matter": {"name": "Attic Fan 1", "type": "outlet"}},
```

`GET /api/matter/devices` serves those as a manifest (`key`, `name`, `type`, `on`). The plugin
reads it once at startup and builds one bridged endpoint per entry. **To bridge another device,
add a `matter` block there and restart this container** — no change in this directory.

`name` is what Google Home shows on first commissioning; renaming it there afterwards sticks,
because the endpoint is keyed on the serial (`haus-<key>`), not the name.

---

## Device types — why everything is an "outlet"

All five are morally wall switches, and they are bridged as Matter **On/Off Plug-in Unit
(0x010A)**.

Matter's actual **On/Off Switch (0x0103) is a _client_ device type**: it carries OnOff as a
*client* cluster and binds to other nodes, i.e. it is the thing that controls a light, not a
thing a controller can control. Google Home will happily commission one and then offer no way to
turn it on — the Binding cluster it would need is not exposed to users. So "bridge it as a
switch" is not implementable as stated; the plug-in unit is the simplest server type Google both
renders and controls.

The alternative is `"type": "light"` (**On/Off Light, 0x0100**) — same on/off behaviour, but
Google files it under lights, so it answers to "turn off the lights" as a group. Use that for
anything that should sweep with the lights; the fireplaces and attic fans deliberately should not.

`DEVICE_TYPES` in `plugin/index.js` is the full set of types the bridge knows how to build.

---

## Deployment

Runs on the same NUC (`10.22.14.2`) as hausphone and zwave-js.

```bash
docker compose up -d --build
docker logs -f matterbridge         # commissioning code + plugin startup
docker compose down
```

Ports on the host network: **8283** frontend, **5540** Matter. (hausphone holds 3000,
zwave-js-server 3001, zwave-js-ui 8091.)

### Why `network_mode: host`
Matter discovery is mDNS over IPv6 link-local. Docker's bridge network does not carry it, and a
commissioner that cannot see the advertisement cannot pair. Same reason hausphone runs on the
host network.

### Commissioning into Google Home
1. `docker logs matterbridge` — the QR code and 11-digit manual pairing code are printed at
   startup, and are also on the frontend at `http://10.22.14.2:8283`.
2. Google Home app → **+ Add** → **Matter-enabled device** → scan the QR.
3. **A Google hub is required** (Nest speaker/display or Google TV). Google Home cannot
   commission Matter devices without one on the network.
4. All five devices appear at once — the bridge itself shows up as an inert "Control Bridge".
   Assign rooms in the Home app.

The Dockerfile's CMD passes `--novirtual`. Without it matterbridge adds its own "Restart
Matterbridge" / "Update Matterbridge" on/off endpoints to the bridge, and Google Home would list
them as two more plugs — one voice command away from restarting the bridge.

Commissioning state lives in the `matterbridge-storage` volume. Losing it means re-pairing in
Google Home and every device coming back as new (rooms and routines lost), which is why it is a
named volume and not a bind mount into the repo.

---

## Container layout

The plugin is copied into **global** node_modules by the Dockerfile, not bind-mounted. Two reasons:

- `import ... from 'matterbridge'` only resolves if the plugin sits next to matterbridge in the
  global lib dir — Node walks up from the plugin directory, and the global dir is not on the
  path of anything mounted elsewhere.
- Matterbridge treats a plugin outside the global dir as "local" and runs `npm link matterbridge`
  in it on every boot. Works, but it writes into the source tree.

It is copied and then `npm install`ed in place rather than `npm install -g ./plugin` — npm 7+
**symlinks** a local directory install and never installs its dependencies, which would leave `ws`
missing at runtime.

`entrypoint.sh` runs `matterbridge -add matterbridge-haus` before starting. Registration writes
to the storage volume rather than the image, so it has to happen at runtime; `-add` is idempotent
and logs "already registered" on every boot after the first.

The plugin is **plain ESM, no TypeScript**, so the image needs no build step. Its one dependency
is `ws` (for `rejectUnauthorized: false` against hausphone's self-signed cert — Node's global
`WebSocket` has no way to pass that).

---

## Gotchas

- **Device-type constants get renamed.** Matterbridge 3.0 exported `onOffOutlet`; 3.10 exports
  `onOffPlugInUnit` for the same Matter code (0x010A). The image floats on
  `luligu/matterbridge:latest`, so `deviceType()` in `plugin/index.js` resolves whichever name
  the installed build has rather than pinning a spelling. Add new aliases there, not a version pin.
- **Startup race.** Both containers come up together and hausphone needs ~20 s to connect its
  device backends, so the manifest fetch always loses the race at least once on a cold boot. The
  plugin retries every 5 s for 2 minutes. If hausphone is genuinely down it gives up and the
  plugin reports an error — `docker compose restart matterbridge` recovers.
- **TLS is not verified.** hausphone serves a self-signed cert and has no auth; it is a LAN-only
  service reached over loopback here. The exemption is scoped to the plugin's own requests
  (`tlsInsecure` in the plugin config), not the whole Node process, so matterbridge still
  verifies certs when it talks to npm.
- **Command failures are invisible to Google.** Matter has no "that didn't work" response once
  the handler has run, so a failed write briefly leaves the endpoint showing a state hausphone
  never reached. The next `/ws` broadcast corrects it.
- **Plugin config lives in the storage volume**, at `/root/.matterbridge/matterbridge-haus.config.json`.
  `plugin/matterbridge-haus.config.json` is only the seed for a first run — editing it later does
  nothing. Change the live config from the frontend, or delete the file in the volume.

---

## Deliberately not bridged

- **Door locks** — Matter door locks are commissionable, but a voice-openable deadbolt is a
  different risk posture than a fireplace. Not without a deliberate decision.
- **Garage** — hausphone gives it slide-to-activate specifically so it cannot be pocket-dialled,
  plus an auto-close watcher. A Google voice command routes around both.
- **M.Fan / M.Light** — the Big Ass Fan already has its own app and cloud integration.
- **Water Feature** — WeMo, already has its own Google integration if wanted.

---

## File Structure
```
matterbridge/
├── CLAUDE.md
├── Dockerfile              ← FROM luligu/matterbridge:latest + global plugin install
├── docker-compose.yml
├── entrypoint.sh           ← registers the plugin, then execs matterbridge
└── plugin/
    ├── package.json                      ← name must start with "matterbridge-"; type: module
    ├── index.js                          ← the whole plugin (dynamic platform)
    ├── matterbridge-haus.config.json     ← seed config (first run only)
    └── matterbridge-haus.schema.json     ← drives the frontend's config form
```

Matterbridge refuses to load a plugin that declares `matterbridge`, `@matter*` or `@project-chip`
as a dependency — it would instantiate a second matter.js. `package.json` lists only `ws`.
