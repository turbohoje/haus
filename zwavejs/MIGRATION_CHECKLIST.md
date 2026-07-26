# Vera → zwave-js Device Migration Checklist

Generated **2026-07-25** from Vera VeraPlus (Sercomm G450, fw 1.7.5186, 500-series Z-Wave) at http://10.22.14.4
Source: `/data_request?id=user_data`. **23 top-level Z-Wave nodes** (+ 36 multi-channel children) across 11 rooms.
**Node IDs mapped 2026-07-26** from live zwave-js state (server 3.8.0 / driver 15.23.5, home id 3855121425) — matched by model + the name/location you set in the UI.

**Status:** migration essentially **complete** — every switch/sensor is interviewed and `ready`. Remaining work:
1. **Z-Wave Extender/Repe (DSD37, Vera node 5)** — the one device still on Vera (a plug-in repeater near the front-door locks).
2. **The three Schlage deadbolts (nodes 4, 5, 19)** are included with S0 but show `ready=False` — interviews never finished (lock RF). Migrating the DSD37 as a bridge should let them complete.

**Per node:** exclude from Vera (or factory-reset the device) → include in zwave-js (*Manage nodes → Include*, S2; **locks = S0**) → record the new node id in `hausphone/app/devices/zwave.py` `DEVICES`.

**Legend:** `[x]` = migrated + interviewed (`ready`). `◐` = included but interview incomplete. `✓app[key]` = controlled by the hausphone PWA. Multi-channel children (`↳`) come across automatically when their parent node is included — **do not pair them separately**. `zjs node:N` is the id zwave-js assigned. Devices whose name starts with `_` are Vera-hidden/auxiliary (ghost/shadow) entries.

**Vera↔zwave-js node ids differ** — keep the Vera # and Vera node here; they're still useful for cross-referencing scenes, old configs, and Vera cleanup.

---

## Attic

- [x] **Attic Fan** — Vera #67 · node 19 · Aeotec ZW140 · On/Off Switch —  **zjs node:16** (`Fan` / Attic, ready)
    - ↳ #68 (endpoint, altid `e1`) — On/Off Switch · ✓app[attic1] → **node 16 · endpoint 1**
    - ↳ #69 (endpoint, altid `e2`) — On/Off Switch · ✓app[attic2] → **node 16 · endpoint 2**
    - ↳ #103 (endpoint, altid `e9`) — Generic IO → node 16 · endpoint 3 (unused)
- [x] **attic sensor** — Vera #119 · node 33 · zooZ ZSE40 · MotionSensor —  **zjs node:15** (`Attic Sensor` / Attic, ready)
    - ↳ #120 (endpoint, altid `m1`) — Temperature Sensor
    - ↳ #121 (endpoint, altid `m3`) — Light Sensor
    - ↳ #122 (endpoint, altid `m5`) — Humidity Sensor

## Basement Office

- [x] **Basement Sensor** — Vera #198 · node 48 · Aeotec ZW100 · Sensor —  **zjs node:21** (`Temp` / Basement, ready)
    - ↳ #240 (endpoint, altid `m1`) — Temperature Sensor
    - ↳ #241 (endpoint, altid `m3`) — Light Sensor
    - ↳ #242 (endpoint, altid `m5`) — Humidity Sensor
    - ↳ #243 (endpoint, altid `m27`) — GenericSensor

## Dining Room

- [ ] **Z-Wave Extender/Repe** — Vera #26 · node 5 · Aeon DSD37 · Generic IO —  **NOT MIGRATED — still on Vera (node 5).** The last device. Plug-in repeater; migrate it as the bridge for the front-door locks.

## Drawing Room

- [ ] ◐ **Front Door** 🔒 — Vera #24 · node 4 · Schlage BE469NX · Doorlock —  **zjs node:19** (`Front Door` / Drawing Room, S0, **ready=False — interview incomplete**). Vera still shows a stale node-4 ghost.

