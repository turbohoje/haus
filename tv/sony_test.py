#!/usr/bin/env python3

# 10.22.14.104
# static in ubiquiti

import requests
import json

# vera motion url status
# http://10.22.14.4:3480/data_request?id=status&DeviceNum=198
# last trip epoch
# http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=198&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=LastTrip 

# Sony Bravia TV IP address and pre-shared key
TV_IP = "10.22.14.104"  
PRE_SHARED_KEY = "2214" 

# Sony Bravia endpoints
BASE_URL = f"http://{TV_IP}/sony"
POWER_URL = f"{BASE_URL}/system"
INPUT_URL = f"{BASE_URL}/avContent"

# Headers for the requests
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

def select_input(input_name):
    """
    Select a known input.
    input_name: str, e.g., "HDMI 1", "HDMI 2", etc.
    """
    params = {
        "method": "setPlayContent",
        "params": [{"uri": f"tv:/{input_name}"}],
        "id": 1,
        "version": "1.0"
    }
    response = send_command(INPUT_URL, params)
    if response:
        print(f"Switched to input: {input_name}")
    else:
        print("Failed to change input.")


def switch_to_hdmi(port):
    HDMI_INPUTS = {
        "HDMI1": "extInput:hdmi?port=1",
        "HDMI2": "extInput:hdmi?port=2",
        "HDMI3": "extInput:hdmi?port=3",
        "HDMI4": "extInput:hdmi?port=4",
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


# Example usage
if __name__ == "__main__":
    # Power on the TV
    #power_on()

    # Switch to a known input, e.g., "HDMI 1"
    #select_input("hdmi 3")
    switch_to_hdmi("HDMI3")

    # Power off the TV
    #power_off()

