# tvsnap — the TV display data as a JSON snapshot on Cloudflare

Publishes a ~700 byte JSON document of what the ffmpeg display already shows —
indoor/outdoor temps, AQI, the hourly and weekly forecast, and Justin's plus the
shared calendar rows — to a Cloudflare Worker backed by R2, behind a shared key.

The consumer is the Venu 2 Plus watch face in
[`garmin_watch`](https://github.com/turbohoje/garmin_watch); see `watch/`.

```
fetch_wx.py    ──> ffmpeg/snap_wx.json   ─┐
fetch_cal.py   ──> ffmpeg/snap_cal.json  ─┼─> publish_snapshot.py ──PUT──> worker ──> R2
fetch_metar.py ──> tvsnap/snap_metar.json─┘                                  ▲
                                                                       GET   │
                                                                 watch face ─┘
```

## Why a separate publisher

`fetch_wx.py`, `fetch_cal.py` and `fetch_metar.py` run as independent cron jobs.
None has the others' data, so if each PUT to a single R2 object they would take
turns clobbering the rest of it. They write local JSON sidecars instead and
`publish_snapshot.py` merges them into one document.

`fetch_metar.py` lives here rather than in `ffmpeg/` because the airport data is
the one part of the payload that is **not** on the TV — nothing in the display
produces or consumes it, so there is no overlay for it to be a by-product of.

Both sidecars inherit the display's sticky-on-failure rule: a failed scrape or
calendar fetch exits before writing, so the previous file stays. That means a
sidecar can be arbitrarily old while still parsing fine, which is why each
source's own timestamp is carried through as `wx_ts` / `cal_ts` — without them a
stale half is indistinguishable from a fresh one on the watch.

## The payload

Sizes measured on real data: 486 B of weather, 201 B of calendar, 146 B of
airports, 858 B merged.

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
  "both": [{"s": 1788674400, "all": 1, "t": "UK Trip"}, ...],
  "metar_ts": 1788714557,    // when fetch_metar.py last succeeded
  "metar": [{"id": "KLMO", "cat": "VFR", "dir": 50, "spd": 3, "obs": 1788713700},
            {"id": "KTEX", "cat": "VFR", "dir": 0,  "spd": 0, "obs": 1788713700}]
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
- **`dir` is an integer in degrees, or the string `"VRB"`.** That mixed type is
  what the METAR itself reports for a variable wind, and it is passed through
  rather than flattened. Any consumer has to type-check it — on the watch that
  means an `instanceof Lang.Number` test, not a bare `.format()`.
- **`gst` is present only when gusting**, and `cat` only when the station
  reported a usable one. Absent keys mean "not applicable", the same rule
  `temp_c` uses for a sensor that did not report.
- **Flight category is collapsed to `VFR` / `IFR`.** The API reports four
  states; `MVFR` and `LIFR` both fold into `IFR` here.
- **Stations come back in `STATIONS` order**, not the API's, so the watch can
  draw rows without sorting. A station that did not report is dropped from the
  list rather than sent empty.

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
*/10   * * * * /home/turbohoje/haus/tvsnap/fetch_metar.py >/dev/null
1-56/5 * * * * /home/turbohoje/haus/tvsnap/publish_snapshot.py >/dev/null
```

`fetch_metar.py` is on its own 10-minute cycle rather than the display's 5.
METARs are issued hourly around :55 with SPECIs in between when conditions
change, and the Aviation Weather Center sets `cache-control: max-age=60`, so
polling harder returns the same bytes. Running on the `:10` boundary leaves the
sidecar about a minute old when the publisher next fires.

It exits non-zero and publishes nothing on a transport failure; the previous
snapshot stays up and the next tick retries. A missing sidecar is not fatal —
it publishes the half it has, and the missing `wx_ts`/`cal_ts` says which.

## Testing without deploying

`worker.mjs` runs under plain node with two stubs (`crypto.subtle.timingSafeEqual`
is a Workers extension, and `env.SNAP` is R2). Point `WORKER_URL` at a local
bridge and `publish_snapshot.py` exercises the real worker end to end — that is
how the 709-byte figure above was measured.

## Status

Verified on the haus box: the wx and cal sidecars are written without changing a
single byte of the six overlay files; the worker's routing, auth, size and JSON
validation paths pass 12 unit tests; `fetch_metar.py`'s parsing passes 12 cases
covering variable wind, gusts, calm, each flight category, a missing station and
an empty 204; the publisher's success, missing-sidecar, stale-sidecar,
wrong-key and unreachable-host paths all behave.

Not yet verified: the actual Cloudflare deploy (needs the API token), and
anything on the watch — see `watch/README.md`.
