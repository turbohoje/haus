import Toybox.Background;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.System;

// The whole file is background-only. Without the annotation the entire app gets
// loaded into the background process against its 65,536-byte pool on venu2plus,
// which is the trap NOTES.md flags.
(:background)
class SnapshotService extends System.ServiceDelegate {

    function initialize() {
        System.ServiceDelegate.initialize();
    }

    // Fired by the temporal event registered in WatchFaceApp. The minimum
    // interval Connect IQ allows is 5 minutes, which is also how often the haus
    // box republishes, so there is nothing to gain by asking for less.
    function onTemporalEvent() as Void {
        Communications.makeWebRequest(
            SNAPSHOT_URL,
            null,
            {
                :method => Communications.HTTP_REQUEST_METHOD_GET,
                :headers => { "X-API-Key" => SNAPSHOT_KEY },
                // The worker forces Content-Type: application/json so this
                // comes back already parsed into a Dictionary.
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            method(:onResponse)
        );
    }

    function onResponse(code as Number, data as Dictionary or String or Null) as Void {
        if (code == 200 && data instanceof Lang.Dictionary) {
            // Handed straight to AppBase.onBackgroundData. The payload is a few
            // hundred bytes, well under what Background.exit will carry.
            Background.exit(data);
            return;
        }

        // Exit empty on any failure rather than writing a sentinel: the face
        // keeps the last good snapshot from Storage and shows its age instead.
        System.println("snapshot fetch failed: " + code);
        Background.exit(null);
    }
}
