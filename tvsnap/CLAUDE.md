# tvsnap — context for agents

Read `README.md` first for what this is and how the pieces fit. This file is the
part that is not obvious from the code: what is actually true right now, what has
been verified, and which invariants will silently break the TV if you touch them.

## State as of 2026-09-06

**Deployed and serving.** `https://haus-tvsnap.justin-476.workers.dev` — worker
`haus-tvsnap` plus the `haus-tvsnap` R2 bucket, both created by `deploy.sh` on
2026-09-06. The publisher is succeeding on cron; the live payload is 859 bytes.

Credentials in `.env` were supplied by the user, not found on the box. Getting a
working one took three tries, and the failures are worth knowing:

- A token whose every permission group ends in `Read` clears `deploy.sh`'s
  preflight and dies at the first mutation with 403 / code 10000
  "Authentication error". Listing R2 buckets and listing worker scripts are
  reads; they prove nothing about deploy rights.
- **Account-owned tokens (`cfat_`) fail `/user/tokens/verify`** with 1000
  "Invalid API Token" even when they work everywhere else. `deploy.sh` therefore
  preflights with `/accounts/$CF_ACCOUNT_ID`, which validates the token and the
  account id together. Do not "fix" it back. A user-owned token (`cfut_`) does
  verify, so both kinds work with the current preflight.
- The account's `tf-vai-lappy` token would also have deployed, but carries
  write-everything including Billing and Account API Tokens. Not used, and not
  something to park in a plaintext `.env` beside a cron job.

**R2 was already enabled** — the account has the unrelated buckets `img` and
`marmot`, and the workers `cdn` and `metrics-server` — so the free-tier
payment-method wall never came up.

**Cloudflare's bot check blocks `Python-urllib`.** The publisher's PUT was
rejected at the edge with 403 / error 1010, before the worker ran, purely
because urllib sends `User-Agent: Python-urllib/3.10`. Confirmed by swapping
only the UA: `Python-urllib/3.10` → 403, anything else → the real response.
`publish_snapshot.py` now sends `User-Agent: haus-tvsnap/1.0`. Any future
Python HTTP client pointed at this worker needs the same, and the symptom looks
exactly like a broken deploy — 1010 is an edge block, not a worker response.

**Cron is installed:**

```cron
*/10   * * * * /home/turbohoje/haus/tvsnap/fetch_metar.py >/dev/null
1-56/5 * * * * /home/turbohoje/haus/tvsnap/publish_snapshot.py >/dev/null
```

`fetch_metar.py` runs regardless of deploy state and writes its sidecar locally;
only the publisher needs `.env`.

The quiet path in `main()` needs `WORKER_URL` and `API_KEY` both empty. They are
now both set, so the publisher is live: every 5 minutes it tries to PUT, and
exits non-zero because the worker does not exist yet. There is no MTA on this
box, so cron discards that output rather than mailing it. It starts succeeding
the moment `deploy.sh` runs, with no further changes.

## Verified vs not

Verified on this box:

- The wx and cal sidecars are written without changing a byte of the six overlay
  files. Confirmed twice: by hand, and by cron running the patched scripts.
- `worker.mjs` passes 12 unit tests (routing, missing/wrong/same-length-wrong
  key, invalid JSON, oversize, content-type, method-not-allowed). Those 12 live
  nowhere in the repo — they were ad hoc, and predate the two-key split.
- The two-key `authorized()` passes 17 checks under node: the full matrix of
  {rw, ro, wrong, same-length-wrong, absent, empty} against GET/PUT/DELETE, that
  a rejected `ro` PUT leaves the stored object byte-identical, and that with
  `READ_KEY` unset the old single-key behaviour returns exactly. Not re-verified
  against the original 12, which no longer exist to run.
- `fetch_metar.py` parsing passes 12 cases: each of the four flight categories,
  variable wind, gusting, calm, absent `fltCat`, an id-only row, response-order
  independence, a missing station, and an empty 204. Its network-failure and
  no-usable-observation paths were confirmed to leave the sidecar byte-identical.
- End to end: the real `publish_snapshot.py` against the real `worker.mjs`,
  858 bytes with airports (709 without). Also its missing-sidecar,
  stale-sidecar, half-configured, wrong-key and unreachable-host paths.

Verified live against the deployed worker on 2026-09-06: `/health` unauthed 200;
GET `/snapshot` 401 with no key and with a wrong key; 200 with `API_KEY` and with
`READ_KEY`; PUT 200 with `API_KEY` and **403 with `READ_KEY`**; DELETE 405; an
unknown path 404; and the stored object unchanged after the rejected write.

**Not** verified: every line of watch-side code. `watch/README.md` has the specific list of things to check in the
simulator — the load-bearing one is whether Connect IQ's custom `:headers`
actually reach Cloudflare, because the whole auth design rests on it.

## Testing without Cloudflare

