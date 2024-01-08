#!/bin/bash

wd=/home/turbohoje/haus/ffmpeg
cd $wd
#clear screen
dd if=/dev/zero count=10000 bs=1024 > /dev/fb0

#un=ENV
#pass=ENV
nvr=10.22.14.9

mkdir -p $wd/imgproc

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
    curl -k -s "https://10.22.14.47/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o $wd/imgproc/0.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o $wd/imgproc/1.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o $wd/imgproc/2.jpg & 
    curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o $wd/imgproc/3.jpg & 
    curl -k -s "https://10.22.14.48/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o $wd/imgproc/4.jpg &
    if [[ $((min % 15)) -eq 0 ]] && [[ $sec -lt 5 ]]; then
        echo "GETTING HOURLY WX DATA"
        ./fetch_wx.py > $wd/wx.txt
    fi
    #oat_c=$(curl -s "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=112&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature")
    #oat_f=$(echo "($oat_c * 9/5) + 32" | bc)
    date=$(date +"%a %b %d %H:%M:%S")
    echo "$date" > $wd/screen.txt
    #echo "OAT $oat_c°C / $oat_f°F" >> screen.txt
    
    wait
    small_dims="scale=640:360"
    
    testargs="[0:v]crop=2520:1380:1326:365,scale=1920:1080[bg];[1:v]$small_dims[1];[2:v]$small_dims[2];[3:v]$small_dims[3];[1][2][3]vstack=inputs=3[stk];[bg][stk]overlay"
    testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/OpenSansEmoji.ttf:textfile=$wd/screen.txt:fontcolor=white:fontsize=64:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=0:line_spacing=20:expansion=none'"
    testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/wx.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=80:line_spacing=20:expansion=none'"

    echo $testargs

    ffmpeg -err_detect aggressive -fflags discardcorrupt  \
    -i "$wd/imgproc/3.jpg" \
    -i "$wd/imgproc/0.jpg" \
    -i "$wd/imgproc/4.jpg" \
    -i "$wd/imgproc/1.jpg" \
    -filter_complex $testargs \
    -vframes 1 \
    -pix_fmt bgra -f fbdev /dev/fb0 > /dev/null
    
    echo "done"
done