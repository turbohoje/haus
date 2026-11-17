#!/usr/bin/env python3
"""Save today's NYT Learning Network word of the day for fetch_cal.py.

The column page 403s anything that isn't a browser, but its RSS feed doesn't.
The feed only carries the word -- the definition is on the article page, which
403s too -- so the definition comes from Wiktionary instead.

Writes wotd.txt as '<YYYY-MM-DD> <word>: <definition>' with the date it was
published in Denver, so fetch_cal.py can tell today's word from a stale one.
A failed definition lookup writes the word alone, and the next run retries.

Words are only published on weekdays, at 10:00 UTC (03:00 MST / 04:00 MDT);
cron runs this every 10 minutes through the morning to catch it either side of
DST, and it leaves the file alone until today's word is up.
"""

import datetime
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

WD = os.path.dirname(os.path.abspath(__file__))
WOTD_FILE = 'wotd.txt'
TZ = ZoneInfo('America/Denver')
FEED = ('https://www.nytimes.com/svc/collections/v1/publish/'
        'https://www.nytimes.com/column/learning-word-of-the-day/rss.xml')
PREFIX = 'Word of the Day: '
DEFINE = 'https://en.wiktionary.org/api/rest_v1/page/definition/'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def define(word):
    """First non-empty English definition, as plain text, or None."""
    try:
        entries = json.loads(get(DEFINE + urllib.parse.quote(word))).get('en', [])
    except (OSError, ValueError) as e:
        print(f'definition lookup failed: {e}', file=sys.stderr)
        return None
    for entry in entries:
        for d in entry.get('definitions', []):
            text = html.unescape(re.sub('<[^>]+>', '', d.get('definition', ''))).strip()
            if text:
                return text
    return None


def main():
    try:
        root = ET.fromstring(get(FEED))
    except (OSError, ET.ParseError) as e:
        print(f'fetch failed: {e}', file=sys.stderr)
        return 1

    today = datetime.datetime.now(TZ).date()
    for item in root.iter('item'):
        title = item.findtext('title') or ''
        if not title.startswith(PREFIX):
            continue
        published = email.utils.parsedate_to_datetime(item.findtext('pubDate'))
        if published.astimezone(TZ).date() != today:
            return 0  # not posted yet, or a weekend
        word = title[len(PREFIX):].strip()
        definition = define(word)
        line = f'{word}: {definition}' if definition else word
        tmp = os.path.join(WD, WOTD_FILE + '.tmp')
        with open(tmp, 'w') as fh:
            fh.write(f'{today.isoformat()} {line}\n')
        os.replace(tmp, os.path.join(WD, WOTD_FILE))
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
