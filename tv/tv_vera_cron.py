#!/usr/bin/env python3
#cron this up to run on the minute

import requests
import pytz
from datetime import datetime
#local file, has IPs of TVs
from tvs_inc import tvs
import pyvizio, time
import json
from datetime import datetime
import sys
sys.path.insert(0, "/home/turbohoje/haus/zwavejs")
import zwq  # zwave-js value reader (replaces Vera data_request calls)

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

    # Current-motion only (zwave-js has no LastTrip epoch; old 15-min linger dropped).
    motion = zwq.motion_tripped(tvs['office']['motion_node'])
    print(f"Motion (office): {motion}")

    state_desired = bool(motion)
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
    # Current-motion only (zwave-js has no LastTrip epoch; old 15-min linger dropped).
    motion = zwq.motion_tripped(tvs['ladyden']['motion_node'])
    print(f"Motion (lady den): {motion}")

    a = pyvizio.Vizio("pyvizio", tvs['ladyden']['ip'], 'ladyden', tvs['ladyden']['auth'])

    state_desired = bool(motion)
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

def lady_den_floor():
    print("\nlady den floor")
    # Current-motion only (zwave-js has no LastTrip epoch; old 15-min linger dropped).
    motion = zwq.motion_tripped(tvs['ladyden']['motion_node'])
    current_temp = zwq.temperature_c(tvs['ladyden']['temp_node'])
    print(f"Motion (lady den): {motion}")

    state_current = bool(zwq.switch_on(tvs['ladyden']['floor_node']))

    #turn on 4-7 am every weekday
    current_time = datetime.now()
    current_hour = current_time.hour
    current_weekday = current_time.weekday()

    if current_weekday < 5 and 4 <= current_hour < 7:
        pre_warm = True
    else:
        pre_warm = False

    state_desired = bool(motion) or pre_warm

    #max temp
    print("current temp")
    print(current_temp)
    if current_temp is not None and current_temp > tvs['ladyden']['temp_max']:
        state_desired = False


    print("Floor should be " + str(state_desired))
    print("Floor is " + str(state_current))

    if state_desired != state_current:
        if state_desired: #turn on
            print("powering on water pump")
            zwq.set_switch(tvs['ladyden']['floor_node'], True)
            time.sleep(5)

        else: #turn off
            zwq.set_switch(tvs['ladyden']['floor_node'], False)
    else:
        print("no change needed")

if __name__ == "__main__":
    basement_office()
    lady_den()
    #lady_den_floor()
    
