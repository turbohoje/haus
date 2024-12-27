#!/usr/bin/env python3

import requests
import pytz
from datetime import datetime
#local file, has IPs of TVs
from tvs_inc import tvs
import pyvizio, time

def lady_den():
    url = tvs['ladyden']['motion']
    print(url)
    response = requests.get(url)
    response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
    
    last_trip_epoch = int(response.text.strip())  # Assuming the response body is just the epoch time
    
    mountain_tz = pytz.timezone("America/Denver")
    now_mountain = datetime.now(mountain_tz)
    
    now_epoch = int(now_mountain.timestamp())
    diff_in_seconds = now_epoch - last_trip_epoch
    
    print(f"Last trip epoch: {last_trip_epoch}")
    print(f"Current time in Denver (epoch): {now_epoch}")
    print(f"Difference in seconds: {diff_in_seconds}")

    a = pyvizio.Vizio("pyvizio", tvs['ladyden']['ip'], 'ladyden', tvs['ladyden']['auth'])
    
    state_desired = diff_in_seconds < 3600
    state_current = a.get_power_state()

    print("TV should be " + str(state_desired))
    print("TV is " + str(state_current))

    if state_desired != state_current:        
        if state_desired: #turn on
            print("powering on")
            a.pow_on()
            time.sleep(3) 
            
            if tvs['ladyden'].get('input') is not None:
                print("setting input")
                a.set_input(tvs['ladyden']['input'])
                
        else: #turn off
            if a.get_current_input() == tvs[key]['input']:
                print("Shutting down")
                a.pow_off()
    else:
        print("input: " + str(a.get_current_input()))
        print("no change needed")


if __name__ == "__main__":
    lady_den()
