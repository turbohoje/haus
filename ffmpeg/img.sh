#!/bin/bash


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

    time curl -k -s "https://10.22.14.47/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/0.jpg &
    time curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=1&user=${un}&password=${pass}" -o imgproc/1.jpg &
    time curl -k -s "https://${nvr}/cgi-bin/api.cgi?cmd=Snap&channel=2&user=${un}&password=${pass}" -o imgproc/2.jpg & 
    time curl -k -s "https://10.22.14.49/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/3.jpg & 
    time curl -k -s "https://10.22.14.48/cgi-bin/api.cgi?cmd=Snap&channel=0&user=${un}&password=${pass}" -o imgproc/4.jpg &

    wait

    testargs="[0:v]crop=900:576:200:0,scale=1920:1080[bg];[1:v]scale=640:480[1];[2:v]scale=640:480[2];[3:v]scale=640:480[3];[1][2][3]vstack=inputs=3[stk];[bg][stk]overlay"
    
    ffmpeg -err_detect aggressive -fflags discardcorrupt  \
    -i "imgproc/3.jpg" \
    -i "imgproc/0.jpg" \
    -i "imgproc/4.jpg" \
    -i "imgproc/1.jpg" \
    -filter_complex $testargs \
    -vframes 1 \
    -f matroska - | ffplay -i -
    
    #-pix_fmt bgra -f fbdev /dev/fb0
    
    echo "done"
    
#done