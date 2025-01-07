#!/usr/bin/env python3

import requests

# Your Ecobee API Key
API_KEY = 'SukJ7Wfaw3TnPuKrlX2xDf3NHIwDmAxU'

# The PIN code obtained in the previous step
PIN_CODE = ''

# Step 1: Exchange the PIN code for an authorization code
auth_url = 'https://api.ecobee.com/token'
data = {
    'grant_type': 'ecobeePin',
    'code': PIN_CODE,
    'client_id': API_KEY
}

# Make the POST request to exchange the PIN code for an authorization code
response = requests.post(auth_url, data=data)
print(response)

if response.status_code == 200:
    # Step 2: Successfully obtained the authorization code and access token
    token_data = response.json()
    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']
    print(f"Access Token: {access_token}")
    print(f"Refresh Token: {refresh_token}")
else:
    print(f"Failed to obtain access token: {response.text}")

