#!/usr/bin/env python3
# grab a weeks worth of data form wxunderground, this is really slow so not bothering every 15 min.
# cron this daily at 0400


import pickle, os
from datetime import date
from playwright.sync_api import sync_playwright
url10 = 'https://www.wunderground.com/forecast/us/co/denver' # 10 day 

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url10, wait_until='domcontentloaded')
    
    # Extract content using XPath
    page.wait_for_selector('//html/body/app-root/app-tenday/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[1]/div/lib-forecast-chart/div/div/div/lib-forecast-chart-header-daily/div/div/div/div[2]/a[3]/div/span[1]/span[1]')
    #content10 = page.locator('//html/body/app-root/app-tenday/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[1]/div/lib-forecast-chart/div/div/div/lib-forecast-chart-header-daily/div/div/div/div[2]/a[3]/div/span[1]/span[1]').all_inner_texts()
    #print(content10)
    
    next=[0]*7
    for i in range(0, 7):
        divIdx = i+3;
        a = page.locator('//html/body/app-root/app-tenday/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[1]/div/lib-forecast-chart/div/div/div/lib-forecast-chart-header-daily/div/div/div/div[2]/a['+str(divIdx)+']/div/span[1]/span[1]').all_inner_texts()[0]
        b = page.locator('//html/body/app-root/app-tenday/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div[2]/section/div[3]/div[1]/div/div[1]/div/lib-forecast-chart/div/div/div/lib-forecast-chart-header-daily/div/div/div/div[2]/a['+str(divIdx)+']/div/span[1]/span[3]').all_inner_texts()[0]
        next[i]=[
            a[:-1],
            b[:-1]
        ]
    print(next)

    data={'values':next, 'last':date.today()}

    current_file_directory = os.path.dirname(os.path.abspath(__file__))
    with open(current_file_directory+'/forecast.pkl', 'wb') as file:
        pickle.dump(data, file)

    browser.close()


