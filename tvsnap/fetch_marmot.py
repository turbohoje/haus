#!/usr/bin/env python3
"""Fetch the Tempest outside temperature and write the snap_marmot.json sidecar.

Like snap_metar.json and unlike snap_wx.json / snap_cal.json, this is not on the
TV, so the fetcher lives here next to the publisher rather than being a
by-product of building an overlay.

The reading comes back out of the metrics-server worker in ~/cf_metrics, which
~/cf_metrics/tempest/scrape.py already feeds every 300 s. Going through the
worker rather than straight to WeatherFlow keeps the Tempest token in one place
and costs nothing — the scrape is running regardless.

This is *not* the same site as temp_c.out in snap_wx.json, despite both being
called `oat` upstream: that one is zwave-js node 8 on the patio at the house.
See README.md. Only the Tempest posts to metrics-server, but /query has no
location filter, so the location is checked here rather than assumed.

Run from cron every 5 minutes, matching the scraper's own interval.

Config comes from .env next to this script (gitignored):

    METRICS_URL=https://metrics-server.<subdomain>.workers.dev
    METRICS_KEY=<the metrics-server API key>
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

WD = os.path.dirname(os.path.abspath(__file__))
SNAP_FILE = os.path.join(WD, 'snap_marmot.json')
ENV_FILE = os.path.join(WD, '.env')

# What scrape.py posts air_temperature under, and the location it tags it with.
SENSOR = 'oat'
LOCATION = 'marmot'

TIMEOUT = 20
# A handful of rows, not one: the newest row is normally the one wanted, but
# this leaves room to skip a reading that is not from the Tempest.
LIMIT = 5
# The Tempest can stop reporting while the worker keeps answering 200 with its
# last row. Older than this and there is nothing worth publishing.
MAX_AGE_SECONDS = 3600


def load_env(path):
    """Minimal KEY=value reader, same as publish_snapshot.py's."""
    out = {}
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


def fetch(url, key):
    """Returns the decoded rows newest-first, or raises."""
    request = urllib.request.Request(
        f'{url.rstrip("/")}/query?sensor={SENSOR}&limit={LIMIT}',
        headers={
            'X-API-Key': key,
            # Cloudflare's bot check answers 403 / error 1010 to urllib's
            # default User-Agent at the edge, before the worker runs. See
            # CLAUDE.md — the symptom looks exactly like a broken deploy.
            'User-Agent': 'haus-tvsnap/1.0',
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read()).get('data', [])


def parse_recorded_at(value):
    """'2026-09-20T19:49:03Z' -> epoch seconds, or None.

    The column is TEXT in that fixed format, not an epoch. strptime rather than
    fromisoformat because 3.10's does not accept the trailing Z.
    """
    try:
        stamp = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None
    return int(stamp.replace(tzinfo=timezone.utc).timestamp())


def build(rows, now):
    """The newest usable Tempest reading, or None.

    Rows tagged with another location are skipped rather than trusted: nothing
    else posts `oat` here today, but the whole point of the name collision note
    in README.md is that the id alone does not identify the site.
    """
    for row in rows:
        if row.get('location') != LOCATION:
            print(f'skipping {SENSOR} row from location '
                  f'{row.get("location")!r}', file=sys.stderr)
            continue

        value = row.get('value')
        if not isinstance(value, (int, float)):
            continue

        obs = parse_recorded_at(row.get('recorded_at'))
        if obs is None:
            continue
        if now - obs > MAX_AGE_SECONDS:
            print(f'newest reading is {(now - obs) // 60} min old',
                  file=sys.stderr)
            return None

        return {'c': round(float(value), 1), 'obs': obs}
    return None


def write_atomic(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(obj, fh, separators=(',', ':'))
    os.replace(tmp, path)


def main():
    env = load_env(ENV_FILE)
    url, key = env.get('METRICS_URL'), env.get('METRICS_KEY')
    if not url or not key:
        sys.exit(f'METRICS_URL and METRICS_KEY must be set in {ENV_FILE}')

    try:
        rows = fetch(url, key)
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Sticky on failure, same as the overlays and fetch_metar.py: the
        # previous sidecar is better than a blank one, and marmot_ts tells the
        # watch how old it has become.
        sys.exit(f'marmot fetch failed, keeping stale sidecar: {e}')

    now = int(time.time())
    marmot = build(rows, now)
    if marmot is None:
        sys.exit('no usable reading, keeping stale sidecar')

    write_atomic(SNAP_FILE, {'ts': now, 'marmot': marmot})
    print(f'wrote {marmot["c"]}C observed {now - marmot["obs"]}s ago')
    return 0


if __name__ == '__main__':
    sys.exit(main())
