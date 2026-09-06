# tvsnap — context for agents

Read `README.md` first for what this is and how the pieces fit. This file is the
part that is not obvious from the code: what is actually true right now, what has
been verified, and which invariants will silently break the TV if you touch them.

## State as of 2026-09-06

**Not deployed.** Everything except the Cloudflare deploy is done and tested.
`deploy.sh` has never been run — it needs `CF_API_TOKEN` / `CF_ACCOUNT_ID` in
`.env`, and no Cloudflare credentials exist anywhere on this box (`~/cf_metrics`
is deployed but has no local `terraform.tfvars` or `.tfstate`). R2 also has to be
enabled once in the dashboard; the free tier still wants a card on file.

**Cron is installed:**

```cron
*/10   * * * * /home/turbohoje/haus/tvsnap/fetch_metar.py >/dev/null
1-56/5 * * * * /home/turbohoje/haus/tvsnap/publish_snapshot.py >/dev/null
```

`fetch_metar.py` runs regardless of deploy state and writes its sidecar locally;
only the publisher needs `.env`.

It exits 0 silently while `.env` is the unfilled template, so it is not currently
mailing failures. That quiet path is deliberate — see the comment in `main()`.
Once `.env` is filled in it starts publishing with no further changes.

## Verified vs not

Verified on this box:

- The wx and cal sidecars are written without changing a byte of the six overlay
  files. Confirmed twice: by hand, and by cron running the patched scripts.
- `worker.mjs` passes 12 unit tests (routing, missing/wrong/same-length-wrong
  key, invalid JSON, oversize, content-type, method-not-allowed).
- `fetch_metar.py` parsing passes 12 cases: each of the four flight categories,
  variable wind, gusting, calm, absent `fltCat`, an id-only row, response-order
  independence, a missing station, and an empty 204. Its network-failure and
  no-usable-observation paths were confirmed to leave the sidecar byte-identical.
- End to end: the real `publish_snapshot.py` against the real `worker.mjs`,
  858 bytes with airports (709 without). Also its missing-sidecar,
  stale-sidecar, half-configured, wrong-key and unreachable-host paths.

**Not** verified: the Cloudflare deploy itself, and every line of watch-side
code. `watch/README.md` has the specific list of things to check in the
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

- **One shared key for read and write.** Chosen knowingly. A read-only key would
  not help: the sensitive part is calendar titles, which leak on read alone, and
  the key ships compiled into a sideloaded `.prg` either way. Splitting it is a
  small change to `authorized()` if the user asks, but it is not an oversight.
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
