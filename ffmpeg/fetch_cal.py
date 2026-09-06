#!/usr/bin/env python3
"""Write the next few calendar events into drawtext overlay files.

Run from cron every 5 minutes, same as fetch_wx.py. Reads two Google
calendars with the service account that calendar_copy/cal_sync.py already
uses (cal-sync@rocketscience-calendar-sync.iam.gserviceaccount.com, which is
shared on both calendars) and writes three plain text files for ffmpeg.sh to
overlay along the bottom of the photo panel: one per calendar in the bottom
corners, plus the rows both calendars share, centered on the row above.

Widths are set by the 1280px photo panel at fontsize 33 (AndaleMono is exactly
20px/char there). Two side blocks plus a gap leave 29 chars each; a shared row
has the row to itself, so it gets the panel's full 62.
"""

import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

WD = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS = '/home/turbohoje/calendar_copy/credentials_dw.json'
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TZ = ZoneInfo('America/Denver')

JENNY = 'herroyalhighness.jenny@gmail.com'
JUSTIN = 'justin@rocketscience.cc'

JENNY_FILE = 'cal_jenny.txt'
JUSTIN_FILE = 'cal_justin.txt'
BOTH_FILE = 'cal_both.txt'

EVENT_COUNT = 4
LOOKAHEAD_DAYS = 60

# Every row is a 1-char weekday + 5-char time + space, then the title.
SIDE_TITLE_WIDTH = 22    # 7 + 22 = 29 chars, half the panel less the gap
SHARED_TITLE_WIDTH = 55  # 7 + 55 = 62 chars, the full panel width

# Single-letter days, same scheme wx_forecast_week.txt already puts on screen:
# T is Tuesday and R is Thursday, S is Saturday and U is Sunday.
DOW = ['M', 'T', 'W', 'R', 'F', 'S', 'U']


# Which synthesized busy blocks are worth a slot, by what is inside the parens.
VISIBLE_BUSY = {'volta'}


def relabel(summary):
    """Rewrite cal_sync.py's placeholder blocks, or drop them.

    cal_sync.py merges other calendars into justin@rocketscience.cc as
    synthesized 'busy (Volta)' / 'busy (AO)' / 'busy (personal)' blocks. Volta
    is worth showing, but not under a title that reads as a stop word, so it
    goes on screen as just 'Volta'. The rest say nothing and return None to be
    dropped.
    """
    if summary.lower().startswith('busy (') and summary.endswith(')'):
        inner = summary[len('busy ('):-1].strip()
        return inner if inner.lower() in VISIBLE_BUSY else None
    return summary


def upcoming(events, now):
    """Filter to events that have not started yet, keeping start-time order.

    An all-day event started at midnight, so requiring start > now would drop
    it for the whole day it is happening. All-day events count as upcoming
    through the end of their last day instead.
    """
    today = now.date()
    out = []
    for ev in events:
        summary = relabel((ev.get('summary') or '').strip())
        if not summary:
            continue

        start = ev['start']
        if 'date' in start:
            # All-day. 'end' is exclusive, so an event ending tomorrow is today's.
            end_date = datetime.date.fromisoformat(ev['end']['date'])
            if end_date <= today:
                continue
            out.append((summary, None, datetime.date.fromisoformat(start['date'])))
        else:
            start_dt = datetime.datetime.fromisoformat(start['dateTime']).astimezone(TZ)
            if start_dt <= now:
                continue
            out.append((summary, start_dt, start_dt.date()))
    return out


def entries(events):
    """The first EVENT_COUNT distinct events as
    (weekday, time, title, epoch, all_day) tuples.

    Deduped by title so a multi-day or daily-recurring event does not eat the
    whole list — each distinct event shows once, at its earliest occurrence.
    Kept unformatted so shared rows can be re-rendered at the wider width.

    The trailing epoch/all_day carry the start moment for snap_cal.json. Only
    the first three fields are ever compared or drawn, so they do not affect
    the overlays — see split_shared().
    """
    out = []
    seen = set()
    for summary, start_dt, day in events:
        key = summary.lower()
        if key in seen:
            continue
        seen.add(key)

        when = start_dt.strftime('%H:%M') if start_dt else '  all'
        if start_dt is not None:
            epoch = int(start_dt.timestamp())
        else:
            # All-day: pin to local midnight of the first day so the watch can
            # render a date without needing to know the event had no time.
            epoch = int(datetime.datetime.combine(
                day, datetime.time.min, tzinfo=TZ).timestamp())
        out.append((DOW[day.weekday()], when, summary, epoch, start_dt is None))
        if len(out) == EVENT_COUNT:
            break
    return out


