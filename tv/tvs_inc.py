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
    "ladyden":{
        "ip":"10.22.14.87",
        "auth":"Z3ung2wbir",
        "input":"hdmi2",
        "motion":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=215&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=LastTrip",
        "temp":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=236&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature",
        "temp_max": 22.0,
        "tripped":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=215&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=Tripped",
        "floor_status":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=192&serviceId=urn:upnp-org:serviceId:SwitchPower1&Variable=Status",
        "floor_set":"http://10.22.14.4:3480/data_request?id=action&DeviceNum=192&serviceId=urn:upnp-org:serviceId:SwitchPower1&action=SetTarget&newTargetValue="
    },
    "office":{
        "ip":"10.22.14.104",
        "psk":"2214",
        "input": "HDMI 3",
        "motion":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=198&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=LastTrip",
        "tripped":"http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=198&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=Tripped"
    }
}
