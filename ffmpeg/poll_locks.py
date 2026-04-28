#!/usr/bin/env python3

import requests
import time

VERA_IP = "10.22.14.4"
VERA_PORT = 3480

# Define your locks in a list of dicts for convenience
LOCKS = [
    {"name": "front",  "id": 24},
    {"name": "back",   "id": 22},
    {"name": "garage", "id": 23},
]

def poll_device(device_id):
    """
    Send a request to Vera to poll (re-read) the device's status.
    Equivalent to calling luup.call_action("HaDevice1", "Poll")
    """
    url = (
        f"http://{VERA_IP}:{VERA_PORT}/data_request?id=action"
        f"&DeviceNum={device_id}"
        f"&serviceId=urn:micasaverde-com:serviceId:HaDevice1"
        f"&action=Poll"
    )
    try:
        requests.get(url, timeout=5)
        print(f"  -> Poll request sent for device #{device_id}")
    except requests.RequestException as ex:
        print(f"  -> Error polling device #{device_id}: {ex}")

def get_lock_status(device_id):
    """
    Returns the lock status as a string: "Locked", "Unlocked", or "Unknown"
    """
    url = (
        f"http://{VERA_IP}:{VERA_PORT}/data_request?id=variableget"
        f"&DeviceNum={device_id}"
        f"&serviceId=urn:micasaverde-com:serviceId:DoorLock1"
        f"&Variable=Status"
    )
    try:
        resp = requests.get(url, timeout=5)
        status_str = resp.text.strip()
        if status_str == "1":
            return "Locked"
        elif status_str == "0":
            return "Unlocked"
        else:
            return f"Unknown ({status_str})"
    except requests.RequestException as ex:
        return f"Error: {ex}"

def get_last_poll_success_info(device_id):
    """
    Returns a tuple of (diff_seconds, formatted_string)

      diff_seconds: How many seconds since last poll success, or None on error
      formatted_string: '10s', '5m', '3h', '2d', or 'Unknown(...)'
    """
    url = (
        f"http://{VERA_IP}:{VERA_PORT}/data_request?id=variableget"
        f"&DeviceNum={device_id}"
        f"&serviceId=urn:micasaverde-com:serviceId:ZWaveNetwork1"
        f"&Variable=LastPollSuccess"
    )
    try:
        resp = requests.get(url, timeout=5)
        last_poll_str = resp.text.strip()
        if not last_poll_str.isdigit():
            return (None, f"Unknown ({last_poll_str})")

        last_poll_epoch = int(last_poll_str)
        now_epoch = int(time.time())
        diff = now_epoch - last_poll_epoch

        # Build the readable string
        if diff < 60:
            result = f"{diff}s"
        elif diff < 3600:
            minutes = diff // 60
            result = f"{minutes}m"
        elif diff < 86400:
            hours = diff // 3600
            result = f"{hours}h"
        else:
            days = diff // 86400
            result = f"{days}d"

        return (diff, result)

    except requests.RequestException as ex:
        return (None, f"Error: {ex}")

def poll_locks():
    """
    Polls all the locks and prints status + time-since-last-poll.
    If it's been over an hour (3600s) since last poll, attempts to poll again.
    """
    for lock in LOCKS:
        print(f"{lock['name'].capitalize()} Lock:")
        
        # Get lock status
        lock_state = get_lock_status(lock["id"])
        print(f"  State: {lock_state}")

        # Get LastPollSuccess info
        diff_seconds, time_since_poll_str = get_last_poll_success_info(lock["id"])
        print(f"  Last poll success: {time_since_poll_str}")

        # If it's been over an hour since last poll, try polling again
        if diff_seconds is not None and diff_seconds > 3600:
            poll_device(lock["id"])

        print("")

if __name__ == "__main__":
    poll_locks()

