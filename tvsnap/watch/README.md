# Watch-side client

Reference implementation for pulling `/snapshot` into the `garmin_watch` face.
Copy `SnapshotService.mc` into that repo's `source/`.

**None of this has been built or run.** The Connect IQ SDK and JDK live on the
Mac (per `garmin_watch/NOTES.md`); the haus box has neither, so what follows is
written against the documented API and the device facts in NOTES.md, not
verified in the simulator. Treat the "to verify" list at the bottom as real work,
not boilerplate.

## Why a background service

A watch face's `onUpdate()` is not a place to make a web request — it runs once
a minute in low power and must not block. Connect IQ's answer is a background
service: the app registers a temporal event, the system wakes a separate process
on that interval, that process fetches, and hands the result back through
`onBackgroundData()`.

The minimum temporal interval is 5 minutes, which is also the republish cadence
on the haus box, so there is nothing to gain by asking for less.

The background process gets **65,536 bytes** on venu2plus — half the watch
face's 131,072. NOTES.md already flags the trap: without `(:background)`
annotations the *entire app* is what gets loaded into that pool. `SnapshotService.mc`
is annotated throughout for that reason. The snapshot itself is ~700 bytes
parsed into a Dictionary, which is what the payload was designed around.

## Wiring it up

**1. `SnapshotConfig.mc`** — copy `SnapshotConfig.mc.example` to
`source/SnapshotConfig.mc`, fill in the worker URL and shared key, and add it to
`.gitignore`. The key is compiled into the `.prg` and readable by anyone holding
the app; that is understood and accepted (see the main README), but it should
still not be in git.

**2. `manifest.xml`** — the current `<iq:permissions/>` is empty and needs two:

```xml
<iq:permissions>
    <iq:uses-permission id="Communications"/>
    <iq:uses-permission id="Background"/>
</iq:permissions>
```

Both are available to watch faces per the table in NOTES.md. Note permission ids
are unvalidated by the schema, so a typo compiles silently and fails at runtime.

**3. `WatchFaceApp.mc`** — register the event and receive the data:

```monkeyc
import Toybox.Background;
import Toybox.Time;

function onStart(state as Dictionary?) as Void {
    if (Toybox has :Background) {
        Background.registerForTemporalEvent(new Time.Duration(5 * 60));
    }
}

function getServiceDelegate() as [System.ServiceDelegate] {
    return [ new SnapshotService() ];
}

function onBackgroundData(data as PersistableType) as Void {
    if (data != null) {
        // Storage, not a member: the face and the service are separate
        // processes and do not share memory.
        Application.Storage.setValue("snapshot", data);
        WatchUi.requestUpdate();
    }
}
```

**4. `WatchFaceView.mc`** — read it back in `drawFull()` with
`Application.Storage.getValue("snapshot")`. Leave `drawAlwaysOn()` alone; NOTES.md
is explicit that the always-on path stays time-only for the AMOLED luminance
budget.

Check `ts` before drawing: the snapshot survives in Storage across restarts, and
a watch out of phone range for a day will happily render yesterday's
temperatures as current. `wx_ts` / `cal_ts` age each half independently.

## To verify in the simulator

- **Custom headers actually reach the worker.** Connect IQ requests go out
  through the phone; `:headers` is documented on `makeWebRequest` but this has
  not been confirmed against a real Cloudflare endpoint. If the key does not
  arrive, the fallback is a query parameter — which means it lands in logs, so
  prefer the header if it works.
- **`Background.exit()` carries the whole Dictionary.** There is a size limit on
  background exit data; ~700 bytes should be well inside it, but confirm rather
  than assume.
- **Background memory.** Whether `(:background)` alone keeps the service under
  65,536 bytes, or the jungle also needs `excludeAnnotations` to keep the face's
  code out of the background build. Check the simulator's memory view.
- **Layout.** The face is currently full at y=43–388 on a 416px round screen
  (see the layout table in NOTES.md). Anything new has to displace something.