## Garage

- [ ] ◐ **Garage Lock** 🔒 — Vera #23 · node 3 · Schlage BE469NX · Doorlock —  **zjs node:5** (`Garage Lock` / Garage, S0, **ready=False — interview incomplete**)
- [x] **Garage Door Opener** — Vera #36 · node 13 · Linear/Nortek GD00Z · BinaryLight · ✓app[garage] —  **zjs node:6** (`Garage Door` / Garage, ready)

## Lady Den

- [x] **Water Pump** — Vera #192 · node 46 · GE/Jasco (Enbrighten ZW1002) · On/Off Switch · ✓app[ld_floor] —  **zjs node:24** (`Water Pump` / Lady Den, S2, ready)
- [x] **Lady Den Sensor** — Vera #215 · node 51 · Aeotec ZW100 · Sensor —  **zjs node:9** (`Temp` / Lady Den, ready)
    - ↳ #236 (endpoint, altid `m1`) — Temperature Sensor
    - ↳ #237 (endpoint, altid `m3`) — Light Sensor
    - ↳ #238 (endpoint, altid `m5`) — Humidity Sensor
    - ↳ #239 (endpoint, altid `m27`) — GenericSensor

## Living Room

- [ ] ◐ **Back Door** 🔒 — Vera #22 · node 2 · Schlage BE469NX · Doorlock —  **zjs node:4** (`Back Door` / Living Room, S0, **ready=False — interview incomplete**)
- [x] **Livingroom Fireplace** — Vera #142 · node 35 · Aeotec ZW139 · On/Off Switch · ✓app[l_fire] —  **zjs node:14** (`Fireplace` / Living Room, ready)
- [x] **Motion Sensor** — Vera #214 · node 50 · zooZ ZSE18 · MotionSensor —  **zjs node:2** (`Motion` / Drawing Room, insecure, ready). Vera entry deleted.
- [x] **Living Room** — Vera #245 · node 52 · Aeotec ZW100 · Sensor —  **zjs node:3** (`Living Room` / Living Room, ready)
    - ↳ #246 (endpoint, altid `m1`) — Temperature Sensor
    - ↳ #247 (endpoint, altid `m3`) — Light Sensor
    - ↳ #248 (endpoint, altid `m5`) — Humidity Sensor
    - ↳ #249 (endpoint, altid `m27`) — GenericSensor

## Master Bedroom

- [x] **Master Reading Light** — Vera #38 · node 15 · Aeotec ZW140 · On/Off Switch —  **zjs node:17** (`Reading Light` / Master, ready)
    - ↳ #39 (endpoint, altid `e1`) — On/Off Switch · ✓app[light_west] → **node 17 · endpoint 1**
    - ↳ #40 (endpoint, altid `e2`) — On/Off Switch · ✓app[light_east] → **node 17 · endpoint 2**
    - ↳ #66 (endpoint, altid `e9`) — Generic IO → node 17 · endpoint 3 (unused)
- [x] **Master Remote** — Vera #42 · node 16 · Aeotec ZW130 · SceneController —  **zjs node:13** (`Remote` / Master, 5 endpoints, ready)
    - ↳ #187–190 (endpoints `e1`–`e4`) — Generic IO → node 13 endpoints
- [x] **Master Fireplace** — Vera #85 · node 23 · Aeotec ZW140 · On/Off Switch · ✓app[m_fire] —  **zjs node:10** (`Fireplace` / Master, ready)
    - ↳ #86 (endpoint, altid `e1`) — On/Off Switch → node 10 · endpoint 1
    - ↳ #87 (endpoint, altid `e2`) — On/Off Switch → node 10 · endpoint 2
    - ↳ #105 (endpoint, altid `e9`) — Generic IO → node 10 · endpoint 3 (unused)
