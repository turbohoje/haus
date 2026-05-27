# ffmpeg display service

Composites the security-camera images plus several text overlays into a single
frame, written every loop to both the Linux framebuffer (`/dev/fb0`, the
physical display) and to `imgproc/output.jpg` (for the web view).

Run as a systemd service: `ffmpeg.service` → `ExecStart=ffmpeg.sh`.

## Render loop (`ffmpeg.sh`)

The main `while` loop, roughly once per pass:

1. Writes the current date + weather line into `center.txt`.
2. Builds an ffmpeg `filter_complex` (`testargs`) that:
   - takes 4 input JPEGs from `imgproc/` (`random.jpg`, `0.jpg`, `3.jpg`,
     `1.jpg`),
   - scales/crops one as a 1280×1080 background and stacks the other three down
     the left,
   - overlays text from several `*.txt` files via `drawtext`.
3. Runs ffmpeg once with `split=2`, mapping one copy to the framebuffer
   (`-f fbdev /dev/fb0`) and one to `imgproc/output.jpg`.

ffmpeg runs **synchronously** each pass, so anything done inline in the loop
blocks the next frame.

### Text overlays (`drawtext` source files)

Each overlay reads a plain text file (`expansion=none`, so contents are drawn
literally). These files are produced by other processes/scripts:

| File                      | Position        | Content                          |
|---------------------------|-----------------|----------------------------------|
| `center.txt`              | top, right-ish  | date + `center_wx.txt` appended  |
| `wx_forecast_hour.txt`    | top right       | hourly weather forecast          |
| `wx_forecast_week.txt`    | right, lower    | weekly weather forecast          |
| `imgproc/rockiesgame.txt` | bottom left     | Rockies game info                |
| `power.txt`               | top left        | live power draw, e.g. `2196 W`   |

The render loop only reads these files. If a file is stale or empty the overlay
just shows the old/blank text — it never blocks the loop.

## Power overlay (`power.txt`)

Live whole-home power comes from a local Xcel-meter Prometheus exporter at
`http://10.22.14.2:9101/metrics`, metric `xcel_meter_power_watts`.

A **background poller** (`power_poller`) handles this, started once before the
render loop and killed on exit via a `trap`:

- polls the exporter every ~5s with `curl --max-time 8`,
- parses the metric value with `awk`,
- writes `power.txt` **only when it gets a real reading**
  (`printf "%.0f W"`).

Because it only writes on success, a slow or missed fetch leaves the last good
value on screen instead of blanking it. Running in the background means a slow
meter response never stalls frame rendering.

### Why it's structured this way

The fetch was originally inline in the render loop with `--max-time 2`, writing
`-- W` on any failure. That blanked the reading on every slow response **and**
stalled the frame for up to 2s. Moving it to a background thread with a longer
timeout and sticky-on-failure writes fixed the frequent `-- W` flicker.

Note: after a restart, `power.txt` shows its last value until the poller's first
successful fetch (within ~8s), then updates.
