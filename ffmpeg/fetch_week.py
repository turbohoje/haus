#!/usr/bin/env python3
# grab a weeks worth of data form wxunderground, not bothering every 15 min.
# cron this daily at 0400


import pickle, os, re
from datetime import date
import requests
from lxml import html
url10 = 'https://www.wunderground.com/forecast/us/co/denver' # 10 day

# wunderground redesign (2026-10): the ten-day grid is now server-rendered,
# so a plain GET works and playwright is no longer needed.
r = requests.get(url10, timeout=30)
r.raise_for_status()
tree = html.fromstring(r.content)
items = tree.xpath('//forecast-grid/forecast-grid-item')

def num(el, xp):
    return re.search(r'-?\d+', el.xpath(xp)[0].text_content()).group(0)

next=[0]*7
# skip today + tomorrow (shown in the hourly block), same as the old a[3..9]
for i, item in enumerate(items[2:9]):
    c, d = item.xpath('.//div[@class="date"]')[0].text_content().split()
    next[i]=[
        num(item, './/div[@class="temp"]/div[contains(@class,"high")]'),
        num(item, './/div[@class="temp"]/div[contains(@class,"low")]'),
        c,
        d
    ]
print(next)

data={'values':next, 'last':date.today()}

current_file_directory = os.path.dirname(os.path.abspath(__file__))
with open(current_file_directory+'/forecast.pkl', 'wb') as file:
    pickle.dump(data, file)
