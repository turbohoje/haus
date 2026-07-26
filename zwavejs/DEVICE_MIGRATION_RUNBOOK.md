# Device Migration Runbook — Vera → zwave-js (collaborative)

**Status:** not started. This is a plan to pick up later. Nothing here has been run.
**Companion docs:** [CLAUDE.md](CLAUDE.md) (setup/spec) · [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) (device inventory).

The unit of work is **one device**. The per-device loop below is repeatable; do it as many
times per session as you like.

---

## Who does what

| You (physical / in the room) | Me / Claude (software) |
|---|---|
| Trigger each device's **exclude** and **include** action (tap pattern, button, air-gap). | Put zwave-js into exclude/include mode (WS script) **or** tell you the exact UI button. |
| Be **near the controller** for locks (secure inclusion). | Tail the driver logs live; read back the new **node id**, endpoints, S2 result, interview status. |
| Decide **S2 security grant** when the UI prompts. | Verify the node responds (read state / test on-off). |
| Access hardwired switches / flip breakers as needed. | Record the node in `hausphone/app/devices/zwave.py` `DEVICES` + tick the checklist. |
| (optional) Name/locate the node in the zwave-js UI. | Clean up the dead device on Vera; do the final `main.py` cutover. |

I **cannot** press the physical pairing action on a device — that always has to be you at the
hardware. Everything else I can drive or observe.

---

## Why this is safe / reversible
- **Exclusion is generic.** A controller in exclude mode resets *any* device, regardless of which
  hub it's paired to. So we exclude with **zwave-js**, not Vera — no dependence on Vera's remove
  wizard.
- **Two controllers coexist.** Vera and zwave-js are separate networks (different home IDs). A
  device lives in exactly one network at a time; the rest keep working on Vera meanwhile.
- **Reversible.** If an include fails or misbehaves, exclude it from zwave-js and re-include it
  into Vera to restore control. Nothing is destructive until you decommission the Vera at the end.
- **Not usable until interviewed.** After inclusion the node runs an interview; wait for
  "interview completed" before trusting it. I watch for this.

---

## One-time prerequisites (before the first device)
1. zwave-js-ui running and driver shows **"controller ready"** (`docker logs zwave-js-ui`).
2. **Choose the control path:**
   - **UI path (zero setup):** you click *Manage Nodes → Include/Exclude* in the `:8091` UI; I
     just watch logs and capture ids. Works today.
   - **Claude-driven path:** enable the **WS Server** (Settings → Home Assistant, port 3000 →
     host `:3001`). Then I run a small `zwave-js-server-python` helper that issues
     `begin_inclusion` / `begin_exclusion` and prints the joined node. One-time setup; smoother
     afterward.
3. Have [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) open to pick devices and jot node ids.

---

## Per-device loop
> Ping me with the device name to start; I'll narrate each step and say "go" when it's your turn.

0. **(me)** Confirm the driver is ready and no include/exclude is already active.
1. **(me)** Start **EXCLUDE** on zwave-js → I say **go**.
2. **(you)** Trigger the device's **exclude** action (usually the same tap pattern as inclusion —
   I'll look up the exact sequence for that model).
3. **(me)** Watch logs → confirm the device reset / "node removed". If nothing in ~30s, we retry.
4. **(me)** Start **INCLUDE** (S2 default) → I say **go**.
5. **(you)** Trigger the device's **include** action; pick the S2 grant if prompted.
6. **(me)** Capture the new **node id**, endpoints, and security result; wait for
   **interview completed**.
7. **(me)** Verify — read `currentValue` and/or test an on/off.
8. **(me)** Record — add/update the entry in `zwave.py` `DEVICES` (node_id, endpoint, label,
   `auto_off_minutes` where it applies) and tick the box in the checklist with the new id.
