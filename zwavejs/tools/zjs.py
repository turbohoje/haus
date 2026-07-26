#!/usr/bin/env python3
"""Minimal zwave-js-server WS client for driving inclusion/exclusion.
Raw JSON protocol over aiohttp (no pydantic). Subcommands: info | exclude | include.
Prints grep-able status markers. For include, S2 classes that need a DSK PIN are
skipped by default (fine for sensors); if the device forces a PIN it writes NEED_PIN
and polls PIN_FILE.
"""
import asyncio, aiohttp, json, sys, time, itertools, os

URL = "ws://127.0.0.1:3001"
PIN_FILE = "/tmp/claude-1000/-home-turbohoje-haus/e8824090-23d7-4397-9d2d-773ce4084d29/scratchpad/pin.txt"
_id = itertools.count(1)
def mid(): return str(next(_id))

# zwave-js SecurityClass ints; 1 (S2_Authenticated) & 2 (S2_AccessControl) need a PIN
NO_PIN_CLASSES = {0, 7}  # S2_Unauthenticated, S0_Legacy

def out(*a):
    print(*a, flush=True)

async def send(ws, obj):
    await ws.send_str(json.dumps(obj))

async def handshake(ws):
    ver = None
    while ver is None:
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            d = json.loads(msg.data)
            if d.get("type") == "version":
                ver = d
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise RuntimeError("socket closed during handshake")
    schema = ver.get("maxSchemaVersion", 0)
    await send(ws, {"messageId": mid(), "command": "set_api_schema", "schemaVersion": schema})
    sl = mid()
    await send(ws, {"messageId": sl, "command": "start_listening"})
    state = None
    while state is None:
        msg = await ws.receive()
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        d = json.loads(msg.data)
        if d.get("type") == "result" and d.get("messageId") == sl:
            if not d.get("success"):
                raise RuntimeError("start_listening failed: %r" % d)
            state = d["result"]["state"]
    return ver, state

async def recv(ws, deadline):
    remaining = deadline - time.time()
    if remaining <= 0:
        return None
    try:
        msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
    except asyncio.TimeoutError:
        return None
    if msg.type != aiohttp.WSMsgType.TEXT:
        return None
    return json.loads(msg.data)

async def cmd_info(ws):
    ver, state = await handshake(ws)
    ctrl = state["controller"]
    nodes = sorted(n["nodeId"] for n in state["nodes"])
    out("SCHEMA", ver.get("maxSchemaVersion"), "server", ver.get("serverVersion"), "driver", ver.get("driverVersion"))
    out("HOME_ID", ctrl.get("homeId"), "ownNodeId", ctrl.get("ownNodeId"))
    out("NODES", nodes)
    out("DONE")

async def cmd_exclude(ws, timeout):
    ver, state = await handshake(ws)
    before = sorted(n["nodeId"] for n in state["nodes"])
    out("BEFORE_NODES", before)
    r = mid(); await send(ws, {"messageId": r, "command": "controller.begin_exclusion"})
    deadline = time.time() + timeout
    removed = None
    while time.time() < deadline and removed is None:
        d = await recv(ws, deadline)
        if d is None:
            continue
        if d.get("type") == "result" and d.get("messageId") == r:
            out("EXCLUSION_STARTED", "success=%s" % d.get("success"), d.get("errorCode", ""))
        if d.get("type") == "event":
            ev = d["event"]
            out("EVENT", ev.get("source"), ev.get("event"))
            if ev.get("event") == "node removed":
                removed = ev["node"]["nodeId"]
    if removed is not None:
        out("NODE_REMOVED", removed)
    else:
        out("EXCLUDE_TIMEOUT")
    await send(ws, {"messageId": mid(), "command": "controller.stop_exclusion"})
    out("DONE")

