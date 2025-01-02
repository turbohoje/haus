#!/usr/bin/env python3
#cron this up to run on the minute

import requests
import pytz
from datetime import datetime
#local file, has IPs of TVs
from tvs_inc import tvs
import pyvizio, time
import json

def basement_office():
    print("\nbasement office wega")
    TV_IP = tvs['office']['ip']  
    PRE_SHARED_KEY = tvs['office']['psk']

    BASE_URL = f"http://{TV_IP}/sony"
    POWER_URL = f"{BASE_URL}/system"
    INPUT_URL = f"{BASE_URL}/avContent"

    HEADERS = {
        "Content-Type": "application/json",
        "X-Auth-PSK": PRE_SHARED_KEY
    }

    def send_command(url, params):
        """Send a command to the TV."""
        try:
            response = requests.post(url, headers=HEADERS, data=json.dumps(params), timeout=5)
            response.raise_for_status()  # Raise an error for bad responses
            return response.json()
        except requests.RequestException as e:
            print(f"Failed to send command: {e}")
            return None
    def get_power_state():
        params = {
            "method": "getPowerStatus",
            "params": [],
            "id": 1,
            "version": "1.0"
        }
        response = send_command(POWER_URL, params)
        if response:
            try:
                # Assuming the response has a structure like {"result": [{"status": True}], ...}
                power_status = response["result"][0]["status"]
                print(power_status)
                return (power_status == "active") 
            except (KeyError, IndexError):
                print("Unexpected response format.")
                return None
        else:
            print("Failed to retrieve power status.")
            return None

    def power_on():
        """Power on the TV."""
        params = {
            "method": "setPowerStatus",
            "params": [{"status": True}],
            "id": 1,
            "version": "1.0"
        }
        response = send_command(POWER_URL, params)
        if response:
            print("Powering on the TV.")
        else:
            print("Failed to power on the TV.")

    def power_off():
        """Power off the TV."""
        params = {
            "method": "setPowerStatus",
            "params": [{"status": False}],
            "id": 1,
            "version": "1.0"
        }
        response = send_command(POWER_URL, params)
        if response:
            print("Powering off the TV.")
        else:
            print("Failed to power off the TV.")

    def switch_to_hdmi(port):
        HDMI_INPUTS = {
            "HDMI 1": "extInput:hdmi?port=1",
            "HDMI 2": "extInput:hdmi?port=2",
            "HDMI 3": "extInput:hdmi?port=3",
            "HDMI 4": "extInput:hdmi?port=4",
        }
        if port not in HDMI_INPUTS:
            print(f"Invalid port: {port}. Available ports: {list(HDMI_INPUTS.keys())}")
            return

        # Payload to set the HDMI input
        payload = {
            "method": "setPlayContent",
            "params": [{"uri": HDMI_INPUTS[port]}],
            "id": 1,
            "version": "1.0",
        }

        # Send the request
        response = requests.post(INPUT_URL, headers=HEADERS, json=payload)

        if response.status_code == 200:
            print(f"Switched to {port}")
        else:
            print(f"Failed to switch to {port}. Status code: {response.status_code}, Response: {response.text}") 

    def get_current_input():
        """
        Get the currently selected input on the Sony TV.
        Returns:
            str: The name of the current input (e.g., "HDMI 1", "HDMI 2") if successful.
            None: If the input information cannot be retrieved.
        """
        params = {
            "method": "getPlayingContentInfo",
            "params": [],
            "id": 1,
            "version": "1.0"
        }
        response = send_command(INPUT_URL, params)
        if response:
            try:
                # Assuming the response has a structure like {"result": [{"source": "extInput:hdmi1", "title": "HDMI 1"}], ...}
                current_input = response["result"][0]["title"]
                return current_input
            except (KeyError, IndexError):
                print("Unexpected response format.")
                return None
        else:
            print("Failed to retrieve input status.")
        return None

    url = tvs['office']['motion']
    print(url)
    response = requests.get(url)
    response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
    last_trip_epoch = int(response.text.strip())  # Assuming the response body is just the epoch time

    tripped_response = requests.get(tvs['office']['tripped'])
    tripped_response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
    tripped_state = int(tripped_response.text.strip())  # Assuming the response body is just the epoch time

    mountain_tz = pytz.timezone("America/Denver")
    now_mountain = datetime.now(mountain_tz)
    
    now_epoch = int(now_mountain.timestamp())
    diff_in_seconds = now_epoch - last_trip_epoch
    
    print(f"Last trip epoch: {last_trip_epoch}")
    print(f"Current time in Denver (epoch): {now_epoch}")
    print(f"Difference in seconds: {diff_in_seconds}")
    print(f"Tripped state: {tripped_state}")

    if tripped_state == 1: 
        state_desired = True
    else:
        state_desired = diff_in_seconds < (3600/4)
    state_current = get_power_state()

    print("TV should be " + str(state_desired))
    print("TV is " + str(state_current))

    if state_desired != state_current:        
        if state_desired: #turn on
            print("powering on")
            power_on()
            time.sleep(5) 

            if tvs['office'].get('input') is not None:
                print("setting input")
                switch_to_hdmi(tvs['office']['input'])
                
        else: #turn off
            if get_current_input() == tvs['office']['input']:
                print("Shutting down")
                power_off()
    else:
        print("input: " + str(get_current_input()))
        print("no change needed")


def lady_den():
    print("\nlady den")
    url = tvs['ladyden']['motion']
    print(url)
    response = requests.get(url)
    response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
    
    last_trip_epoch = int(response.text.strip())  # Assuming the response body is just the epoch time
    
    mountain_tz = pytz.timezone("America/Denver")
    now_mountain = datetime.now(mountain_tz)
    
    now_epoch = int(now_mountain.timestamp())
    diff_in_seconds = now_epoch - last_trip_epoch

    tripped_response = requests.get(tvs['ladyden']['tripped'])
    tripped_response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
    tripped_state = int(tripped_response.text.strip())  # Assuming the response body is just the epoch time
    
    print(f"Last trip epoch: {last_trip_epoch}")
    print(f"Current time in Denver (epoch): {now_epoch}")
    print(f"Difference in seconds: {diff_in_seconds}")
    print(f"Tripped state: {tripped_state}")

    a = pyvizio.Vizio("pyvizio", tvs['ladyden']['ip'], 'ladyden', tvs['ladyden']['auth'])
    
    if tripped_state == 1: 
        state_desired = True
    else:
        state_desired = diff_in_seconds < (3600/4)
    state_current = a.get_power_state()

    print("TV should be " + str(state_desired))
    print("TV is " + str(state_current))

    if state_desired != state_current:        
        if state_desired: #turn on
            print("powering on")
            a.pow_on()
            time.sleep(5) 

            if tvs['ladyden'].get('input') is not None:
                print("setting input")
                a.set_input(tvs['ladyden']['input'])
                
        else: #turn off
            if a.get_current_input() == tvs['ladyden']['input']:
                print("Shutting down")
                a.pow_off()
    else:
        print("input: " + str(a.get_current_input()))
        print("no change needed")


if __name__ == "__main__":
    basement_office()
    lady_den()
    
