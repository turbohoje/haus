#!/bin/bash

#clear screen
dd if=/dev/zero count=10000 bs=1024 > /dev/fb0

#un=ENV
#pass=ENV
nvr=10.22.14.9

mkdir -p ./imgproc

while [ 1 ]; do
    # nvr images, (slower)
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/0.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o imgproc/1.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o imgproc/2.jpg
    #time curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/3.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=4&user=${un}&password=${pass}" -o imgproc/4.jpg
    #direct from camera

    min=$(date +"%M")
    sec=$(date +"%S")
    curl -k -s "https://10.22.14.47/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/0.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o imgproc/1.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o imgproc/2.jpg & 
    curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/3.jpg & 
    curl -k -s "https://10.22.14.48/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/4.jpg &
    if (( min == 0 )) && (( sec < 5 )); then
        echo "GETTING DATA"
        exit;
        #comes from https://open-meteo.com/en/docs#current=temperature_2m,relative_humidity_2m,apparent_temperature&hourly=&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max&location_mode=csv_coordinates&csv_coordinates=39.7500028,-104.9739337,,America%2FDenver&wind_speed_unit=kn&forecast_days=1&models=best_match
        curl -s "https://api.open-meteo.com/v1/forecast?latitude=39.7500028&longitude=-104.9739337&current=temperature_2m,relative_humidity_2m,apparent_temperature&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max&wind_speed_unit=kn&timezone=America%2FDenver&forecast_days=1&models=best_match" > wx.json &
    fi
    oat_c=$(curl -s "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=112&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature")
    oat_f=$(echo "($oat_c * 9/5) + 32" | bc)
    date=$(date +"%a %b %d %H:%M:%S")
    echo "$date" > screen.txt
    echo "OAT $oat_c°C / $oat_f°F" >> screen.txt
    cat wx.json | jq -j '.daily.temperature_2m_min[0],"°C ",.daily.temperature_2m_max[0],"°C\n",.daily.wind_speed_10m_max[0],"kt ",.daily.precipitation_probability_max[0]," \\%precip"'  >> screen.txt
    
    wait
    small_dims="scale=640:360"
    
    testargs="[0:v]crop=2520:1380:1326:365,scale=1920:1080[bg];[1:v]$small_dims[1];[2:v]$small_dims[2];[3:v]$small_dims[3];[1][2][3]vstack=inputs=3[stk];[bg][stk]overlay"
    testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/OpenSansEmoji.ttf:textfile=screen.txt:fontcolor=white:fontsize=64:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=0:line_spacing=20'"

    ffmpeg -err_detect aggressive -fflags discardcorrupt  \
    -i "imgproc/3.jpg" \
    -i "imgproc/0.jpg" \
    -i "imgproc/4.jpg" \
    -i "imgproc/1.jpg" \
    -filter_complex $testargs \
    -vframes 1 \
    -pix_fmt bgra -f fbdev /dev/fb0
    
    echo "done"
    
done