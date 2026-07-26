#!/usr/bin/env python3
"""zwq — tiny synchronous reader/writer for the zwave-js-server WebSocket.

Replaces the old Vera `data_request?id=variableget&DeviceNum=...` HTTP calls.
zwave-js-server is WebSocket-only, so each call opens a short-lived WS, pulls the
driver's already-cached node values from the `start_listening` state dump, and
returns the one you asked for. No polling round-trip — the driver keeps values live.

Vera DeviceNum -> zwave-js nodeId mapping lives in MIGRATION_CHECKLIST.md.

Convenience helpers (what the cron scripts actually need):
    temperature_c(node)   -> float | None   (Air temperature, always Celsius)
    humidity(node)        -> float | None
    switch_on(node)       -> bool  | None    (Binary Switch currentValue)
    set_switch(node, on)  -> bool            (Binary Switch targetValue; write)
    motion_tripped(node)  -> bool | None     (Notification Home Security motion)
    lock_status(node)     -> "Locked"|"Unlocked"|None (Door Lock currentMode)

Low-level:
    get_value(node, command_class, property, endpoint=0, property_key=None)
    set_value(node, command_class, property, value, endpoint=0)
"""
import asyncio, aiohttp, json, itertools, sys

URL = "ws://127.0.0.1:3001"
_ids = itertools.count(1)
def _mid(): return str(next(_ids))

# Command class numbers we use
CC_BINARY_SWITCH = 37   # 0x25
CC_BINARY_SENSOR = 48   # 0x30
CC_MULTILEVEL_SENSOR = 49  # 0x31
CC_DOOR_LOCK = 98       # 0x62
CC_NOTIFICATION = 113   # 0x71


async def _connect(session):
    ws = await session.ws_connect(URL, heartbeat=20)
    ver = None
    while ver is None:
        d = json.loads((await ws.receive()).data)
        if d.get("type") == "version":
            ver = d
    await ws.send_str(json.dumps({"messageId": _mid(), "command": "set_api_schema",
                                  "schemaVersion": ver["maxSchemaVersion"]}))
    sl = _mid()
    await ws.send_str(json.dumps({"messageId": sl, "command": "start_listening"}))
    state = None
    while state is None:
        d = json.loads((await ws.receive()).data)
        if d.get("type") == "result" and d.get("messageId") == sl:
            if not d.get("success"):
                raise RuntimeError("start_listening failed: %r" % d)
            state = d["result"]["state"]
    return ws, state


def _find(state, node, cc, prop, endpoint, pk):
    n = next((x for x in state["nodes"] if x["nodeId"] == node), None)
    if n is None:
        raise LookupError(f"node {node} not present on controller")
    for v in n.get("values", []):
        if (v.get("commandClass") == cc and v.get("property") == prop
                and (v.get("endpoint") or 0) == endpoint
                and v.get("propertyKey") == pk):
            return v
    return None


async def _get(node, cc, prop, endpoint, pk):
    async with aiohttp.ClientSession() as s:
        ws, state = await _connect(s)
        try:
            return _find(state, node, cc, prop, endpoint, pk)
        finally:
            await ws.close()


async def _set(node, cc, prop, value, endpoint):
    async with aiohttp.ClientSession() as s:
        ws, state = await _connect(s)
        try:
            r = _mid()
            await ws.send_str(json.dumps({
                "messageId": r, "command": "node.set_value", "nodeId": node,
                "valueId": {"commandClass": cc, "endpoint": endpoint, "property": prop},
                "value": value,
            }))
            while True:
                d = json.loads((await ws.receive()).data)
                if d.get("type") == "result" and d.get("messageId") == r:
                    return bool(d.get("success"))
        finally:
            await ws.close()


def get_value(node, command_class, property, endpoint=0, property_key=None):
    """Return the cached value (scalar), or None if the value isn't present."""
    v = asyncio.run(_get(node, command_class, property, endpoint, property_key))
    return None if v is None else v.get("value")


def set_value(node, command_class, property, value, endpoint=0):
    return asyncio.run(_set(node, command_class, property, value, endpoint))


# ---- conveniences --------------------------------------------------------

def temperature_c(node):
    """Air temperature in Celsius, converting from the device's reported unit."""
    v = asyncio.run(_get(node, CC_MULTILEVEL_SENSOR, "Air temperature", 0, None))
    if v is None or v.get("value") is None:
        return None
    val = float(v["value"])
    unit = ((v.get("metadata") or {}).get("unit") or "")
    if "F" in unit:            # e.g. "°F"
        return (val - 32) * 5.0 / 9.0
    return val


def humidity(node):
    return get_value(node, CC_MULTILEVEL_SENSOR, "Humidity")


def switch_on(node):
    v = get_value(node, CC_BINARY_SWITCH, "currentValue")
    return None if v is None else bool(v)


def set_switch(node, on):
    return set_value(node, CC_BINARY_SWITCH, "targetValue", bool(on))


def motion_tripped(node):
    """True if the sensor currently reports motion.
    Notification 'Home Security' / 'Motion sensor status' (0=idle, 8=motion)."""
    v = get_value(node, CC_NOTIFICATION, "Home Security",
                  property_key="Motion sensor status")
    if v is None:
        # ZW100 also exposes a plain Binary Sensor
        b = get_value(node, CC_BINARY_SENSOR, "Any")
        return None if b is None else bool(b)
    return v != 0


def lock_status(node):
    """'Locked' / 'Unlocked' / None. Door Lock currentMode: 255=secured, 0=unsecured."""
    v = get_value(node, CC_DOOR_LOCK, "currentMode")
    if v is None:
        return None
    return "Locked" if v == 255 else "Unlocked"


if __name__ == "__main__":
    # quick self-test / ad-hoc query:  zwq.py temp 21   |   zwq.py 21 49 "Air temperature"
    a = sys.argv[1:]
    if a and a[0] == "temp":
        for n in a[1:] or [3, 8, 9, 12, 21]:
            n = int(n)
            raw = asyncio.run(_get(n, CC_MULTILEVEL_SENSOR, "Air temperature", 0, None))
            rv = None if raw is None else raw.get("value")
            unit = None if raw is None else (raw.get("metadata") or {}).get("unit")
            print(f"node {n}: raw={rv}{unit or ''}  -> {temperature_c(n)}°C")
    elif len(a) >= 3:
        print(get_value(int(a[0]), int(a[1]), a[2],
                        int(a[3]) if len(a) > 3 else 0,
                        a[4] if len(a) > 4 else None))
    else:
        print(__doc__)
