#!/usr/bin/env python3

import requests, sys, re, pickle, os
from datetime import date
from lxml import html
from playwright.sync_api import sync_playwright

current_file_directory = os.path.dirname(os.path.abspath(__file__))

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

def print_elements(element, indent=0):
    print("  " * indent + f"Tag: {element.tag}, Text: {element.text.strip() if element.text else 'None'}")
    
    # Iterate over child elements and recursively print them
    for child in element:
        print_elements(child, indent + 1)

def xpath_value(content, xpath):
    element = content.xpath(xpath)
    return str(element[0].text_content()) if element else None

def ftoc(f):
    if type(f) == str:
        f = int(f)
    c = (f - 32) * 5 / 9
    return "{:4.1f}".format(c)

def ctof(c):
    return "{:2.0f}".format((now_c * 9/5) + 32.0)

url = 'https://www.wunderground.com/weather/us/co/denver'  # Replace with your desired URL
aqi_url = 'https://www.wunderground.com/health/us/co/denver?cm_ven=localwx_modaq'
xpath = ''  # Replace with the XPath of the element you want to find

oat_now_c = "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=112&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature"
basemnt_now_c = "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=228&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature"
ladyden_now_c = "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=232&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature"

r = requests.get(oat_now_c)
now_c = float(r.text)
now_f = ctof(now_c)
now_cs = "{:4.1f}".format(now_c)

try:
    r = requests.get(basemnt_now_c)
    now_c = float(r.text)
    basement_now_txt = "{:4.1f}".format(now_c)
except:
  basement_now_txt = "-nf-"


try:
    r = requests.get(ladyden_now_c)
    now_c = float(r.text)
    ladyden_now_txt = "{:4.1f}".format(now_c)
except:
    ladyden_now_txt = "-nf-"

content = fetch_html(url)
aqi_content = fetch_html(aqi_url)

today_txt  = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[1]/div/a/div/div[2]/span[1]')
today_f    = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[1]/div/a/div/div[2]/span[3]/span/lib-display-unit/span/span[1]')

tonight_txt  = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[2]/div/a/div/div[2]/span[1]')
tonight_f    = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[2]/div/a/div/div[2]/span[3]/span/lib-display-unit/span/span[1]')

tomorrow_txt  = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[3]/div/a/div/div[2]/span[1]')
tomorrow_f    = xpath_value(content, '/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[3]/div/lib-city-today-forecast/div/div[3]/div/a/div/div[2]/span[3]/span[1]/lib-display-unit/span/span[1]')




# today_txt    =    today_txt.replace(' night', ' nt')
# tonight_txt  =  tonight_txt.replace(' night', ' nt')
# tomorrow_txt = tomorrow_txt.replace(' night', ' nt')

today_txt    =    today_txt.replace('Tomorrow night', 'Tom.night')
tonight_txt  =  tonight_txt.replace('Tomorrow night', 'Tom.night')
tomorrow_txt = tomorrow_txt.replace('Tomorrow night', 'Tom.night')


width = max(len(today_txt), len(tonight_txt), len(tomorrow_txt))
now_txt      = "{:<{}}".format("Now", width)
today_txt    = "{:<{}}".format(today_txt, width)
tonight_txt  = "{:<{}}".format(tonight_txt, width)
tomorrow_txt = "{:<{}}".format(tomorrow_txt, width)


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

def abbreviate_string(s):
    if len(s) <= 4:
        return s
    # Step 1: Remove vowels except the first character
    vowels = 'aeiou'
    abbreviated = s[0] + ''.join([char for char in s[1:] if char.lower() not in vowels])
    
    # Step 2: Reduce the length to 4 characters if necessary
    return abbreviated[:4]

# pollen      = svg_value(content,'/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[4]/div[2]/lib-pollen-tile/a/div[3]')
# pollen_type = svg_value(content,'/html/body/app-root/app-today/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[4]/div[2]/lib-pollen-tile/a/div[3]/svg/text[1]')
aqi         = xpath_value(aqi_content,'/html/body/app-root/app-health/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div[1]/div[1]/div/health-air-quality-index/div/div/div[1]/div/div/div/div[2]/div[2]/div[1]/div[2]')
aqi_text    = abbreviate_string(str(xpath_value(aqi_content,'/html/body/app-root/app-health/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div[1]/div[1]/div/health-air-quality-index/div/div/div[1]/div/div/div/div[1]/div[2]/div[2]')))
# print(f"today {today_f} tonight_f {tonight_f} tomorrow {tomorrow_f}")
# print(f"today preicp {today_precip} tonight_precip {tonight_precip} tomorrow precip {tomorrow_precip}")

#print(f"{now_txt}:{now_cs}°C {now_f}°F")
print(f"{today_txt}:{tod_c}°C {today_f}°F {tod_p}%")
print(f"{tonight_txt}:{ton_c}°C {tonight_f}°F {ton_p}%")
print(f"{tomorrow_txt}:{tom_c}°C {tomorrow_f}°F {tom_p}%")

#print("AQ:" + str(aqi_text) + "/" + str(aqi) + " L:"+ladyden_now_txt+" B:"+basement_now_txt)
with open(current_file_directory+'/center_wx.txt', 'w') as file:
    print(f"{now_txt}:{now_cs}°C {now_f}°F", file=file)
    print("AQ:" + str(aqi_text) + "/" + str(aqi) + " L:"+ladyden_now_txt+" B:"+basement_now_txt, file=file)


with open(current_file_directory+'/forecast.pkl', 'rb') as file:
    forecast = pickle.load(file)

today = date.today()
diff = today - forecast['last']
if(diff.days > 1):
    print("fetch error")
else:
    print("hi:", end="")
    for i in forecast['values']:
        print(i[0], end=" ")
    print()
    print("lo:", end="")
    for i in forecast['values']:
        print(i[1], end=" ")
