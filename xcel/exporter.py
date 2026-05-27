import logging
import os
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import URLError

from prometheus_client import CollectorRegistry, Gauge, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

METER_IP = os.environ.get("METER_IP", "10.22.14.23")
METER_PORT = int(os.environ.get("METER_PORT", "8081"))
PORT = int(os.environ.get("PORT", "9101"))
CERT_FILE = os.environ.get("CERT_FILE", "/certs/cert.pem")
KEY_FILE = os.environ.get("KEY_FILE", "/certs/key.pem")
TIMEOUT = float(os.environ.get("METER_TIMEOUT", "5"))

SEP_NS = "{urn:ieee:std:2030.5:ns}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("xcel-exporter")


def build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("ECDHE-ECDSA-AES128-CCM8:@SECLEVEL=0")
    # The meter does a post-handshake renegotiation to request the client cert,
    # which OpenSSL 3.x refuses unless this flag is set.
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    return ctx


SSL_CTX = build_ssl_context()


def fetch_reading(path: str) -> int:
    url = f"https://{METER_IP}:{METER_PORT}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/sep+xml"})
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=TIMEOUT) as r:
        body = r.read()
    root = ET.fromstring(body)
    value_el = root.find(f"{SEP_NS}value")
    if value_el is None or value_el.text is None:
        raise ValueError(f"no <value> in response from {path}")
    return int(value_el.text)


def collect() -> bytes:
    registry = CollectorRegistry()
    up = Gauge("xcel_meter_up", "Whether the meter is reachable and responding", registry=registry)
    power = Gauge("xcel_meter_power_watts", "Real-time power demand in watts", registry=registry)
    energy = Gauge(
        "xcel_meter_energy_wh",
        "Cumulative energy consumption in watt-hours",
        registry=registry,
    )

    ok = True
    try:
        power.set(fetch_reading("/upt/1/mr/1/r"))
    except (URLError, ET.ParseError, ValueError, OSError) as e:
        log.warning("power demand fetch failed: %s", e)
        ok = False

    try:
        energy.set(fetch_reading("/upt/1/mr/3/r"))
    except (URLError, ET.ParseError, ValueError, OSError) as e:
        log.warning("energy fetch failed: %s", e)
        ok = False

    up.set(1 if ok else 0)
    return generate_latest(registry)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found\n")
            return
        body = collect()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main():
    log.info("listening on :%d, meter %s:%d", PORT, METER_IP, METER_PORT)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
