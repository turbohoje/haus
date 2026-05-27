# Xcel Itron Gen5 Riva — Prometheus Exporter

## Goal

Build a Dockerized Prometheus exporter that scrapes an Xcel Energy Itron Gen5 Riva smart meter
in real time when Prometheus hits the `/metrics` endpoint. No background polling loop — scrape
on demand, return fresh data every time.

## Background

The meter speaks IEEE 2030.5 (SEP 2.0) over HTTPS on port 8081. It requires mutual TLS using a
self-signed EC cert whose LFDI (first 40 chars of the SHA256 fingerprint) has been registered
with Xcel via the Meters and Devices portal. The meter enforces the cipher suite
`ECDHE-ECDSA-AES128-CCM8`, which is not available in most modern OpenSSL builds — use an Alpine
base image or verify CCM8 support explicitly.

The certs (`cert.pem`, `key.pem`) already exist and are registered. Do not regenerate them.

## Meter Details

- **IP:** `10.22.14.23` (static DHCP lease)
- **Port:** `8081`
- **Protocol:** HTTPS, IEEE 2030.5 / SEP 2.0
- **Required cipher:** `ECDHE-ECDSA-AES128-CCM8`
- **TLS verification:** skip (`--insecure` / `verify=False`) — meter uses self-signed cert
- **Cert files:** mounted into container at `/certs/cert.pem` and `/certs/key.pem`

## Known Working Endpoints

| Path | Description | Unit |
|---|---|---|
| `/upt/1/mr/1/r` | Real-time power demand | W |
| `/upt/1/mr/3/r` | Cumulative consumption | Wh |

Probe `/dcap` first to enumerate all available endpoints — there may be more (voltage, current,
net power with solar, etc). Parse the XML and expose whatever is present.

## Response Format

The meter returns XML. The value lives in a `<value>` tag. Example:

```xml
<MirrorMeterReading xmlns="urn:ieee:std:2030.5:ns">
  <lastUpdateTime>1234567890</lastUpdateTime>
  <MirrorReadingSet>
    <Reading>
      <value>2450</value>
    </MirrorReadingSet>
</MirrorMeterReading>
```

Parse with an XML library, not regex. There may also be a `<multiplier>` and `<powerOfTenMultiplier>`
field that scales the raw value — handle this correctly. Final value = `value * 10^powerOfTenMultiplier`.

## Exporter Behavior

- Scrape the meter **live on each `/metrics` request** — no background thread, no cache
- If the meter is unreachable or returns an error, expose a `xcel_meter_up 0` gauge and return
  200 (don't 500 — let Prometheus handle staleness)
- Timeout per meter request: 5 seconds
- Expose standard Prometheus text format

## Metrics to Expose

```
# HELP xcel_meter_up Whether the meter is reachable and responding
# TYPE xcel_meter_up gauge
xcel_meter_up 1

# HELP xcel_meter_power_watts Real-time power demand in watts
# TYPE xcel_meter_power_watts gauge
xcel_meter_power_watts 2450

# HELP xcel_meter_energy_wh Cumulative energy consumption in watt-hours
# TYPE xcel_meter_energy_wh counter
xcel_meter_energy_wh 14523100
```

Add additional metrics if more endpoints are discovered via `/dcap`.

## Implementation Notes

- Language: Python preferred (requests or httpx for HTTP, xml.etree for parsing, prometheus_client for exposition)
- The `requests` library does not support CCM8 ciphers out of the box — you will need to use a
  custom `HTTPAdapter` with an `SSLContext` that forces the cipher, or shell out to curl if
  Python's OpenSSL doesn't support CCM8
- Alpine-based Docker image confirmed to support the CCM8 cipher — use `python:3.12-alpine` as base
- If using a custom SSLContext: `ssl.SSLContext` → `ctx.set_ciphers('ECDHE-ECDSA-AES128-CCM8')`
  then pass via requests adapter
- Alternatively, subprocess curl is acceptable as a fallback if SSL adapter approach fails

## Docker / Compose

- Image based on `python:3.12-alpine`
- Certs mounted read-only from host: `./certs:/certs:ro`
- Exporter listens on port `9090` (or configurable via env var `PORT`)
- Meter IP/port configurable via env vars `METER_IP` and `METER_PORT` (defaults: `10.22.14.23`, `8081`)
- Restart policy: `unless-stopped`
- Example compose snippet:

```yaml
services:
  xcel-exporter:
    build: .
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./certs:/certs:ro
    environment:
      - METER_IP=10.22.14.23
      - METER_PORT=8081
      - PORT=9090
```

## Validation

Before writing any exporter code, verify the meter is responding by shelling into a container:

```bash
docker run --rm -v $(pwd)/certs:/certs alpine/curl \
  curl --ciphers ECDHE-ECDSA-AES128-CCM8 --insecure \
  --cert /certs/cert.pem --key /certs/key.pem \
  https://10.22.14.23:8081/upt/1/mr/1/r
```

If this returns XML, proceed. If TLS handshake fails, the cert is not yet provisioned by Xcel —
do not proceed until this works.

## Deliverables

1. `exporter.py` — the Prometheus exporter
2. `Dockerfile` — Alpine-based, installs dependencies, runs exporter
3. `docker-compose.yml` — as described above
4. `README.md` — how to drop in certs, run, and verify with `curl localhost:9090/metrics`
