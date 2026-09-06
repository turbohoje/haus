# tvsnap — the TV display data as a JSON snapshot on Cloudflare

Publishes a ~700 byte JSON document of what the ffmpeg display already shows —
indoor/outdoor temps, AQI, the hourly and weekly forecast, and Justin's plus the
shared calendar rows — to a Cloudflare Worker backed by R2, behind a shared key.

The consumer is the Venu 2 Plus watch face in
[`garmin_watch`](https://github.com/turbohoje/garmin_watch); see `watch/`.

```
fetch_wx.py  ──> ffmpeg/snap_wx.json  ─┐
                                       ├─> publish_snapshot.py ──PUT──> worker ──> R2
fetch_cal.py ──> ffmpeg/snap_cal.json ─┘                                  ▲
                                                                    GET   │
                                                              watch face ─┘
```

## Why a separate publisher

`fetch_wx.py` and `fetch_cal.py` run as independent cron jobs. Neither has the
other's data, so if each PUT to a single R2 object they would take turns
clobbering half of it. They write local JSON sidecars instead and
`publish_snapshot.py` merges the two and sends one document.

Both sidecars inherit the display's sticky-on-failure rule: a failed scrape or
calendar fetch exits before writing, so the previous file stays. That means a
sidecar can be arbitrarily old while still parsing fine, which is why each
source's own timestamp is carried through as `wx_ts` / `cal_ts` — without them a
stale half is indistinguishable from a fresh one on the watch.

## The payload

Sizes measured on real data: 486 B of weather, 201 B of calendar, 709 B merged.

```json
{
  "ts": 1788712994,          // when this document was published
  "wx_ts": 1788712804,       // when fetch_wx.py last succeeded
  "temp_c": {"basement": 25.0, "ladyden": 28.0, "master": 24.8,
             "living": 25.3, "attic": 35.6, "out": 25.0},
  "aqi": {"v": 27, "label": "Good"},
  "hourly": [{"label": "Today", "f": 92, "c": 33.3, "precip": 21}, ...],
  "week": [{"d": "T", "hi": 89, "lo": 61}, ...],
  "cal_ts": 1788712804,      // when fetch_cal.py last succeeded
  "justin": [{"s": 1788789600, "all": 0, "t": "pay jim"}, ...],
  "both": [{"s": 1788674400, "all": 1, "t": "UK Trip"}, ...]
}
```

Choices worth knowing:

- **Temps are °C**, matching the display, and a sensor that did not report is
  **omitted** rather than sent as a sentinel — `-nf-` on screen is a missing key
  here, so the watch can tell "no reading" from a real 0.0.
- **`s` is epoch seconds, not ISO 8601.** Monkey C has no date parser but takes
  an epoch straight into `Time.Moment`, so this saves the watch both bytes and
  the parsing it cannot do. All-day events pin to local midnight and set
  `all: 1`.
- **Titles are full length** (bounded at 60 chars). The 22/55-char truncation in
  the overlays is an artifact of the 1280px panel; the watch has its own width
  and decides its own truncation.
- **`week` is omitted** when `forecast.pkl` is more than a day stale — the same
  check the `wx_forecast_week.txt` overlay makes.
- **Jenny's calendar is not published.** Only `cal_justin` rows and the shared
  `cal_both` rows leave the house.

## API

| Route | Auth | Behavior |
|---|---|---|
| `GET /snapshot` | `X-API-Key` | The current document, `Content-Type: application/json`. 404 before the first publish. |
| `PUT /snapshot` | `X-API-Key` | Replaces it. 400 on invalid JSON, 413 over 32 KB. |
| `GET /health` | none | `{"status":"ok"}` |

Storage is one R2 object, last-write-wins, no history — the watch only ever
wants what is true now, and the publisher re-sends every 5 minutes anyway.

**One shared key does both read and write**, so a leaked key is also a write
capability. That was the deliberate call: the key ships compiled into a
sideloaded watch app, where a separate read-only key would have been exactly as
exposed, and the sensitive half of this data (calendar titles) leaks on read
alone. Rotating means changing `API_KEY` in `.env`, re-running `deploy.sh`, and
rebuilding the face. The key is compared in constant time.

## Deploying

The haus box has no node, wrangler or terraform — only curl and python3 — so
`deploy.sh` drives `api.cloudflare.com` directly rather than following
`~/cf_metrics`' terraform + wrangler pattern. It is idempotent; re-run it to
push a `worker.mjs` change or rotate the key.

```sh
cp env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # the shared key
$EDITOR .env                                                    # token, account, key
./deploy.sh
```

The API token needs **Workers R2 Storage: Edit**, **Workers Scripts: Edit** and
**Account Settings: Read** (My Profile → API Tokens → Create Token). R2 has to
be enabled on the account once in the dashboard first — the free tier still
wants a payment method on file.

`deploy.sh` creates the `haus-tvsnap` R2 bucket, uploads the worker with its R2
and secret bindings, enables the workers.dev route, and writes the resulting
`WORKER_URL` back into `.env`.

## Cron

`publish_snapshot.py` needs both sidecars fresh, so it runs a minute after the
two fetches. Those are on `*/5`, so:

```cron
1-56/5 * * * * /home/turbohoje/haus/tvsnap/publish_snapshot.py >/dev/null
```

It exits non-zero and publishes nothing on a transport failure; the previous
snapshot stays up and the next tick retries. A missing sidecar is not fatal —
it publishes the half it has, and the missing `wx_ts`/`cal_ts` says which.

## Testing without deploying

`worker.mjs` runs under plain node with two stubs (`crypto.subtle.timingSafeEqual`
is a Workers extension, and `env.SNAP` is R2). Point `WORKER_URL` at a local
bridge and `publish_snapshot.py` exercises the real worker end to end — that is
how the 709-byte figure above was measured.

## Status

Verified on the haus box: both sidecars are written without changing a single
byte of the six overlay files; the worker's routing, auth, size and JSON
validation paths pass 12 unit tests; the publisher's success, missing-sidecar,
stale-sidecar, wrong-key and unreachable-host paths all behave.

Not yet verified: the actual Cloudflare deploy (needs the API token), and
anything on the watch — see `watch/README.md`.