9. **(you, optional)** Name + assign a room to the node in the zwave-js UI.
10. **(me)** Vera cleanup — delete the now-dead device entry so Vera stays tidy (via the Vera UI
    trash, or I script the Vera API; I'll confirm the exact call at run time).

---

## Multi-channel devices (important)
The **Aeotec ZW140 / ZW139** dual relays — attic fan, both fireplaces, master reading lights —
come in as **one node with two endpoints** (endpoint 1 and 2), *not* two nodes. So in `zwave.py`
both app keys point at the **same `node_id`** with different `endpoint`:

```python
"attic1": {"node_id": <NEW>, "endpoint": 1, "label": "Attic1"},
"attic2": {"node_id": <NEW>, "endpoint": 2, "label": "Attic2"},
```

Include the physical node **once**; I map both keys to its endpoints.

---

## App cutover strategy (the 8 hausphone devices)
A migrated app-device stops responding in the PWA (still pointed at Vera) until we flip the
backend. Two ways:

- **(recommended) Batch + flip.** Migrate all 8 app devices in one session, then change
  `main.py` to `from app.devices import zwave as vera`, add `await vera.connect()` at startup, and
  rebuild the container. One clean switch, no hybrid code (YAGNI).
- **(only if needed) Hybrid.** I add a temporary shim so the app reads some keys from Vera and
  some from zwave-js during a phased migration. More code + more ways to break — avoid unless you
  want to spread the 8 over many sessions.

Non-app devices (sensors, locks, repeaters, scene remotes) can be migrated **anytime** with zero
impact on the PWA.

---

## Recommended order
1. **Pilot (zero app risk):** a non-app, non-secure, single-endpoint device — e.g. a **range
   extender** (ZW117 #37 or Aeon DSD37 #26). Learn the mechanics before anything critical.
2. **Simple app switches:** Water Pump (`ld_floor`), then Garage opener (`garage` — test the
   relay carefully).
3. **Multi-channel app switches:** Attic Fan (`attic1/2`), Living Fireplace (`l_fire`), Master
   Fireplace (`m_fire`), Master Reading Lights (`light_west/east`).  ← after this, do the cutover.
4. **Sensors + remaining repeaters** (Aeotec ZW100 multisensors, Zooz motion).
5. **Locks LAST** — 3× Schlage BE469NX. These are **S0** locks (confirmed: Security CC `0x98`, no
   S2 `0x9F`), so include with `zjs.py include <secs> 3` (Security_S0) — **no DSK PIN**. S0 is
   range-sensitive; doing locks last means the repeaters are already meshed to carry it (a fresh
   network has none). User codes live in the lock, so they survive re-pairing.

---

## Gotchas
- **Inclusion trigger varies by model** — I'll look up the exact tap/button sequence per device
  before each one (e.g. Aeotec action button vs Jasco 2× paddle tap).
- **Security policy:** everything is fine **insecure EXCEPT door locks**. The BE469NX locks use
  **S0** (`strategy 3`, no PIN). A lock that ends up insecure is useless (no lock/unlock) — redo it.
- **Re-include repeaters too** or the mesh gets weak once Vera is gone.
- **Locks:** S0 is range-sensitive — needs a solid mesh (do them last) or the stick near the lock,
  else the S0 bootstrap fails and it falls back to insecure.
- **Ghosts:** the `_`-prefixed Vera entries (checklist "(no room)") are shadow devices — don't try
  to migrate them.

---

## Tooling — the Claude-driven path (validated 2026-07-25, migration #1)
- **WS server is live:** container `:3001` → host `:3001` (compose fixed to `3001:3001`). Clients
  connect to `ws://127.0.0.1:3001`. (zwave-js-ui `serverPort` was set to 3001, not the default 3000.)
- **Helper:** `zwavejs/tools/zjs.py` — a raw aiohttp WebSocket client (no pydantic). Subcommands:
  - `info` — controller + node list
  - `exclude <secs>` — general-exclusion window
  - `include <secs> [strategy]` — inclusion; **strategy 0 = Default/S2, 2 = Insecure**
  - `watch <nodeId> <secs>` — queue a re-interview and watch a node
  - `remove_failed <nodeId>` — drop a dead/failed node
- **Env:** needs a venv with **aiohttp** on this box's Python 3.10:
  `python3 -m venv venv && venv/bin/pip install aiohttp`.
  **Do NOT** `pip install zwave-js-server-python` here — it breaks on py3.10 (pydantic/`TypedDict`),
  which is why the helper speaks the raw JSON protocol instead.

## Lessons from migration #1 (ZSE18 "Motion Sensor" → node 2)
- **Battery/sleeping sensors: include INSECURE (`strategy 2`).** The default S2 attempt failed on
  this sleeping sensor (came in at `highestSecurityClass -1`, interview never ran, node went dead).
  Insecure completed cleanly on the first try. S2 adds little on a motion sensor anyway. (Door
  locks are the one exception — the BE469NX needs **S0** via `strategy 3`, no PIN; everything
  non-lock is fine insecure per project rule.)
- **Keep the sensor awake through the interview.** Right after `NODE_ADDED`, single-press the
  Z-Wave button a few times / trigger motion so zwave-js drains the whole interview in one wake.
  If it sleeps mid-interview it half-completes and can be marked **dead**.
- **Factory reset is the reliable "get it off Vera" for a stubborn/sleeping device.** General
  exclusion didn't cleanly catch this Vera-paired sensor. Hold the Z-Wave button ~10 s (LED blinks
  then off) to wipe it, then include fresh.
- **Recover a bad inclusion:** `zjs.py remove_failed <nodeId>` → factory-reset the device →
  re-include insecure.
- **Vera cleanup:** `?id=device&action=delete&device=N` **then** `?id=reload` — the delete only
  persists (device drops off the list) after a Luup reload.
- **Windows time out (~3–5 min):** if the device starts its blue "hunting" blink *after* the window
  closed, just reopen the window.
- **Locks need the mesh FIRST (confirmed 2026-07-25, Front Door BE469NX).** Tried to include the
  lock at the front door with only the controller + one sleeping sensor on zwave-js — the stick
  **heard nothing** (no "node found"), and the lock stayed on Vera (nothing lost). A fresh network
  has no repeaters, so a distant lock is simply unreachable. **Migrate the mains-powered switches/
  repeaters between the NUC and the door first, working outward from the stick**, then the lock
  includes on the first try. This lock's relays were Vera nodes 5,14,15,19,23,35,42,46,48
  (DSD37 #26, ZW117 #37, ZW140 switches #38/67/85, ZW139 #142, Jasco #192, ZW100 sensors).
  - **Mesh-dependency check:** the Front Door lock's Vera `Neighbors` list did NOT include node 1
    (the controller) — it only reaches Vera *through* repeaters. If a device's neighbor list omits
    the controller, it definitely can't join a fresh (mesh-less) zwave-js network.
  - **"Delete device" in Vera ≠ exclusion.** Deleting the Vera UI entry does not reset the lock; it
    stayed bonded and kept responding to Vera polls (`CommFailure 0`). To verify a device actually
    left, force a Vera poll (`action=Poll` on serviceId HaDevice1) — if it still answers, it's still
    bonded. A real exclusion (or factory reset) is required before it can join zwave-js.

## How to start next time
Just send me something like:

> "zwave-js is up — let's migrate the **Living Room fireplace**."

and I'll run the per-device loop. The WS server + `tools/zjs.py` are already wired, so I can drive
include/exclude by API and just prompt you for the button presses (as we did for the ZSE18).
