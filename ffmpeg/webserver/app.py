#!/usr/bin/env python3

# app.py
import os
import time
from datetime import datetime

from flask import Flask, send_file, render_template_string
from flask_socketio import SocketIO
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
WD = os.environ.get("WD", os.getcwd())
IMAGE_PATH = os.path.join(WD, "../imgproc", "output.jpg")
HOST, PORT = "0.0.0.0", 3000
MAX_EMIT_HZ = 1            # <= 1 refresh per second

print(f"[BOOT]   WD  = {WD}")
print(f"[BOOT]   IMG = {IMAGE_PATH}")

# --------------------------------------------------------------------------
# Flask & Socket.IO
# --------------------------------------------------------------------------
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # disable HTTP cache
socketio = SocketIO(app, 
                    cors_allowed_origins="*",
                    allow_upgrades=False
)

HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Live Image</title>
<style>body,html{margin:0;background:#000;display:flex;justify-content:center;}
img{width:100%;height:auto;object-fit:contain;}</style></head>
<body><img id="live" src="/image" ><script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/3.1.3/socket.io.min.js"></script>
<script>
 const img=document.getElementById('live'), 
 s=io("/", { transports: ["websocket"], upgrade: false });
 s.on('refresh',()=>{
   console.warn('🟡 refresh event received – reloading image');
   img.src='/image?t='+Date.now();
});
 s.onAny((event, ...args) => {
    console.log(`🔵 socket event: ${event}`, ...args);
}); 
 s.on('connect',   ()=>console.log('🔌 socket connected',s.id));
 s.on('disconnect',()=>console.log('❌ socket disconnected'));
</script></body></html>"""

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    print("[HTTP]   GET /")
    return render_template_string(HTML)

@app.route("/image")
def image():
    now=datetime.now().strftime("%H:%M:%S")
    print(f"[HTTP]   {now} GET /image")
    return send_file(IMAGE_PATH, mimetype="image/jpeg")

# --------------------------------------------------------------------------
# Socket logging
# --------------------------------------------------------------------------
@socketio.on("connect")
def _on_connect():    print(f"[WS]     Browser connected")

@socketio.on("disconnect")
def _on_disconnect(): print("[WS]     Browser disconnected")

# --------------------------------------------------------------------------
# Watchdog with rate-limit
# --------------------------------------------------------------------------
class ChangeHandler(FileSystemEventHandler):
    def periodic_emit(self): #used for testing locally wo modifying a file
        while True: 
            print("test")
            time.sleep(2)
            self.on_modified(type("Event", (), {"src_path": IMAGE_PATH})())  # Simulate a file change event


    def __init__(self):
        super().__init__()
        self.last_emit = 0.0          # seconds from time.monotonic()
        # threading.Thread(target=self.periodic_emit, daemon=True).start()
        # print("ch init")

    def on_modified(self, event):
        if event.src_path != IMAGE_PATH:
            return

        now = time.monotonic()
        if now - self.last_emit < 1 / MAX_EMIT_HZ:
            print("[WATCH]  Skipping emit (rate-limited)")
            return                   # too soon – ignore this event

        self.last_emit = now
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        size = os.path.getsize(IMAGE_PATH)
        print(f"[WATCH]  {ts} modified: {size} bytes – emitting refresh")
        socketio.emit("refresh", namespace="/", callback=print)

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
if __name__ == "__main__":
    observer = Observer()
    observer.schedule(ChangeHandler(), os.path.dirname(IMAGE_PATH), recursive=False)

    observer.start()
    print(f"[BOOT]   Watching {IMAGE_PATH}")
    print(f"[BOOT]   http://{HOST}:{PORT}")
    try:
        socketio.run(app, host=HOST, port=PORT, debug=False)
    finally:
        observer.stop()
        observer.join()