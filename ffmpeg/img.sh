#!/bin/bash

#clear screen
dd if=/dev/zero count=10000 bs=1024 > /dev/fb0

#un=ENV
#pass=ENV
nvr=10.22.14.9

mkdir -p ./imgproc

#while [ 1 ]; do
    # nvr images, (slower)
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/0.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o imgproc/1.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o imgproc/2.jpg
    #time curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/3.jpg
    #time curl -k -s "https://${ip}/cgi-bin/api.cgi?cmd=Snap&channel=4&user=${un}&password=${pass}" -o imgproc/4.jpg
    #direct from camera

    curl -k -s "https://10.22.14.47/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/0.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o imgproc/1.jpg &
    curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o imgproc/2.jpg & 
    curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/3.jpg & 
    curl -k -s "https://10.22.14.48/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/4.jpg &

    oat_c=$(curl -s "http://10.22.14.4:3480/data_request?id=variableget&DeviceNum=112&serviceId=urn:upnp-org:serviceId:TemperatureSensor1&Variable=CurrentTemperature")
    oat_f=$(echo "($oat_c * 9/5) + 32" | bc)


    wait
    small_dims="scale=640:360"
    #,scale=1920:1080
    testargs="[0:v]crop=2520:1380:1326:365,scale=1920:1080[bg];[1:v]$small_dims[1];[2:v]$small_dims[2];[3:v]$small_dims[3];[1][2][3]vstack=inputs=3[stk];[bg][stk]overlay"
    testargs="$testargs,drawtext=fontfile=/home/turbohoje/haus/ffmpeg/Arial.ttf:text='$oat_c°C/$oat_f°F':fontcolor=white:fontsize=64:box=1:boxcolor=black@0.4:boxborderw=10:x=1500:y=0"

    ffmpeg -err_detect aggressive -fflags discardcorrupt  \
    -i "imgproc/3.jpg" \
    -i "imgproc/0.jpg" \
    -i "imgproc/4.jpg" \
    -i "imgproc/1.jpg" \
    -filter_complex $testargs \
    -vframes 1 \
    -pix_fmt bgra -f fbdev /dev/fb0
    
    echo "done"
    
# done