#!/bin/bash
#https://reolink.com/wp-content/uploads/2017/01/Reolink-CGI-command-v1.61.pdf
#https://camlytics.com/camera/reolink

#clear the frame buffer w zeros
dd if=/dev/zero count=10000 bs=1024 > /dev/fb0

#un=ENV
#pass=ENV
ip=10.22.14.9

#-loglevel 99 -report -v 9 \
#args="[0:v]scale=960:540[one];[1:v]scale=960:540[two];[2:v]scale=960:540[three];[3:v]scale=960:540[four];[one][two]hstack=inputs=2[top];[three][four]hstack=inputs=2[bottom];[top][bottom]vstack=inputs=2"

args="[0:v][1:v]hstack=inputs=2[top];[2:v][3:v]hstack=inputs=2[bottom];[top][bottom]vstack=inputs=2"


#ffmpeg   \
#-i "rtmp://$ip/bcs/channel0_sub.bcs?channel=0&stream=1&user=$un&password=$pass" \
#-i "rtmp://$ip/bcs/channel1_sub.bcs?channel=0&stream=1&user=$un&password=$pass" \
#-i "rtmp://$ip/bcs/channel2_sub.bcs?channel=0&stream=1&user=$un&password=$pass" \
#-i "rtmp://$ip/bcs/channel3_sub.bcs?channel=0&stream=1&user=$un&password=$pass" \
#-filter_complex $args \
#-pix_fmt bgra -f fbdev /dev/fb0

/h264Preview_01_sub


ffmpeg -err_detect aggressive -fflags discardcorrupt  \
-i "rtsp://$un:$pass@$ip:554/h264Preview_01_sub" \
-i "rtsp://$un:$pass@$ip:554/h264Preview_02_sub" \
-i "rtsp://$un:$pass@$ip:554/h264Preview_04_sub" \
-i "rtsp://$un:$pass@$ip:554/h264Preview_03_sub" \
-filter_complex $args \
-pix_fmt bgra -f fbdev /dev/fb0

