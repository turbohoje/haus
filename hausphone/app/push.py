"""Web Push (VAPID) notifications.

Used for alerts the app must deliver when it isn't open — currently only the
garage auto-close giving up. Keys and subscriptions live in the same persistent
volume as the TLS cert, so they survive `docker compose up --build`.

Push requires a secure context on the phone, which is why the app serves HTTPS
with the self-signed cert; on iOS it additionally requires the PWA to be
installed to the home screen. The NUC needs outbound HTTPS to reach the push
services (fcm.googleapis.com, web.push.apple.com, updates.push.services.mozilla.com).
"""
import asyncio
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# /certs is the container's persistent volume; fall back to a local dir for dev runs.
_default_dir = "/certs" if os.path.isdir("/certs") else str(Path(__file__).parent.parent / "data")
DATA_DIR = Path(os.environ.get("HAUSPHONE_DATA_DIR", _default_dir))
VAPID_KEY_PATH = DATA_DIR / "vapid_private.pem"
SUBS_PATH = DATA_DIR / "push_subscriptions.json"
# VAPID requires a contact the push service can reach if it needs to complain.
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:turbohoje@gmail.com")
TTL_SECONDS = 1800          # push service holds the alert this long if the phone is offline

_vapid = None               # py_vapid.Vapid01
_public_key = ""            # base64url raw P-256 point — the browser's applicationServerKey
_subs: list = []            # subscription dicts as handed over by pushManager.subscribe()


def load():
    """Generate/read the VAPID keypair and load saved subscriptions. Non-fatal:
    if pywebpush is missing or the dir is unwritable, push just stays off."""
    global _vapid, _public_key, _subs
    try:
        import base64
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _vapid = Vapid01.from_file(str(VAPID_KEY_PATH))
        raw = _vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        _public_key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    except Exception as e:
        log.warning("Push disabled (VAPID setup failed): %s", e)
        _vapid = None
        _public_key = ""
        return

    try:
        if SUBS_PATH.exists():
            _subs = json.loads(SUBS_PATH.read_text())
    except Exception as e:
        log.warning("Could not read push subscriptions: %s", e)
        _subs = []
    log.info("Push ready (%d subscription(s))", len(_subs))


def available() -> bool:
    return _vapid is not None


def public_key() -> str:
    return _public_key


def _save_subs():
    try:
        SUBS_PATH.write_text(json.dumps(_subs))
    except Exception as e:
        log.warning("Could not save push subscriptions: %s", e)


def add_subscription(sub: dict) -> int:
    """Store a browser subscription, replacing any earlier one for that endpoint."""
    endpoint = sub.get("endpoint")
    if not endpoint:
        raise ValueError("subscription has no endpoint")
    global _subs
    _subs = [s for s in _subs if s.get("endpoint") != endpoint]
    _subs.append(sub)
    _save_subs()
    log.info("Push subscription added (%d total)", len(_subs))
    return len(_subs)


def remove_subscription(endpoint: str) -> int:
    global _subs
    before = len(_subs)
    _subs = [s for s in _subs if s.get("endpoint") != endpoint]
    if len(_subs) != before:
        _save_subs()
        log.info("Push subscription removed (%d left)", len(_subs))
    return len(_subs)


def _send_one(sub: dict, payload: str):
    """Blocking single send. Returns True to keep the subscription, False to drop it."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info=sub,
            data=payload,
            vapid_private_key=_vapid,
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=TTL_SECONDS,
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            log.info("Push endpoint gone (%s) — dropping subscription", status)
            return False
        log.warning("Push send failed (%s): %s", status, e)
        return True
    except Exception as e:
        log.warning("Push send error: %s", e)
        return True


async def send(title: str, body: str, tag: str = "haus", url: str = "/") -> int:
    """Fan out one notification to every subscribed phone. Returns the count sent."""
    if not available() or not _subs:
        return 0
    payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url})
    loop = asyncio.get_event_loop()
    targets = list(_subs)
    results = await asyncio.gather(
        *(loop.run_in_executor(None, _send_one, sub, payload) for sub in targets)
    )
    for sub, keep in zip(targets, results):
        if not keep:
            remove_subscription(sub.get("endpoint"))
    sent = sum(1 for keep in results if keep)
    log.info("Push sent to %d/%d subscription(s): %s", sent, len(targets), title)
    return sent