There is no node on this box, but podman is here. `worker.mjs` runs under plain
node with two stubs — `crypto.subtle.timingSafeEqual` (a Workers extension) and
`env.SNAP` (R2). Write a ~20 line `http.createServer` bridge that adapts node's
req/res to `worker.fetch(new Request(...), env)`, mount it, and point
`WORKER_URL` at `http://127.0.0.1:8787`:

```sh
podman run -d --rm --name wsrv -p 8787:8787 -v /tmp/wtest:/w:z -w /w \
  docker.io/library/node:22-alpine node serve.mjs
```

That is how every number in the README was measured. It exercises the real
worker and the real publisher, so prefer it over mocking either one.

## Invariants — break these and the TV breaks

**The overlays must stay byte-identical.** `fetch_wx.py` and `fetch_cal.py` drive
a live display; the JSON is a by-product. Both scripts wrap their snapshot write
so a snapshot failure can never fail the run, and both only reach it after every
overlay has been written. Diff the six `.txt` files before and after any change
to either script — that is the actual regression test.

**`split_shared()` must keep matching on `item[:3]`.** `entries()` now returns
5-tuples (the epoch and all-day flag were appended for the snapshot). Comparing
whole tuples would change which rows get pulled into `cal_both.txt`, which the
`y=h-th-160` positioning depends on. See the ffmpeg README's "Shared rows".

**Sticky-on-failure is load bearing.** A failed fetch leaves the previous sidecar
in place, exactly like the overlays. This is why the publisher carries `wx_ts`
and `cal_ts` through separately — without them a stale half is indistinguishable
from a fresh one on the watch. Do not collapse them into the single `ts`.

**Payload size is a design constraint, not a nicety.** The consumer is a
venu2plus watch face whose background process gets 65,536 bytes total, and the
JSON is parsed into a Dictionary inside that pool. 858 bytes today. Anything that
would grow this by an order of magnitude needs rethinking, not just adding.

**`metar[].dir` is an int or the string `"VRB"`.** The one mixed-type field in
the payload, and the likeliest thing to crash the watch face, since a bare
`.format()` on a String is a runtime error. Kept mixed because it is what the
METAR reports; if you ever normalise it, `watch/README.md` and the payload
section of `README.md` both describe the current contract and must change too.

## Decisions already made — do not silently revisit

- **Two keys as of 2026-09-06: `API_KEY` (read+write) and optional `READ_KEY`
  (read only).** The user asked for a reduced-capability key for another project
  that only consumes the JSON, which is the "if the user asks" case the previous
  note here anticipated. `authorized()` now returns `"rw"`, `"ro"` or `null`, and
  `PUT` requires `"rw"`. The original reasoning still holds for *exposure* —
  calendar titles leak on read alone — so `READ_KEY` limits damage, not
  disclosure, and is not a reason to hand it to anything less trusted. With
  `READ_KEY` unset the behaviour is exactly the old single-key one.
- **Jenny's calendar is not published.** Only `cal_justin` rows and the shared
  `cal_both` rows. This was explicit.
- **Epoch seconds, not ISO 8601.** Monkey C has no date parser but takes an epoch
  straight into `Time.Moment`.
- **Airports are watch-only and deliberately not on the TV.** Asked and
  answered; this is why `fetch_metar.py` sits in `tvsnap/` and breaks the
  otherwise-consistent "ffmpeg writes the sidecars" pattern.
- **Flight category is collapsed to VFR/IFR.** The AWC API reports four states
  and the user chose two, knowing MVFR and LIFR fold into `IFR`.
- **R2, not KV.** The user picked R2. At ~700 bytes KV would have been the
  simpler fit and needs no dashboard signup — worth mentioning if they hit R2's
  payment-method wall, but do not switch it unilaterally.

## The METAR source

`https://aviationweather.gov/api/data/metar?ids=...&format=json` — NOAA's
Aviation Weather Center. Free, no key, no registration. It computes `fltCat`
server-side, which is why nothing here parses ceilings out of the raw METAR.

Behaviours worth knowing before you touch `fetch_metar.py`, all confirmed live:

- An unknown or offline station is **silently dropped** from the response array,
  not reported as an error. Fewer rows than `STATIONS` is normal.
- If it recognises **none** of the ids it answers **HTTP 204 with an empty
  body**, which `json.loads` cannot parse. `fetch()` special-cases that.
- `wdir` is an int **or the string `"VRB"`** (seen at KSFO).
- `wgst` is **absent**, not null, when the wind is not gusting.
- `cache-control: max-age=60`, so anything faster than a 1-minute poll is
  returning cached bytes.

## Related

- `../ffmpeg/README.md` — the display this data comes from, and its failure model
- `~/cf_metrics` — the other Cloudflare project; terraform + wrangler, which this
  one deliberately does not follow because neither tool is installed here
- `github.com/turbohoje/garmin_watch` — the consumer. Its `NOTES.md` is careful
  about separating verified facts from estimates; match that when writing there.
