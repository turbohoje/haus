#!/usr/bin/env python3
"""Fetch METARs for the watched airports and write the snap_metar.json sidecar.

Unlike snap_wx.json and snap_cal.json, this data is not on the TV — nothing in
ffmpeg/ produces or consumes it — so the fetcher lives here next to the
publisher rather than being a by-product of building an overlay.

Source is the Aviation Weather Center's free API (no key, no registration).
It computes fltCat server-side, which is why this script does not have to parse
ceilings and visibility out of the raw METAR to decide VFR vs IFR.

Run from cron every 10 minutes. METARs are issued hourly around :55 with SPECIs
in between when conditions change, and the endpoint sets cache-control
max-age=60, so polling harder buys nothing.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

WD = os.path.dirname(os.path.abspath(__file__))
SNAP_FILE = os.path.join(WD, 'snap_metar.json')

# Order is preserved into the payload, so the watch can draw rows without
# sorting. KLMO (the local field) first.
STATIONS = ['KLMO', 'KTEX']

URL = ('https://aviationweather.gov/api/data/metar'
       '?ids={ids}&format=json')
TIMEOUT = 20

# fltCat is one of VFR / MVFR / IFR / LIFR. Collapsed to two states here:
# anything that is not plain VFR reads as IFR.
VFR = 'VFR'
IFR = 'IFR'


def fetch(stations):
    """Returns the decoded array, or raises.

    The API answers 204 with an empty body when it recognises none of the ids,
    which json.loads would choke on, so that case becomes an empty list.
    """
    request = urllib.request.Request(
        URL.format(ids=','.join(stations)),
        headers={'User-Agent': 'haus-tvsnap (github.com/turbohoje/haus)'},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read()
    if not body.strip():
        return []
    return json.loads(body)


def station_row(ob):
    """One station's compact record, or None if it carries nothing useful.

    Missing values are omitted rather than sent as a sentinel, the same rule
    snap_wx.json uses for a sensor that did not report.
    """
    row = {'id': ob['icaoId']}

    cat = ob.get('fltCat')
    if cat:
        row['cat'] = VFR if cat == VFR else IFR

    # wdir is an int in degrees, or the string 'VRB' when the wind is variable.
    # That mixed type is passed through as-is because it is what the METAR says;
    # the watch has to type-check it. See watch/README.md.
    wdir = ob.get('wdir')
    if wdir is not None:
        row['dir'] = wdir

    wspd = ob.get('wspd')
    if wspd is not None:
        row['spd'] = wspd

    # wgst is absent entirely when the wind is not gusting, not null.
    wgst = ob.get('wgst')
    if wgst is not None:
        row['gst'] = wgst

    obs = ob.get('obsTime')
    if obs is not None:
        row['obs'] = obs

    # An id on its own is not worth a row.
    return row if len(row) > 1 else None


def build(observations):
    """Emit in STATIONS order, skipping any station the API did not return.

    An unknown or offline station is silently dropped from the response array
    rather than reported as an error, so a short list is normal, not a failure.
    """
    by_id = {ob.get('icaoId'): ob for ob in observations if ob.get('icaoId')}
    rows = []
    for station in STATIONS:
        ob = by_id.get(station)
        if ob is None:
            print(f'{station}: no observation returned', file=sys.stderr)
            continue
        row = station_row(ob)
        if row is not None:
            rows.append(row)
    return rows


def write_atomic(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(obj, fh, separators=(',', ':'))
    os.replace(tmp, path)


def main():
    try:
        observations = fetch(STATIONS)
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Sticky on failure, same as the overlays: leaving the previous sidecar
        # in place is better than blanking it, and metar_ts tells the watch how
        # old it has become.
        sys.exit(f'metar fetch failed, keeping stale sidecar: {e}')

    rows = build(observations)
    if not rows:
        sys.exit('no usable observations, keeping stale sidecar')

    write_atomic(SNAP_FILE, {'ts': int(time.time()), 'metar': rows})
    print(f'wrote {len(rows)} station(s): '
          + ', '.join(r['id'] for r in rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
