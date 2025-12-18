#!/usr/bin/env python3
import sys, json

from pathlib import Path
from pyecobee import *

if len(sys.argv) < 2:
    print("Please provide off or manual")
    sys.exit(1)


print (f"setting to {sys.argv[1]}")


current_directory = str(Path(__file__))
last_slash_index = current_directory.rfind("/")+1
current_directory = current_directory[:last_slash_index]
token_file = current_directory+"token.json"

try:
    with open(token_file, "r") as f:
        tok = json.load(f)
except FileNotFoundError:
    print(f"ERROR: token file not found: {token_file}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"ERROR: token file is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: failed to load token file: {e}", file=sys.stderr)
    sys.exit(1)

#print(tok)

ecobee_service = EcobeeService(
    thermostat_name='Main FLoor',
    application_key='SukJ7Wfaw3TnPuKrlX2xDf3NHIwDmAxU',
    refresh_token=tok['refresh_token'],
    access_token = tok['access_token'] 
)


#used to get pin 
#authorize_response = ecobee_service.authorize()
#print(authorize_response.pretty_format())
#print('Authorization Token => {0}'.format(ecobee_service.authorization_token))

#or hit this url: https://api.ecobee.com/authorize?response_type=ecobeePin&client_id=SukJ7Wfaw3TnPuKrlX2xDf3NHIwDmAxU&scope=smartRead,smartWrite,offline_access,thermostat
# and put the contents in token.json

# curl -X POST https://api.ecobee.com/token -H "Content-Type: application/x-www-form-urlencoded"  --data "grant_type=ecobeePin&code=SRrdAJ5b5ddp8IB50sqShiDjSRrdAJ5b5ddp8IB50sqShiDj&client_id=SukJ7Wfaw3TnPuKrlX2xDf3NHIwDmAxU"

# check and get fresh access token
ecobee_service.refresh_tokens() 

# After refreshing, update the token data and save it back to the file
nt = {
    "access_token": ecobee_service.access_token,
    "token_type": "Bearer",
    "expires_in": 3600,  # Typical expiration time for access tokens
    "scope": "smartRead,smartWrite,offline_access,thermostat",
    "refresh_token": ecobee_service.refresh_token
}

#print(nt)



#save token off to disk
try:
    with open(token_file, "w") as outfile:
        outfile.write(json.dumps(nt))
except FileNotFoundError:
    print(f"ERROR: token file not found: {token_file}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"ERROR: token file is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: failed to load token file: {e}", file=sys.stderr)
    sys.exit(1)

#working summary response
# thermostat_summary_response = ecobee_service.request_thermostats_summary(selection=Selection(
#     selection_type=SelectionType.THERMOSTATS.value,
#     selection_match='319279437236',
#     include_alerts=True,
#     include_device=True, 
#     include_settings=True,  
#     include_equipment_status=True))

# print(thermostat_summary_response.pretty_format())
# print(thermostat_summary_response)

thermostats = ecobee_service.request_thermostats(selection=Selection(
    selection_type=SelectionType.THERMOSTATS.value,
    selection_match='319279437236',
    include_alerts=True,
    include_device=True, 
    include_settings=True,  
    include_equipment_status=True))
thermostat = thermostats.thermostat_list[0]
print(f"current value {thermostat.settings.humidifier_mode}")

#thermostat.settings.humidifier_mode = "off" || "manual"

update_thermostat_response = ecobee_service.update_thermostats(
        selection=Selection(
            selection_type=SelectionType.THERMOSTATS.value,
            selection_match='319279437236'),
        thermostat=Thermostat(thermostat.identifier,
            settings=Settings(
                humidifier_mode=sys.argv[1])
            )
)
        
#print(update_thermostat_response.pretty_format())

# sys.exit(0)
# THERMOSTAT_ID = '319279437236'
# desired_humidity = 40


# issue_demand_response_response = ecobee_service.issue_demand_response(
#     selection=Selection(
#         selection_type=SelectionType.THERMOSTATS.value,
#         selection_match='319279437236'),
#     demand_response=DemandResponse(
#         name='myDR',
#         message='This is a DR!',
#         event=Event(
#             heat_hold_temp=790,
#             end_time='11:37:18',
#             end_date='2025-02-04',
#             name='apiDR',
#             # type='useEndTime',
#             cool_hold_temp=790,
#             start_date='2025-01-04',
#             start_time='11:37:18',
#             is_temperature_absolute=True)))
# logger.info(issue_demand_response_response.pretty_format())
# assert issue_demand_response_response.status.code == 0, (
#     'Failure while executing issue_demand_response_response:\n{0}'.format(
#         issue_demand_response_response.pretty_format()))