- [x] **Master Temp zw** — Vera #168 · node 42 · Aeotec ZW100 · Sensor —  **zjs node:12** (`Temp` / Master, ready)
    - ↳ #169–172, #244 (endpoints `m1`/`m3`/`m5`/`m27`/`m2`) — Temp/Light/Humidity/Generic/Sensor

## Patio

- [x] **Patio sensor 1** — Vera #81 · node 22 · zooZ ZSE40 · Sensor —  **zjs node:8** (`Temp` / Patio, ready)
    - ↳ #112 (endpoint, altid `m1`) — Temperature Sensor
    - ↳ #113 (endpoint, altid `m3`) — Light Sensor
    - ↳ #114 (endpoint, altid `m5`) — Humidity Sensor

## Upstairs Office

- [x] **Upstairs Repeater** — Vera #37 · node 14 · Aeotec ZW117 · Generic IO —  **zjs node:20** (Repeater Slave, unnamed, ready)

## (no room) — ghosts / shadow entries

- [ ] **_Scene Controller** — Vera #4 · node 1 · Scene Controller — Vera controller itself; not migrated. (zwave-js controller = the Zooz ZST39 stick, **node 1**.)
- [ ] **_Door Lock 4** — Vera #288 · node 56 · Doorlock — ghost; see note below.
- [ ] **_Door Lock** — Vera #291 · node 55 · Doorlock — ghost; see note below.
- [ ] **_Door Lock 7** — Vera #293 · node 54 · Doorlock — ghost; see note below.

> **Extra lock found on zwave-js:** **node 7 `Balcony Lock`** (Master, S0, ready) has no named
> counterpart in this checklist — it corresponds to one of the three `_Door Lock` ghosts above
> (Vera nodes 54/55/56), which were real but hidden/mislabeled on Vera. Confirm which physical
> lock it is when convenient.

---

## Priority — hausphone app devices (feature parity → `zwave.py` `DEVICES`)

| Vera # | key | name | zwave-js node · endpoint | type |
|---|---|---|---|---|
| 39 | `light_west` | Master Light West | **node 17 · ep 1** | On/Off Switch |
| 40 | `light_east` | Master Light East | **node 17 · ep 2** | On/Off Switch |
| 68 | `attic1` | Fan 1 | **node 16 · ep 1** | On/Off Switch |
| 69 | `attic2` | Fan 2 | **node 16 · ep 2** | On/Off Switch |
| 192 | `ld_floor` | Water Pump | **node 24** | On/Off Switch |
| 36 | `garage` | Garage Door Opener | **node 6** | BinaryLight |
| 142 | `l_fire` | Livingroom Fireplace | **node 14** | On/Off Switch |
| 85 | `m_fire` | Master Fireplace | **node 10** | On/Off Switch |

---

## Vera cleanup (after cutover)

Still lingering on Vera (`10.22.14.4`) as stale entries — delete via
`?id=device&action=delete&device=N` then `?id=reload`:

| Vera # | Vera node | name | why |
|---|---|---|---|
| 24 | 4 | Front Door | migrated to zjs node 19; stale ghost |
| 26 | 5 | Z-Wave Extender/Repe | **do NOT delete yet — still the live repeater to migrate** |
| 288 | 56 | _Door Lock 4 | ghost |
| 291 | 55 | _Door Lock | ghost |
| 293 | 54 | _Door Lock 7 | ghost |

---

## Not migrated (system / gateway)

- #1 ZWave — urn:schemas-micasaverde-com:device:ZWaveNetwork:1
- #2 Zigbee Network — urn:schemas-micasaverde-com:device:ZigbeeNetwork:1
- #3 Bluetooth Network — urn:schemas-micasaverde-com:device:BluetoothNetwork:1
- #80 UPnP Event Proxy — urn:schemas-futzle-com:device:UPnPProxy:1
- #104 Google — urn:schemas-upnp-org:device:GoogleHome:1
- #132 ecobee — urn:schemas-micasaverde-com:device:ecobee:2
