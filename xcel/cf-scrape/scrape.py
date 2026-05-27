#!/usr/bin/env python3
"""
scrape.py — Pulls xcel_meter_power_watts and xcel_meter_energy_wh from the
xcel-exporter Prometheus endpoint and POSTs them to the cf-metrics-server Worker
as denzel_power_watts (W) and denzel_watt_hours (Wh).

Environment variables (all required unless noted):
  METRICS_URL          URL of the Prometheus endpoint  (default: http://xcel-exporter:9101/metrics)
  WORKER_URL           Base URL of the Cloudflare Worker
  API_KEY              X-API-Key value for the Worker
  SENSOR_ID_POWER      sensor_id to use for power demand   (default: denzel_power_watts)
  SENSOR_ID_ENERGY     sensor_id to use for energy total   (default: denzel_watt_hours)
  LOCATION             location label for readings         (default: house)
  SCRAPE_INTERVAL      Seconds between scrapes in loop mode (default: 60)
  RUN_ONCE             Set to "true" to scrape once and exit (default: false)
  LOG_LEVEL            DEBUG | INFO | WARNING | ERROR  (default: INFO)
"""

import os
import sys
import time
import logging
import re
import signal

import requests

# ── Config ────────────────────────────────────────────────────────────────────

METRICS_URL       = os.environ.get("METRICS_URL", "http://xcel-exporter:9101/metrics")
WORKER_URL        = os.environ.get("WORKER_URL", "").rstrip("/")
API_KEY           = os.environ.get("API_KEY", "")
SENSOR_ID_POWER   = os.environ.get("SENSOR_ID_POWER",  "denzel_power_watts")
SENSOR_ID_ENERGY  = os.environ.get("SENSOR_ID_ENERGY", "denzel_watt_hours")
LOCATION          = os.environ.get("LOCATION", "house")
SCRAPE_INTERVAL   = int(os.environ.get("SCRAPE_INTERVAL", "60"))
RUN_ONCE          = os.environ.get("RUN_ONCE", "false").lower() == "true"
LOG_LEVEL         = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("scraper")

# Matches Prometheus lines with or without labels:  metric_name{...} <float>  OR  metric_name <float>
METRIC_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([\d.eE+\-]+)', re.MULTILINE)

# xcel-exporter metric → (sensor_id sent to CF, unit)
WANTED = {
    "xcel_meter_power_watts": (SENSOR_ID_POWER,  "W"),
    "xcel_meter_energy_wh":   (SENSOR_ID_ENERGY, "Wh"),
}

# Only push when the meter is up — avoid storing stale zeros.
METER_UP_METRIC = "xcel_meter_up"

# ── Signal handling ───────────────────────────────────────────────────────────

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down after current cycle.", signum)
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)

# ── Core logic ────────────────────────────────────────────────────────────────

def validate_config():
    errors = []
    if not WORKER_URL:
        errors.append("WORKER_URL is required")
    if not API_KEY:
        errors.append("API_KEY is required")
    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        sys.exit(1)


def fetch_metrics() -> dict[str, float]:
    """Scrape the Prometheus endpoint and return {metric_name: value} for wanted metrics."""
    log.debug("Fetching metrics from %s", METRICS_URL)
    resp = requests.get(METRICS_URL, timeout=10)
    resp.raise_for_status()

    found = {}
    for match in METRIC_RE.finditer(resp.text):
        name, raw_value = match.group(1), match.group(2)
        if name in WANTED or name == METER_UP_METRIC:
            try:
                found[name] = float(raw_value)
            except ValueError:
                log.warning("Could not parse value %r for metric %s", raw_value, name)

    return found


def push_reading(sensor_id: str, value: float, unit: str) -> bool:
    """POST a single reading to the Worker. Returns True on success."""
    payload = {
        "sensor_id": sensor_id,
        "value":     value,
        "unit":      unit,
        "location":  LOCATION,
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key":    API_KEY,
    }
    url = f"{WORKER_URL}/ingest"
    log.debug("POSTing to %s: %s", url, payload)

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            log.info("Stored %s=%.4f%s (id=%s)", sensor_id, value, unit,
                     resp.json().get("id", "?"))
            return True
        else:
            log.error("Worker rejected %s: HTTP %s — %s",
                      sensor_id, resp.status_code, resp.text[:200])
            return False
    except requests.RequestException as exc:
        log.error("Failed to push %s: %s", sensor_id, exc)
        return False


def scrape_and_push():
    """One scrape cycle: fetch metrics and push each wanted value."""
    try:
        metrics = fetch_metrics()
    except requests.RequestException as exc:
        log.error("Failed to fetch metrics from %s: %s", METRICS_URL, exc)
        return

    if metrics.get(METER_UP_METRIC, 0) != 1:
        log.warning("Meter is not up (xcel_meter_up=%s), skipping push",
                    metrics.get(METER_UP_METRIC))
        return

    missing = set(WANTED) - set(metrics)
    if missing:
        log.warning("Metrics not found in response: %s", ", ".join(sorted(missing)))

    for metric_name, (sensor_id, unit) in WANTED.items():
        if metric_name in metrics:
            push_reading(sensor_id, metrics[metric_name], unit)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    validate_config()
    log.info("Scraper starting — metrics_url=%s worker_url=%s interval=%ss",
             METRICS_URL, WORKER_URL, SCRAPE_INTERVAL)

    if RUN_ONCE:
        log.info("RUN_ONCE=true — scraping once then exiting")
        scrape_and_push()
        return

    log.info("Running in loop mode. SIGTERM or Ctrl-C to stop.")
    while not _shutdown:
        scrape_and_push()
        for _ in range(SCRAPE_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Scraper stopped.")


if __name__ == "__main__":
    main()
