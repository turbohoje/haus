# xcel-exporter

Prometheus exporter for the Xcel Energy Itron Gen5 Riva smart meter. Scrapes
the meter live on each `/metrics` request — no background polling.

## Metrics

| Metric | Type | Unit | Source |
|---|---|---|---|
| `xcel_meter_up` | gauge | 0/1 | derived from scrape outcome |
| `xcel_meter_power_watts` | gauge | W | `/upt/1/mr/1/r` (Instantaneous Demand) |
| `xcel_meter_energy_wh` | gauge | Wh | `/upt/1/mr/3/r` (Current Summation Delivered) |

`xcel_meter_energy_wh` is exposed as a gauge rather than a counter because the
meter reports a cumulative lifetime reading the exporter doesn't own — use
`increase()` in PromQL to get consumption over a window.

## Setup

Drop the meter certs at the project root:

```
xcel/
├── cert.pem
└── key.pem
```

Both are `.gitignore`d. They get baked into the image at build time (`COPY cert.pem /certs/...`), so the image is self-contained.

## Run

```
docker compose up -d --build
curl -s localhost:9101/metrics | grep ^xcel_
```

Expected output:

```
xcel_meter_up 1.0
xcel_meter_power_watts 1066.0
xcel_meter_energy_wh 3.6964002e+07
```

## Configuration

Environment variables (all optional, defaults shown):

| Var | Default |
|---|---|
| `METER_IP` | `10.22.14.23` |
| `METER_PORT` | `8081` |
| `PORT` | `9101` |
| `CERT_FILE` | `/certs/cert.pem` |
| `KEY_FILE` | `/certs/key.pem` |
| `METER_TIMEOUT` | `5` (seconds) |

## TLS notes

The meter speaks IEEE 2030.5 / SEP 2.0 with mutual TLS and requires the
`ECDHE-ECDSA-AES128-CCM8` cipher. Three things have to be true for the
handshake to succeed against OpenSSL 3.x (what ships in `python:3.12-alpine`):

1. **TLS 1.2 only** — CCM8 is a TLS 1.2 cipher; without pinning, OpenSSL
   negotiates 1.3 and the meter aborts.
2. **`@SECLEVEL=0`** — OpenSSL 3.x's default security level rejects CCM8
   (8-byte MAC is considered weak).
3. **`OP_LEGACY_SERVER_CONNECT`** — the meter does a post-handshake
   renegotiation to request the client cert; OpenSSL 3.x refuses by default.

All three are set in `build_ssl_context()` in `exporter.py:30`.
