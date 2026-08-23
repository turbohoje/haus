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

# Background poller for live power consumption from the local Xcel meter
# exporter. Runs independently of the (blocking) ffmpeg loop with a generous
# timeout, and only overwrites power.txt when it gets a real reading, so a slow
# or missed fetch leaves the last good value on screen instead of blanking it.
power_poller() {
  while true; do
    watts=$(curl -s --max-time 8 http://10.22.14.2:9101/metrics 2>/dev/null \
            | awk '/^xcel_meter_power_watts /{print $2; exit}')
    if [ -n "$watts" ]; then
      printf "%.0f W\n" "$watts" > "$wd/power.txt"
    fi
    sleep 5
  done
}
power_poller &
trap 'kill %1 2>/dev/null' EXIT

while [ 1 ]; do
  sleep 0.1
  date=$(date +"%a %b%d  %H:%M:%S")
  echo "$date" > $wd/center.txt
  cat $wd/center_wx.txt >> $wd/center.txt

  small_dims="scale=640:360"
  testargs="[0:v]scale=1280:1080:force_original_aspect_ratio=increase,crop=1280:1080:(in_w-1280)/2:(in_h-1080)/2[bg];[1:v]$small_dims[1];[2:v]crop=2520:1380:1326:100,$small_dims[2];[3:v]$small_dims[3];[1][2][3]vstack=inputs=3[stk];[stk][bg]hstack"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/center.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw-670:y=0:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/wx_forecast_hour.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=0:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/wx_forecast_week.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw:y=180:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/imgproc/rockiesgame.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=10:y=h-th-10:line_spacing=20:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/power.txt:fontcolor=white:fontsize=44:box=1:boxcolor=black@0.4:boxborderw=10:x=10:y=0:line_spacing=20:expansion=none'"
  # Next 4 calendar events along the bottom of the 1280px photo panel, written
  # by fetch_cal.py on cron: jenny on the panel's left edge, justin
  # right-anchored, 29 chars each so the two boxes clear each other. Rows both
  # calendars share go in cal_both.txt, centered on the row above and free to
  # use the panel's full 62-char width -- a third box will not fit alongside
  # the other two. These run at fontsize 33 (3/4 of the other overlays) with
  # line_spacing cut to match, since drawtext's line pitch here is 30+spacing
  # and leaving it at 20 would shrink the width but not the height.
  # The 160 offset puts cal_both's box bottom at y=930, clearing a
  # bottom-anchored 3-line side block (top at 950) -- the most either side can
  # have while cal_both.txt is non-empty.
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/cal_jenny.txt:fontcolor=white:fontsize=33:box=1:boxcolor=black@0.4:boxborderw=10:x=650:y=h-th-10:line_spacing=10:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/cal_justin.txt:fontcolor=white:fontsize=33:box=1:boxcolor=black@0.4:boxborderw=10:x=w-tw-10:y=h-th-10:line_spacing=10:expansion=none'"
  testargs="$testargs,drawtext='fontfile=/home/turbohoje/haus/ffmpeg/AndaleMono.ttf:textfile=$wd/cal_both.txt:fontcolor=white:fontsize=33:box=1:boxcolor=black@0.4:boxborderw=10:x=640+(1280-tw)/2:y=h-th-160:line_spacing=10:expansion=none'"



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