def format_rows(items, title_width):
    return [f'{dow}{when} {summary[:title_width]}'
            for dow, when, summary, _epoch, _all_day in items]


def split_shared(left, right):
    """Pull rows the two calendars have in common into their own list.

    It takes the same weekday, time and full title on both sides to count as
    the same thing — Jenny's 09:00 dentist and Justin's 14:00 dentist stay in
    their own columns. Matching on the full title rather than the truncated
    one keeps two long, differently-ending titles apart.

    Neither side gets backfilled, so k shared rows means k lines in the middle
    and EVENT_COUNT-k down each side. The middle block is drawn above the side
    blocks, and this keeps the sides at 3 lines or fewer whenever there is
    anything in the middle for them to clear.
    """
    right_keys = {item[:3] for item in right}
    shared = [item for item in left if item[:3] in right_keys]
    common = {item[:3] for item in shared}
    return ([item for item in left if item[:3] not in common],
            [item for item in right if item[:3] not in common],
            shared)


def write_atomic(path, lines):
    """drawtext re-reads the file every frame, so swap it in whole rather than
    letting a frame catch a half-written file."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        fh.write(''.join(line + '\n' for line in lines))
    os.replace(tmp, path)


# ── JSON sidecar for the Cloudflare snapshot (see ../tvsnap/README.md) ───────
# Jenny's calendar is deliberately not included: only Justin's own rows and the
# rows both calendars share leave the house.

SNAP_FILE = 'snap_cal.json'
SNAP_TITLE_WIDTH = 60  # bounds the payload; real titles are far shorter


def snap_rows(items):
    """Display truncation is a panel-width artifact, so titles go out at their
    full length here and the watch decides how much of one it can draw."""
    return [{'s': epoch, 'all': 1 if all_day else 0,
             't': summary[:SNAP_TITLE_WIDTH]}
            for _dow, _when, summary, epoch, all_day in items]


def write_snapshot(justin_only, shared):
    """Reached only on a successful fetch, so a failed run leaves the previous
    sidecar for publish_snapshot.py to re-send — same rule as the overlays."""
    try:
        write_atomic_json(os.path.join(WD, SNAP_FILE), {
            'ts': int(datetime.datetime.now(TZ).timestamp()),
            'justin': snap_rows(justin_only),
            'both': snap_rows(shared),
        })
    except OSError as e:
        # The overlays are the job; never fail the run over the snapshot.
        print(f'{SNAP_FILE} not written: {e}', file=sys.stderr)


def write_atomic_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(obj, fh, separators=(',', ':'))
    os.replace(tmp, path)


def fetch(service, calendar_id, time_min, time_max):
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime',
        maxResults=100,
    ).execute()
    return result.get('items', [])


def main():
    creds = Credentials.from_service_account_file(CREDENTIALS, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    now = datetime.datetime.now(TZ)
    time_min = now.isoformat()
    time_max = (now + datetime.timedelta(days=LOOKAHEAD_DAYS)).isoformat()

    try:
        jenny = fetch(service, JENNY, time_min, time_max)
        justin = fetch(service, JUSTIN, time_min, time_max)
    except (HttpError, OSError) as e:
        # The three files have to agree on which rows are shared, so one bad
        # fetch means none of them get rewritten. The overlays keep their last
        # good contents rather than blanking, same as power.txt / center_wx.txt.
        print(f'fetch failed, keeping stale overlays: {e}', file=sys.stderr)
        return 1

    jenny_only, justin_only, shared = split_shared(
        entries(upcoming(jenny, now)), entries(upcoming(justin, now)))

    write_atomic(os.path.join(WD, JENNY_FILE), format_rows(jenny_only, SIDE_TITLE_WIDTH))
    write_atomic(os.path.join(WD, JUSTIN_FILE), format_rows(justin_only, SIDE_TITLE_WIDTH))
    write_atomic(os.path.join(WD, BOTH_FILE), format_rows(shared, SHARED_TITLE_WIDTH))

    write_snapshot(justin_only, shared)
    return 0


if __name__ == '__main__':
    sys.exit(main())
