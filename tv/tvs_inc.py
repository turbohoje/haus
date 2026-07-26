tvs = {
    "master":{
        "ip":"10.22.14.134",
        "auth":"Zdmx9r0pcx",
        "input":"HDMI-3",
        "backlight": (60*30)
    },
    "kitchen":{
        "ip":"10.22.14.133",
        "auth":"Z0xucmo0yo",
        "input":"HDMI-3"
    },
    # Vera (10.22.14.4) decommissioned 2026-07-26 — sensors migrated to zwave-js.
    # Values below are zwave-js node ids (see zwavejs/MIGRATION_CHECKLIST.md);
    # tv_vera_cron.py reads them via the zwq helper. Old Vera DeviceNums noted.
    "ladyden":{
        "ip":"10.22.14.87",
        "auth":"Z3ung2wbir",
        "input":"hdmi2",
        "motion_node": 9,     # Lady Den ZW100        (was Vera DeviceNum 215)
        "temp_node": 9,       # Lady Den ZW100 temp   (was 236)
        "temp_max": 22.0,
        "floor_node": 24,     # Water Pump switch     (was 192)
    },
    "office":{
        "ip":"10.22.14.104",
        "psk":"2214",
        "input": "HDMI 3",
        "motion_node": 21,    # Basement Office ZW100 (was Vera DeviceNum 198)
    }
}
