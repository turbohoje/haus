#!/bin/env python3
#pip3 install pyvizio

import pyvizio, os, time, sys, getopt, threading

#pull in tvs object
from tvs_inc import tvs

key = ""
secdelay = 3600
try:
    opts, args = getopt.getopt(sys.argv[1:], "d:m:", ["display=","min="])
    for opt, arg in opts:
        if opt in ("-d", "--display"):
            key = arg
        if opt in ("-m", "--min"):
            secdelay = 60 * int(arg)
except getopt.GetoptError as err:
    # print help information and exit:
    print(err)  # will print something like "option -a not recognized"
    sys.exit(2)



a = pyvizio.Vizio("pyvizio", tvs[key]['ip'], key, tvs[key]['auth'])
# a.set_setting("picture", "backlight", 50)

def brightness_inc(val):
    #increase the brightness in 5 steps over val seconds
    #sleep to let the input select rest
    for inc in range(1, 102, 20):
        if inc > 100:
            inc = 100
        print("setting bright to " + str(inc))
        a.set_setting("picture", "backlight", int(inc))
        time.sleep(int(int(val)/5))
    print("brightness done")

if a.get_power_state() == False:
    print(key + " tv is off, powering on and setting input")
    
    print("setting input")
    a.set_input(tvs[key]['input'])
    
    time.sleep(3)
    
    if tvs[key].get('backlight') is not None:
        print("backlight!!")
        x = threading.Thread(target=brightness_inc, args=((tvs[key]['backlight'],)))
        x.start()
    
    time.sleep(3) 
    a.pow_on()
    
    a.set_input(tvs[key]['input'])
    time.sleep(secdelay)
    
    #only shutdown if the input hasnt been changed.
    if a.get_current_input() == tvs[key]['input']:
        print("Shutting down")
        a.pow_off()
    else:
        print("input changed, assume someone is watching the tv")
else:
    print(key + " tv is on, skipping")
