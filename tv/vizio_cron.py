#!/bin/env python3
#pip3 install pyvizio

import pyvizio, os, time, sys, getopt
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

tvs = {
    "master":{
        "ip":"10.22.14.187",
        "auth":"Zdmx9r0pcx",
        "input":"HDMI-3"
    },
    "kitchen":{
        "ip":"10.22.14.133",
        "auth":"Z0xucmo0yo",
        "input":"HDMI-3"
    }
}

key = "kitchen"
a = pyvizio.Vizio("pyvizio", tvs[key]['ip'], key, tvs[key]['auth'])

if a.get_power_state() == False:
    print("tv is off, powering on and setting input")
    a.pow_on()
    time.sleep(3)
    a.set_input(tvs[key]['input'])
    time.sleep(secdelay)
    print("Shutting down")
    a.pow_off()
else:
    print("tv is on, skipping")