async def cmd_include(ws, timeout, strategy=0):
    ver, state = await handshake(ws)
    before = set(n["nodeId"] for n in state["nodes"])
    out("BEFORE_NODES", sorted(before), "strategy", strategy)
    # defensively clear any lingering exclusion/inclusion from a prior session
    await send(ws, {"messageId": mid(), "command": "controller.stop_exclusion"})
    await send(ws, {"messageId": mid(), "command": "controller.stop_inclusion"})
    await asyncio.sleep(1)
    r = mid(); await send(ws, {"messageId": r, "command": "controller.begin_inclusion", "options": {"strategy": strategy}})
    deadline = time.time() + timeout
    added = None
    interview_done = False
    grace_until = None
    while time.time() < deadline:
        d = await recv(ws, deadline)
        if d is None:
            if added is not None and grace_until and time.time() > grace_until:
                break
            continue
        if d.get("type") == "result" and d.get("messageId") == r:
            out("INCLUSION_STARTED", "success=%s" % d.get("success"), d.get("errorCode", ""))
        if d.get("type") != "event":
            continue
        ev = d["event"]; name = ev.get("event")
        out("EVENT", ev.get("source"), name)
        if name == "grant security classes":
            requested = ev.get("requested", {}).get("securityClasses", [])
            grant = [c for c in requested if c in NO_PIN_CLASSES]
            out("GRANT_REQUESTED", requested, "GRANTING", grant)
            await send(ws, {"messageId": mid(), "command": "controller.grant_security_classes",
                            "inclusionGrant": {"securityClasses": grant, "clientSideAuth": False}})
        elif name == "validate dsk and enter pin":
            dsk = ev.get("dsk")
            out("NEED_PIN", dsk)
            pin = None
            while pin is None and time.time() < deadline:
                if os.path.exists(PIN_FILE):
                    pin = open(PIN_FILE).read().strip()
                    os.remove(PIN_FILE)
                else:
                    await asyncio.sleep(1)
            if pin:
                await send(ws, {"messageId": mid(), "command": "controller.validate_dsk_and_enter_pin", "pin": pin})
                out("PIN_SUBMITTED")
        elif name == "node added":
            node = ev["node"]; added = node["nodeId"]
            out("NODE_ADDED", added, "lowSecurity=%s" % node.get("isSecure"),
                "highestSecurityClass=%s" % node.get("highestSecurityClass"))
            grace_until = time.time() + 45  # let interview run a bit
        elif name == "interview completed" and ev.get("nodeId") == added:
            interview_done = True
            out("INTERVIEW_COMPLETED", added)
            break
    if added is None:
        out("INCLUDE_TIMEOUT")
    else:
        out("RESULT_NODE", added, "interview_done=%s" % interview_done)
    await send(ws, {"messageId": mid(), "command": "controller.stop_inclusion"})
    out("DONE")

async def cmd_watch(ws, node_id, timeout):
    ver, state = await handshake(ws)
    n = next((x for x in state["nodes"] if x["nodeId"] == node_id), None)
    out("WATCH node", node_id, "status0", (n or {}).get("status"), "ready", (n or {}).get("ready"),
        "stage", (n or {}).get("interviewStage"), "values", len(((n or {}).get("values")) or []))
    # ask zwave-js to (re)interview this node; it will run when the node next wakes
    await send(ws, {"messageId": mid(), "command": "node.refresh_info", "nodeId": node_id})
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = await recv(ws, deadline)
        if d is None or d.get("type") != "event":
            continue
        ev = d["event"]
        if ev.get("nodeId") == node_id or (ev.get("node") or {}).get("nodeId") == node_id:
            out("EVENT", ev.get("source"), ev.get("event"), ev.get("args") or "")
            if ev.get("event") == "interview completed":
                out("INTERVIEW_COMPLETED", node_id); break
            if ev.get("event") == "ready":
                out("READY", node_id)
    out("DONE")

async def cmd_remove_failed(ws, node_id):
    ver, state = await handshake(ws)
    present = [n["nodeId"] for n in state["nodes"]]
    out("NODES_BEFORE", sorted(present))
    if node_id not in present:
        out("ALREADY_ABSENT", node_id); out("DONE"); return
    r = mid()
    await send(ws, {"messageId": r, "command": "controller.remove_failed_node", "nodeId": node_id})
    deadline = time.time() + 30
    while time.time() < deadline:
        d = await recv(ws, deadline)
        if d is None:
            continue
        if d.get("type") == "result" and d.get("messageId") == r:
            out("REMOVE_RESULT", "success=%s" % d.get("success"), d.get("errorCode", ""))
            break
        if d.get("type") == "event" and d["event"].get("event") == "node removed":
            out("NODE_REMOVED", d["event"]["node"]["nodeId"])
    out("DONE")

async def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "info"
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL, heartbeat=20) as ws:
            if action == "info":
                await cmd_info(ws)
            elif action == "exclude":
                await cmd_exclude(ws, timeout)
            elif action == "include":
                strat = int(sys.argv[3]) if len(sys.argv) > 3 else 0
                await cmd_include(ws, timeout, strat)
            elif action == "watch":
                await cmd_watch(ws, int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 180)
            elif action == "remove_failed":
                await cmd_remove_failed(ws, int(sys.argv[2]))
            else:
                out("unknown action", action)

asyncio.run(main())
