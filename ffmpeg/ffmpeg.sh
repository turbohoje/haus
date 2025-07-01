#!/bin/bash
#https://reolink.com/wp-content/uploads/2017/01/Reolink-CGI-command-v1.61.pdf
#https://camlytics.com/camera/reolink

wd=/home/turbohoje/haus/ffmpeg
cd $wd

#clear the frame buffer w zeros
dd if=/dev/zero count=10000 bs=1024 > /dev/fb0

  # echo "output to ffplay"
  # # osx ouput
  # ffmpeg -err_detect aggressive -fflags discardcorrupt  \
  # -i "rtsp://$un:$pass@$ip:554/h264Preview_04_sub" \
  # -i "rtsp://$un:$pass@$ip:554/h264Preview_01_sub" \
  # -i "rtsp://$un:$pass@$ip:554/h264Preview_05_sub" \
  # -i "rtsp://$un:$pass@$ip:554/h264Preview_02_sub" \
  # -filter_complex $testargs \
  # -f matroska - | ffplay -i -

#un=ENV
#pass=ENV
ip=10.22.14.9

while [ 1 ]; do

  date=$(date +"%a %b%d  %H:%M:%S")
  echo "$date" > $wd/center.txt
  cat $wd/center_wx.txt >> $wd/center.txt
  

  small_dims="scale=640:360"
  testargs="[0:v]scale=-1:1080,crop=1280:1080:(in_w-1280)/2:0[bg];[1:v]$small_dims[1];[2:v]crop=2520:1380:1326:100,$small_dims[2];[3:v]$small_dims[3];[1][2][3]vstack=inputs=3[stk];[stk][bg]hstack"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/center.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw-670:y=0:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/wx_forecast_hour.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=0:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/wx_forecast_week.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=180:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/imgproc/rockiesgame.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=10:y=h-th-10:line_spacing=20:expansion=none'"



  # # fb nuc output
  #   ffmpeg -err_detect aggressive -fflags discardcorrupt  \
  #   -i "$wd/imgproc/random.jpg" \
  #   -i "$wd/imgproc/0.jpg" \
  #   -i "$wd/imgproc/3.jpg" \
  #   -i "$wd/imgproc/1.jpg" \
  #   -filter_complex $testargs \
  #   -vframes 1 \
  #   -pix_fmt bgra -f fbdev /dev/fb0 > /dev/null 2>&1 || stdlog "ffmpeg fail"

  # # output to file 
  #  ffmpeg -err_detect aggressive -fflags discardcorrupt  \
  #   -i "$wd/imgproc/random.jpg" \
  #   -i "$wd/imgproc/0.jpg" \
  #   -i "$wd/imgproc/3.jpg" \
  #   -i "$wd/imgproc/1.jpg" \
  #   -filter_complex $testargs \
  #   -frames:v 1 -q:v 2 -y "$wd/imgproc/output.jpg"

  # output to both at once
    ffmpeg -err_detect aggressive -fflags discardcorrupt  \
    -i "$wd/imgproc/random.jpg" \
    -i "$wd/imgproc/0.jpg" \
    -i "$wd/imgproc/3.jpg" \
    -i "$wd/imgproc/1.jpg" \
    -filter_complex "${testargs},split=2[fb][jpg]" \
    -map "[fb]"  -vframes 1 -pix_fmt bgra -f fbdev /dev/fb0 \
    -map "[jpg]" -frames:v 1 -q:v 2 -y "$wd/imgproc/output.jpg" 

done