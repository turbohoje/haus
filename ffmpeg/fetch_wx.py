#!/usr/bin/env python3

import requests, sys, re
from lxml import html

def fetch_html(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError if the response was an HTTP error

        tree = html.fromstring(response.content)
        return tree
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
        return None

def xpath_value(content, xpath):
    element = content.xpath(xpath)
    return str(element[0].text_content()) if element else None

def ftoc(f):
    if type(f) == str:
        f = int(f)
    c = (f - 32) * 5 / 9
    return "{:4.1f}".format(c)

url = 'https://www.wunderground.com/weather/us/co/denver'  # Replace with your desired URL
xpath = ''  # Replace with the XPath of the element you want to find


content = fetch_html(url)

today_f    = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[1]/div/a/div/div[2]/span[3]/span/lib-display-unit/span/span[1]')
tonight_f  = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[2]/div/a/div/div[2]/span[3]/span/lib-display-unit/span/span[1]')
tomorrow_f = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[3]/div/a/div/div[2]/span[3]/span[1]/lib-display-unit/span/span[1]')


today_precip    = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[1]/div/div/div/a[1]')
tonight_precip  = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[2]/div/div/div/a[1]')
tomorrow_precip = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[3]/div/div/div/a[1]')

if None in (today_f, tonight_f, tomorrow_f, today_precip, tonight_precip, tomorrow_precip):
    print("Failed to scrape values")
    sys.exit(1)

tod_c = ftoc(today_f)
ton_c = ftoc(tonight_f)
tom_c = ftoc(tomorrow_f)

m = re.search(r'^(\d+)%', today_precip)
tod_p = m.group(1)
m = re.search(r'^(\d+)%', tonight_precip)
ton_p = m.group(1)
m = re.search(r'^(\d+)%', tomorrow_precip)
tom_p = m.group(1)

# print(f"today {today_f} tonight_f {tonight_f} tomorrow {tomorrow_f}")
# print(f"today preicp {today_precip} tonight_precip {tonight_precip} tomorrow precip {tomorrow_precip}")

print(f"Today:   {tod_c}°C {tod_p}%")
print(f"Tonight: {ton_c}°C {ton_p}%")
print(f"Tomorrow:{tom_c}°C {tom_p}%")
