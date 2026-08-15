"""Web push over the browser's OWN Push API — RFC 8292 (VAPID) + RFC 8291.

§6.2: "web push via VAPID (iOS requires installed PWA ≥16.4 — the install
prompt is a first-week onboarding step)".

── Why this is a full implementation and not a simulator ───────────────────

Web push is the one channel in §23.3 that needs **no vendor account at all**.
The push service is whichever one the user's own browser chose — its URL
arrives inside the subscription and is data to us — and VAPID authenticates us
with a keypair we generate ourselves. There is nothing to sign up for, no key
to be issued, no per-message billing relationship. So the honest prototype of
this channel is the channel: real ECDH, real HKDF, real AES128GCM, real ES256,
posted to whatever endpoint the browser handed over.

That matters beyond tidiness. The three things most likely to be wrong in a
push implementation — the encryption, the VAPID signature, and §23.6's
dead-subscription handling — are all things a simulator would have had to
invent an answer for, and all three would then have been exercised for the
first time in front of a user.

── What the endpoint being DATA buys ───────────────────────────────────────

`endpoint` comes from the browser. In a browser signed into a normal profile
it is a push service run by the browser vendor; in the test suite it is a
loopback URL. The adapter cannot tell, and must not: it POSTs an encrypted
body to a URL and reads a status code, which is the entire protocol. That is
why `tests/notifications/test_webpush.py` can exercise the real crypto against
a real HTTP server without reaching the internet, and why CI's
`test_no_live_network.py` block does not need an exception for this file.

── The crypto, in the order RFC 8291 §3.4 gives it ─────────────────────────

    ecdh_secret = ECDH(as_private, ua_public)                      # 32 bytes
    PRK_key     = HMAC-SHA256(auth_secret, ecdh_secret)
    key_info    = "WebPush: info" || 0x00 || ua_public || as_public
    IKM         = HMAC-SHA256(PRK_key, key_info || 0x01)           # 32 bytes
    PRK         = HMAC-SHA256(salt, IKM)                           # RFC 8188
    CEK         = HMAC-SHA256(PRK, "Content-Encoding: aes128gcm\\0\\x01")[:16]
    NONCE       = HMAC-SHA256(PRK, "Content-Encoding: nonce\\0\\x01")[:12]

and the body is RFC 8188's aes128gcm framing:

    salt(16) || rs(4, big-endian) || idlen(1)=65 || as_public(65) || ciphertext

with the plaintext padded by a single trailing `0x02` — the LAST-record
delimiter. `0x01` is the non-last one, and using it on a single-record message
makes the browser reject a payload that decrypts perfectly, which is a
memorable afternoon.

── The keypair ─────────────────────────────────────────────────────────────

Generated once by `python -m sitara_api.notifications.vapid --generate` and
stored under `services/api/.secrets/` beside the Firebase key — git-ignored,
mounted read-only into the container. It is deliberately NOT generated at boot:
a browser subscription is bound to the `applicationServerKey` it was created
with, so a keypair that changed on restart would silently invalidate every
subscription in the database and every push would come back 403 from a service
that was working perfectly.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as asym_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sitara_schemas.notifications import DeliveryFailure, NotificationChannel

from sitara_api.notifications.providers.base import (
    ChannelProviderName,
    ChannelUnavailable,
    Delivery,
    DeliveryOutcome,
    PushSubscription,
)

logger = logging.getLogger(__name__)

#: RFC 8188 record size. One record is enough for every message §23 sends —
#: a title, a line and a deep link — and multi-record framing would be code
#: with no caller.
RECORD_SIZE = 4096

#: RFC 8188 §2: the last record's plaintext ends with 0x02. See the header for
#: what 0x01 costs.
_LAST_RECORD_DELIMITER = b"\x02"

#: RFC 8292 §2: at most 24 hours. Twelve leaves room for a clock that is a
#: little ahead of the push service's without ever presenting an expired token.
_VAPID_TTL = dt.timedelta(hours=12)

#: RFC 8292 §2.1's `sub`: a contact for the push service operator to reach if
#: our traffic misbehaves. A `mailto:` we own — never a user's address.
DEFAULT_VAPID_SUBJECT = "mailto:notifications@sitara.app"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """HKDF-SHA256, extract then expand, for one 32-byte-or-less block.

    Written out rather than taken from `cryptography.hazmat.primitives.kdf`
    because RFC 8291 uses HKDF in two places with DIFFERENT salts and the
    library's one-shot object is single-use — three near-identical KDF objects
    read as three different derivations when they are one function called three
    times.
    """
    extract = hmac.HMAC(salt, hashes.SHA256())
    extract.update(ikm)
    prk = extract.finalize()
    expand = hmac.HMAC(prk, hashes.SHA256())
    expand.update(info + b"\x01")
    return expand.finalize()[:length]


@dataclass(frozen=True)
class VapidKeypair:
    """Ours, self-generated. §6.2's applicationServerKey.

    `public_key_b64` is what the browser passes to `pushManager.subscribe` and
    is therefore PUBLIC by design — it is served by
    `GET /v1/notifications/push/key` and nothing about it is a secret.
    """

    private_key_pem: str
    subject: str = DEFAULT_VAPID_SUBJECT

    @property
    def _private(self) -> ec.EllipticCurvePrivateKey:
        key = serialization.load_pem_private_key(
            self.private_key_pem.encode("ascii"), password=None
        )
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("VAPID key must be an EC P-256 private key (RFC 8292 §2)")
        return key

    @property
    def public_key_bytes(self) -> bytes:
        return self._private.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )

    @property
    def public_key_b64(self) -> str:
        return b64url(self.public_key_bytes)

    @classmethod
    def generate(cls, subject: str = DEFAULT_VAPID_SUBJECT) -> VapidKeypair:
        private = ec.generate_private_key(ec.SECP256R1())
        return cls(
            private_key_pem=private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode("ascii"),
            subject=subject,
        )

    @classmethod
    def load(cls, path: Path) -> VapidKeypair:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            private_key_pem=data["private_key_pem"],
            subject=data.get("subject", DEFAULT_VAPID_SUBJECT),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "private_key_pem": self.private_key_pem,
                    "subject": self.subject,
                    "public_key_b64": self.public_key_b64,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # A private key readable by the group is a private key in a backup
        # somebody else can read. §13's posture, applied to the one secret this
        # channel has.
        os.chmod(path, 0o600)

    def authorization(self, endpoint: str, *, now: dt.datetime) -> str:
        """RFC 8292 §3's `Authorization: vapid t=..., k=...`.

        The audience is the ORIGIN of the endpoint and not the endpoint — a
        JWT scoped to the full path would be rejected by every push service,
        and the mistake is invisible locally where the stand-in checks nothing.
        """
        origin = urlsplit(endpoint)
        header = {"typ": "JWT", "alg": "ES256"}
        claims = {
            "aud": f"{origin.scheme}://{origin.netloc}",
            "exp": int((now + _VAPID_TTL).timestamp()),
            "sub": self.subject,
        }
        signing_input = b".".join(
            b64url(json.dumps(part, separators=(",", ":")).encode("utf-8")).encode(
                "ascii"
            )
            for part in (header, claims)
        )
        der = self._private.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        # ES256 wants the raw r||s pair, 32 bytes each. `cryptography` signs
        # to DER, and a DER signature in a JWT is accepted by nothing — it is
        # also 70-ish bytes rather than 64, which is the tell.
        r, s = asym_utils.decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = signing_input.decode("ascii") + "." + b64url(raw)
        return f"vapid t={token}, k={self.public_key_b64}"


def encrypt(
    payload: bytes, subscription: PushSubscription, *, salt: bytes | None = None
) -> bytes:
    """RFC 8291 §3.4 + RFC 8188 §2 — one aes128gcm record, ready to POST.

    `salt` is a parameter only so the RFC's own test vector can be reproduced;
    every real call takes the random default. It is keyword-only and has no
    use in production, which is the most a signature can do to keep a fixed
    salt from reaching one.
    """
    salt = salt if salt is not None else os.urandom(16)
    ua_public_bytes = b64url_decode(subscription.p256dh)
    auth_secret = b64url_decode(subscription.auth)

    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public_bytes = as_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), ua_public_bytes
    )
    ecdh_secret = as_private.exchange(ec.ECDH(), ua_public)

    # RFC 8291 §3.4 — the auth secret is the SALT of the first HKDF and the
    # ECDH output is its IKM. Swapping them produces 32 plausible bytes and a
    # browser that silently drops every message.
    ikm = _hkdf(
        salt=auth_secret,
        ikm=ecdh_secret,
        info=b"WebPush: info\x00" + ua_public_bytes + as_public_bytes,
        length=32,
    )
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    ciphertext = AESGCM(cek).encrypt(nonce, payload + _LAST_RECORD_DELIMITER, None)
    header = salt + struct.pack("!I", RECORD_SIZE) + bytes([len(as_public_bytes)])
    return header + as_public_bytes + ciphertext


class WebPushChannel:
    """§23.3's push rung. IMPLEMENTED — the protocol, not a stand-in.

    Holds no per-user state: everything it needs arrives in the `Delivery`,
    which is what lets one instance serve the whole worker.
    """

    name = ChannelProviderName.WEB_PUSH_VAPID
    channel = NotificationChannel.PUSH

    def __init__(
        self,
        keypair: VapidKeypair,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._keypair = keypair
        self._client = client
        self._timeout = timeout

    @property
    def public_key(self) -> str:
        """What `pushManager.subscribe` needs. Public by design."""
        return self._keypair.public_key_b64

    async def send(self, delivery: Delivery) -> DeliveryOutcome:
        subscription = delivery.recipient.push_subscription
        if subscription is None:
            # Not a failure of the message. §23.3's ladder asks
            # `Recipient.reachable_on` before choosing a rung, so reaching here
            # means a subscription was retired between the two — which is
            # exactly §23.6's race and is answered by moving down the ladder.
            return DeliveryOutcome(
                accepted=False,
                provider=self.name,
                failure=DeliveryFailure.SUBSCRIPTION_GONE,
            )

        body = encrypt(_payload(delivery), subscription)
        now = dt.datetime.now(dt.UTC)
        headers = {
            "Authorization": self._keypair.authorization(subscription.endpoint, now=now),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            # §23.4, as far as the push service can help: it holds an
            # undelivered message for at most this long. The expiry SWEEP is
            # still what guarantees the rule, because a service is free to
            # deliver earlier and we are not free to be late.
            "TTL": str(max(0, int((delivery.expires_at - now).total_seconds()))),
        }
        if delivery.collapse_key:
            # RFC 8030 §5.4. The push service replaces an undelivered message
            # with the same topic — §23.4's collapse, done by the one party
            # that can still reach a message we have already handed over.
            # Topics are base64url-charset only, so the key is hashed into it
            # rather than passed through, and a colon in a collapse key would
            # otherwise be a 400 from the push service on every brief.
            headers["Topic"] = _topic(delivery.collapse_key)

        try:
            response = await self._post(subscription.endpoint, body, headers)
        except httpx.HTTPError as exc:
            # §13: the exception does not travel. A push service URL can carry
            # a subscription id, and an exception string tends to end up in a
            # log and a trace at once.
            logger.warning(
                "push transport failure",
                extra={"message_id": delivery.message_id, "error": type(exc).__name__},
            )
            raise ChannelUnavailable("push service unreachable") from None

        if response.status_code in (404, 410):
            # §23.6 — "a 410/404 from the push service marks the subscription
            # dead immediately". The service is telling us the browser
            # discarded it; retrying is the one response that is certainly
            # wrong.
            return DeliveryOutcome(
                accepted=False,
                provider=self.name,
                failure=DeliveryFailure.SUBSCRIPTION_GONE,
            )
        if response.status_code in (200, 201, 202):
            return DeliveryOutcome(
                accepted=True,
                provider=self.name,
                provider_message_id=response.headers.get("location"),
            )
        if response.status_code >= 500 or response.status_code == 429:
            return DeliveryOutcome(
                accepted=False, provider=self.name, failure=DeliveryFailure.TRANSIENT
            )
        # 400, 401, 403, 413 — the service understood and declined. A bad VAPID
        # signature lands here, which is why it is not counted as a dead token:
        # retiring every subscription in the database because a key was
        # mis-rotated is a recoverable mistake made unrecoverable.
        logger.warning(
            "push rejected",
            extra={"message_id": delivery.message_id, "status": response.status_code},
        )
        return DeliveryOutcome(
            accepted=False, provider=self.name, failure=DeliveryFailure.REJECTED
        )

    async def _post(
        self, endpoint: str, body: bytes, headers: dict[str, str]
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(endpoint, content=body, headers=headers)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(endpoint, content=body, headers=headers)


def _payload(delivery: Delivery) -> bytes:
    """What the service worker receives.

    Already-localised strings and a route. Deliberately NOT a message key: the
    service worker has no catalog, and §2.4 has no English fallback — a key
    that failed to resolve in a worker would render as the key itself, in a
    system notification, in the wrong language and outside the app.
    """
    return json.dumps(
        {
            "message_id": delivery.message_id,
            "title": delivery.title,
            "body": delivery.body,
            "deep_link": delivery.deep_link,
            "locale": delivery.locale,
            # RFC 8030's Topic collapses on the SERVICE; this collapses in the
            # notification centre once it has arrived. Both are needed —
            # §23.4's rule is that the user sees one brief notification, and
            # the two mechanisms cover the message before and after handover.
            "tag": delivery.collapse_key,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _topic(collapse_key: str) -> str:
    """RFC 8030 §5.4's Topic: base64url charset, at most 32 characters."""
    import hashlib

    return b64url(hashlib.blake2b(collapse_key.encode("utf-8"), digest_size=18).digest())
