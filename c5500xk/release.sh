#!/bin/bash

#login, get session id
SESSION_ID="$(
    curl 'https://192.168.0.1/cgi/cgi_action' \
      -H 'Accept: */*' \
      -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
      -H 'Connection: keep-alive' \
      -H 'Content-Type: text/plain;charset=UTF-8' \
      -H 'DNT: 1' \
      -H 'Origin: https://192.168.0.1' \
      -H 'Referer: https://192.168.0.1/login.html' \
      -H 'Sec-Fetch-Dest: empty' \
      -H 'Sec-Fetch-Mode: cors' \
      -H 'Sec-Fetch-Site: same-origin' \
      -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
      -H 'X-Requested-With: XMLHttpRequest' \
      -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
      -H 'sec-ch-ua-mobile: ?0' \
      -H 'sec-ch-ua-platform: "macOS"' \
      --data-raw "username=admin&password=$password" \
      --insecure \
      -c - 2>/dev/null \
    | awk '/Session-Id/ {print $NF}'
)"

#get status
curl 'https://192.168.0.1/cgi/cgi_get?Object=GetConnectionStatus' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --insecure -s | jq '.wan_status.net_state, .wan_status.ipaddr'

#release
curl 'https://192.168.0.1/cgi/cgi_set' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Origin: https://192.168.0.1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'content-type: application/x-www-form-urlencoded' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --data-raw 'Object=Device.X_CTL_WANDetection&Operation=Modify&ReleaseWANIP=true' \
  --insecure
curl 'https://192.168.0.1/cgi/cgi_action' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: text/plain;charset=UTF-8' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Origin: https://192.168.0.1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --data-raw 'Action=Release' \
  --insecure

sleep 10
#renew
  curl 'https://192.168.0.1/cgi/cgi_set' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Origin: https://192.168.0.1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'content-type: application/x-www-form-urlencoded' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --data-raw 'Object=Device.X_CTL_WANDetection&Operation=Modify&ReleaseWANIP=false' \
  --insecure

curl 'https://192.168.0.1/cgi/cgi_action' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: text/plain;charset=UTF-8' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Origin: https://192.168.0.1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --data-raw 'Action=Renew' \
  --insecure
sleep 5
#print new IP
  curl 'https://192.168.0.1/cgi/cgi_get?Object=GetConnectionStatus' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9,fr;q=0.8' \
  -H 'Connection: keep-alive' \
  -b "Session-Id=$SESSION_ID" \
  -H 'DNT: 1' \
  -H 'Referer: https://192.168.0.1/quicksetup.html' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  --insecure -s | jq '.wan_status.net_state, .wan_status.ipaddr'
