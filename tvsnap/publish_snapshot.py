#!/usr/bin/env python3
"""Merge the ffmpeg JSON sidecars and PUT them to the Cloudflare worker.

Run from cron a minute after fetch_wx.py / fetch_cal.py, which write
ffmpeg/snap_wx.json and ffmpeg/snap_cal.json as a by-product of building the
TV overlays. Those two cannot publish directly: they run independently and
would each clobber the other's half of a single R2 object.

Both sidecars are sticky — a failed fetch leaves the previous file in place —
so their own timestamps are carried through as wx_ts / cal_ts. Without those a
stale half looks identical to a fresh one on the watch.

Config comes from .env next to this script (gitignored):

    WORKER_URL=https://haus-tvsnap.<subdomain>.workers.dev
    API_KEY=<shared key>
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

WD = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(os.path.dirname(WD), 'ffmpeg')

WX_FILE = os.path.join(FFMPEG_DIR, 'snap_wx.json')
CAL_FILE = os.path.join(FFMPEG_DIR, 'snap_cal.json')

TIMEOUT = 20
STALE_SECONDS = 3600  # sidecars refresh every 5 min; an hour old is a real fault


def load_env(path):
    """Minimal KEY=value reader. Avoids a dependency for two settings.

    Returns None when there is no .env at all, which the caller treats as
    "not deployed yet" rather than an error.
    """
    out = {}
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError as e:
        sys.exit(f'cannot read {path}: {e}')
    return out


def load_sidecar(path):
    """Missing or corrupt returns None — a half snapshot still beats none."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        print(f'skipping {os.path.basename(path)}: {e}', file=sys.stderr)
        return None


def build(wx, cal):
    now = int(time.time())
    snap = {'ts': now}

    if wx:
        snap['wx_ts'] = wx.get('ts')
        for key in ('temp_c', 'aqi', 'hourly', 'week'):
            if key in wx:
                snap[key] = wx[key]

    if cal:
        snap['cal_ts'] = cal.get('ts')
        snap['justin'] = cal.get('justin', [])
        snap['both'] = cal.get('both', [])

    for label, ts in (('wx', snap.get('wx_ts')), ('cal', snap.get('cal_ts'))):
        if ts and now - ts > STALE_SECONDS:
            print(f'warning: {label} data is {(now - ts) // 60} min old',
                  file=sys.stderr)

    return snap


def publish(url, api_key, snap):
    body = json.dumps(snap, separators=(',', ':')).encode()
    request = urllib.request.Request(
        url.rstrip('/') + '/snapshot',
        data=body,
        method='PUT',
        headers={'Content-Type': 'application/json', 'X-API-Key': api_key},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return len(body), response.read().decode()


def main():
    env = load_env(os.path.join(WD, '.env'))
    url = env.get('WORKER_URL') if env else None
    api_key = env.get('API_KEY') if env else None

    if not url and not api_key:
        # deploy.sh has not been run yet. The cron entry is installed before the
        # worker exists, so staying quiet here is the difference between a clean
        # inbox and a failure mail every 5 minutes until someone deploys.
        return 0
    if not url or not api_key:
        # Half-configured is a real mistake, unlike not-configured-at-all.
        sys.exit('WORKER_URL and API_KEY must both be set in .env')

    wx = load_sidecar(WX_FILE)
    cal = load_sidecar(CAL_FILE)
    if wx is None and cal is None:
        sys.exit('neither sidecar is readable; nothing to publish')

    try:
        size, reply = publish(url, api_key, build(wx, cal))
    except urllib.error.HTTPError as e:
        sys.exit(f'publish rejected: HTTP {e.code} {e.read().decode()[:200]}')
    except (urllib.error.URLError, OSError) as e:
        # cron retries in 5 minutes; the old snapshot stays up meanwhile.
        sys.exit(f'publish failed: {e}')

    print(f'published {size} bytes: {reply}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
