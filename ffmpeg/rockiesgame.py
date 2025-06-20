#!/usr/bin/env python3

import requests
import datetime
import pytz
from icalendar import Calendar

# Convert webcal to https for fetching
webcal_url = "webcal://ics.ecal.com/ecal-sub/685561dadb35a70008f599cf/MLB%20.ics"
https_url = webcal_url.replace("webcal://", "https://")

# Fetch the calendar data
response = requests.get(https_url)
calendar = Calendar.from_ical(response.content)

# Set timezone
local_tz = pytz.timezone("America/Denver")  # Change to your timezone
today = datetime.datetime.now(local_tz).date()

output_file = "/home/turbohoje/haus/ffmpeg/imgproc/rockiesgame.txt"

with open(output_file, "w") as f:

    # Parse and filter today's events
    for component in calendar.walk():
        if component.name == "VEVENT":
            dtstart = component.get("dtstart").dt
            description = component.get("description", "No description")

            # Normalize to datetime
            if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
                event_date = dtstart
                event_time = "All day"
            else:
                dtstart = dtstart.astimezone(local_tz)
                event_date = dtstart.date()
                event_time = dtstart.strftime("%I:%M %p")

            if event_date == today and "Buy Tickets" in description:
                print(f"Event Today: {dtstart.strftime('%H:%M')}")
                f.write(f"Rockies {dtstart.strftime('%H:%M')}\n")

