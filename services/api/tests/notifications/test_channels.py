"""The channel adapters, against the real protocols (§23.3, §23.6).

Nothing here is mocked. `WebPushChannel` performs real RFC 8291 encryption and
posts to a real HTTP server on loopback; `SmtpChannel` holds a real SMTP
conversation with Mailpit. The one thing standing in for anything is the push
SERVICE — which is outside our system by design, because RFC 8030 puts the
endpoint URL inside the subscription and makes it data to us.

The most important test in this file is the first one: RFC 8291's own published
test vector, decrypted with our own key derivation. Every other property of a
push implementation has a symptom; a wrong KDF has none. The browser drops the
payload, the push service returns 201, and the phone is silent.
"""

from __future__ import annotations

import datetime as dt
import struct
from email import message_from_string

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sitara_schemas.notifications import (
    DeliveryFailure,
    MessageClass,
    NotificationChannel,
)

from sitara_api.notifications.providers.base import (
    ChannelNotImplemented,
    ChannelUnavailable,
    Delivery,
    PushSubscription,
    Recipient,
)
from sitara_api.notifications.providers.email_smtp import SmtpChannel, SmtpConfig
from sitara_api.notifications.providers.webpush import (
    VapidKeypair,
    WebPushChannel,
    _hkdf,
    b64url,
    b64url_decode,
    encrypt,
)
from sitara_api.notifications.providers.whatsapp import WhatsAppChannel
from tests.notifications.conftest import (
    MAILPIT_SMTP,
    mailpit_clear,
    mailpit_messages,
    requires_mailpit,
)

NOW = dt.datetime(2026, 8, 15, 4, 0, tzinfo=dt.UTC)

# RFC 8291 Appendix A — the published example, verbatim.
RFC_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
RFC_RECEIVER_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
RFC_RECEIVER_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
RFC_BODY = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
    "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)
RFC_PLAINTEXT = b"When I grow up, I want to be a watermelon"


def _decrypt(body: bytes, private: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    """RFC 8291 in reverse — the receiver's half.

    Written here rather than imported because the product has no reason to
    decrypt a push: only a browser does. It exists so the vector below can be
    checked against OUR derivation, which is the whole point of the exercise.
    """
    salt = body[:16]
    idlen = body[20]
    as_public_bytes = body[21 : 21 + idlen]
    ciphertext = body[21 + idlen :]
    ua_public_bytes = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    shared = private.exchange(
        ec.ECDH(),
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public_bytes),
    )
    ikm = _hkdf(
        salt=auth,
        ikm=shared,
        info=b"WebPush: info\x00" + ua_public_bytes + as_public_bytes,
        length=32,
    )
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    return AESGCM(cek).decrypt(nonce, ciphertext, None).rstrip(b"\x02\x01")


def _delivery(**overrides) -> Delivery:  # noqa: ANN003
    base = {
        "message_id": "brief:u1:2026-08-15:en:r0",
        "message_class": MessageClass.DAILY_LOOP,
        "channel": NotificationChannel.PUSH,
        "recipient": Recipient(),
        "locale": "en",
        "title": "Good morning",
        "body": "Your brief for today is ready.",
        "deep_link": "/today",
        "expires_at": NOW + dt.timedelta(hours=6),
    }
    return Delivery(**{**base, **overrides})


# ---------------------------------------------------------------------------
# RFC 8291 — the crypto
# ---------------------------------------------------------------------------


def test_our_key_derivation_decrypts_rfc_8291s_own_test_vector() -> None:
    """The one test that would catch a wrong KDF.

    A push implementation with a swapped HKDF salt produces 32 plausible bytes,
    a 201 from the push service, and a phone that never buzzes. There is no
    symptom to notice and no log line to read — which is why the RFC's own
    vector is checked rather than a round-trip alone.
    """
    private = ec.derive_private_key(
        int.from_bytes(b64url_decode(RFC_RECEIVER_PRIVATE), "big"), ec.SECP256R1()
    )
    # Sanity: the private key really is the one whose public half the RFC
    # publishes, so a failure below is about the derivation and not the fixture.
    assert (
        b64url(
            private.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        == RFC_RECEIVER_PUBLIC
    )
    assert _decrypt(b64url_decode(RFC_BODY), private, b64url_decode(RFC_AUTH)) == (
        RFC_PLAINTEXT
    )


def test_our_encrypt_round_trips_through_the_same_derivation() -> None:
    private = ec.derive_private_key(
        int.from_bytes(b64url_decode(RFC_RECEIVER_PRIVATE), "big"), ec.SECP256R1()
    )
    subscription = PushSubscription(
        endpoint="https://push.invalid/x", p256dh=RFC_RECEIVER_PUBLIC, auth=RFC_AUTH
    )
    body = encrypt(b'{"title":"Good morning"}', subscription)
    assert _decrypt(body, private, b64url_decode(RFC_AUTH)) == b'{"title":"Good morning"}'


def test_the_body_carries_rfc_8188s_header_block() -> None:
    """salt(16) || rs(4) || idlen(1)=65 || as_public(65) || ciphertext."""
    subscription = PushSubscription(
        endpoint="https://push.invalid/x", p256dh=RFC_RECEIVER_PUBLIC, auth=RFC_AUTH
    )
    body = encrypt(b"hello", subscription)
    assert len(body[:16]) == 16
    assert struct.unpack("!I", body[16:20])[0] == 4096
    assert body[20] == 65
    # Uncompressed EC point, so the first byte of the key is 0x04.
    assert body[21] == 0x04


def test_two_encryptions_of_one_payload_differ() -> None:
    """A fresh salt and a fresh ephemeral key every time.

    A fixed salt would make two identical briefs produce identical ciphertext,
    which leaks that they were identical to anyone watching the wire.
    """
    subscription = PushSubscription(
        endpoint="https://push.invalid/x", p256dh=RFC_RECEIVER_PUBLIC, auth=RFC_AUTH
    )
    assert encrypt(b"same", subscription) != encrypt(b"same", subscription)


# ---------------------------------------------------------------------------
# RFC 8292 — VAPID
# ---------------------------------------------------------------------------


def test_the_vapid_audience_is_the_endpoint_ORIGIN_not_the_endpoint() -> None:
    """A JWT scoped to the full path is rejected by every push service — and
    the mistake is invisible locally, where a stand-in checks nothing."""
    keypair = VapidKeypair.generate()
    header = keypair.authorization(
        "https://fcm.googleapis.com/fcm/send/abc123", now=NOW
    )
    token = header.removeprefix("vapid t=").split(",")[0]
    import json

    claims = json.loads(b64url_decode(token.split(".")[1]))
    assert claims["aud"] == "https://fcm.googleapis.com"
    assert claims["sub"].startswith("mailto:")


def test_the_es256_signature_is_raw_r_s_and_not_der() -> None:
    """`cryptography` signs to DER; a DER signature in a JWT is accepted by
    nothing, and it is ~70 bytes rather than 64 — which is the tell."""
    keypair = VapidKeypair.generate()
    header = keypair.authorization("https://push.invalid/x", now=NOW)
    token = header.removeprefix("vapid t=").split(",")[0]
    assert len(b64url_decode(token.split(".")[2])) == 64


def test_the_vapid_header_carries_the_public_key() -> None:
    keypair = VapidKeypair.generate()
    header = keypair.authorization("https://push.invalid/x", now=NOW)
    assert f"k={keypair.public_key_b64}" in header


def test_a_keypair_round_trips_through_a_file(tmp_path) -> None:  # noqa: ANN001
    """The keypair is persisted rather than regenerated — a key that changed on
    restart would invalidate every browser subscription in the database."""
    keypair = VapidKeypair.generate()
    path = tmp_path / "vapid.json"
    keypair.save(path)
    assert VapidKeypair.load(path).public_key_b64 == keypair.public_key_b64
    assert path.stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# The push adapter, against a real HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_push_arrives_decryptable_with_its_deep_link(
    push_service, vapid
) -> None:  # noqa: ANN001
    """End to end: encrypt, sign, POST, decrypt at the other end.

    Asserting on the DECRYPTED payload rather than on the request count is the
    point — a stub that only counted would pass against an adapter encrypting
    to the wrong key.
    """
    subscription = push_service.subscription
    channel = WebPushChannel(vapid)
    outcome = await channel.send(
        _delivery(recipient=Recipient(push_subscription=subscription))
    )
    assert outcome.accepted is True

    received = push_service.received[0]
    assert received["headers"]["content-encoding"] == "aes128gcm"
    assert received["headers"]["authorization"].startswith("vapid t=")
    payload = push_service.decrypt(received["body"])
    assert payload["title"] == "Good morning"
    # §24.1: "every push carries its deep link", and it is a ROUTE — a push
    # that could carry an origin could navigate a browser off our domain.
    assert payload["deep_link"] == "/today"
    assert not payload["deep_link"].startswith("http")


@pytest.mark.asyncio
async def test_the_ttl_header_is_the_time_left_before_23_4s_expiry(
    push_service, vapid
) -> None:  # noqa: ANN001
    """§23.4, as far as the push service can help — it holds an undelivered
    message for at most this long."""
    channel = WebPushChannel(vapid)
    await channel.send(
        _delivery(
            recipient=Recipient(push_subscription=push_service.subscription),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30),
        )
    )
    ttl = int(push_service.received[0]["headers"]["ttl"])
    assert 1700 <= ttl <= 1800


@pytest.mark.asyncio
async def test_a_collapse_key_becomes_an_rfc_8030_topic(push_service, vapid) -> None:  # noqa: ANN001
    """§23.4's collapse, done by the one party that can still reach a message
    we have already handed over.

    The key is HASHED into the topic rather than passed through: topics are
    base64url-charset only, and `brief:<id>:<date>` has colons in it — which
    would be a 400 from the push service on every single brief.
    """
    channel = WebPushChannel(vapid)
    await channel.send(
        _delivery(
            recipient=Recipient(push_subscription=push_service.subscription),
            collapse_key="brief:6c70000000000000000000a1:2026-08-15",
        )
    )
    topic = push_service.received[0]["headers"]["topic"]
    assert ":" not in topic
    assert len(topic) <= 32


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 410])
async def test_a_404_or_410_is_a_dead_subscription(push_service, vapid, status) -> None:  # noqa: ANN001
    """§23.6: "a 410/404 from the push service marks the subscription dead
    immediately"."""
    push_service.status = status
    outcome = await WebPushChannel(vapid).send(
        _delivery(recipient=Recipient(push_subscription=push_service.subscription))
    )
    assert outcome.accepted is False
    assert outcome.failure is DeliveryFailure.SUBSCRIPTION_GONE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_5xx_or_429_is_transient(push_service, vapid, status) -> None:  # noqa: ANN001
    """Counts toward §23.6's three CONSECUTIVE failures — it is evidence about
    the network, not about the subscription."""
    push_service.status = status
    outcome = await WebPushChannel(vapid).send(
        _delivery(recipient=Recipient(push_subscription=push_service.subscription))
    )
    assert outcome.failure is DeliveryFailure.TRANSIENT


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 413])
async def test_a_rejection_is_not_a_dead_subscription(
    push_service, vapid, status
) -> None:  # noqa: ANN001
    """The test that protects against a five-minute mistake becoming a
    re-subscribe campaign.

    A mis-rotated VAPID key makes every push 403. If that counted toward
    §23.6's failure budget, three mornings later EVERY subscription in the
    database would be dead and every user would have to grant the permission
    again — for a configuration error that took five minutes to fix.
    """
    push_service.status = status
    outcome = await WebPushChannel(vapid).send(
        _delivery(recipient=Recipient(push_subscription=push_service.subscription))
    )
    assert outcome.failure is DeliveryFailure.REJECTED


@pytest.mark.asyncio
async def test_an_unreachable_push_service_raises_rather_than_leaking(vapid) -> None:  # noqa: ANN001
    """§13: the upstream exception does not travel. A push endpoint URL can
    carry a subscription id, and an exception string ends up in a log and a
    trace at once."""
    channel = WebPushChannel(vapid, client=httpx.AsyncClient(timeout=0.2))
    subscription = PushSubscription(
        # Reserved-for-documentation address; nothing listens, and nothing
        # routes off this machine.
        endpoint="http://127.0.0.1:9/push/x",
        p256dh=RFC_RECEIVER_PUBLIC,
        auth=RFC_AUTH,
    )
    with pytest.raises(ChannelUnavailable) as caught:
        await channel.send(_delivery(recipient=Recipient(push_subscription=subscription)))
    assert "127.0.0.1" not in str(caught.value)


# ---------------------------------------------------------------------------
# The email adapter, against Mailpit
# ---------------------------------------------------------------------------


@requires_mailpit
@pytest.mark.asyncio
async def test_an_email_arrives_in_the_real_inbox() -> None:
    """A real SMTP conversation with a real server, asserted from its inbox."""
    await mailpit_clear()
    channel = SmtpChannel(
        SmtpConfig(host=MAILPIT_SMTP[0], port=MAILPIT_SMTP[1], from_address="tara@sitara.localhost")
    )
    outcome = await channel.send(
        _delivery(
            channel=NotificationChannel.EMAIL,
            recipient=Recipient(email="reader@example.invalid"),
        )
    )
    assert outcome.accepted is True

    messages = await mailpit_messages()
    assert len(messages) == 1
    assert messages[0]["Subject"] == "Good morning"
    assert messages[0]["To"][0]["Address"] == "reader@example.invalid"


@requires_mailpit
@pytest.mark.asyncio
async def test_list_unsubscribe_is_on_marketing_and_never_on_transactional() -> None:
    """§23.3: "on Class M, never on Class T".

    An unsubscribe header on an OTP invites somebody to unsubscribe from the
    message that lets them sign in — and some clients act on the header
    without asking the reader first.
    """
    await mailpit_clear()
    channel = SmtpChannel(
        SmtpConfig(host=MAILPIT_SMTP[0], port=MAILPIT_SMTP[1], from_address="tara@sitara.localhost")
    )
    for message_class in (MessageClass.MARKETING, MessageClass.TRANSACTIONAL):
        await channel.send(
            _delivery(
                channel=NotificationChannel.EMAIL,
                message_class=message_class,
                message_id=f"m-{message_class.value}",
                recipient=Recipient(email="reader@example.invalid"),
                unsubscribe_url="/api/v1/notifications/unsubscribe/x",
            )
        )

    import httpx as _httpx

    async with _httpx.AsyncClient(base_url="http://localhost:8025", timeout=5.0) as api:
        listed = (await api.get("/api/v1/messages")).json()["messages"]
        headers = {}
        for summary in listed:
            raw = (await api.get(f"/api/v1/message/{summary['ID']}/raw")).text
            parsed = message_from_string(raw)
            headers[parsed["Message-ID"]] = parsed.get("List-Unsubscribe")

    assert headers["<m-marketing@sitara.app>"] is not None
    assert headers["<m-transactional@sitara.app>"] is None


@requires_mailpit
@pytest.mark.asyncio
async def test_the_locale_rides_on_the_message() -> None:
    """§23.8 reports per locale and §2.4 has no fallback — a mail client that
    knows the language renders the right script and reads it aloud correctly."""
    await mailpit_clear()
    channel = SmtpChannel(
        SmtpConfig(host=MAILPIT_SMTP[0], port=MAILPIT_SMTP[1], from_address="tara@sitara.localhost")
    )
    await channel.send(
        _delivery(
            channel=NotificationChannel.EMAIL,
            locale="hi",
            title="सुप्रभात",
            body="आज का आपका ब्रीफ़ तैयार है।",
            recipient=Recipient(email="reader@example.invalid"),
        )
    )
    import httpx as _httpx

    async with _httpx.AsyncClient(base_url="http://localhost:8025", timeout=5.0) as api:
        listed = (await api.get("/api/v1/messages")).json()["messages"]
        raw = (await api.get(f"/api/v1/message/{listed[0]['ID']}/raw")).text
    parsed = message_from_string(raw)
    assert parsed["Content-Language"] == "hi"
    assert "सुप्रभात" in listed[0]["Subject"]


@pytest.mark.asyncio
async def test_an_unreachable_smtp_host_raises_without_the_address() -> None:
    """§13 again: an SMTP error string can carry the recipient, which is PII."""
    channel = SmtpChannel(
        SmtpConfig(host="127.0.0.1", port=9, from_address="tara@sitara.localhost", timeout=0.3)
    )
    with pytest.raises(ChannelUnavailable) as caught:
        await channel.send(
            _delivery(
                channel=NotificationChannel.EMAIL,
                recipient=Recipient(email="reader@example.invalid"),
            )
        )
    assert "reader@example.invalid" not in str(caught.value)


# ---------------------------------------------------------------------------
# WhatsApp — DECLARED
# ---------------------------------------------------------------------------


def test_whatsapp_cannot_be_constructed() -> None:
    """Two guards, deliberately, because they fail differently: the matrix
    keeps it out of the ladder, and the raise keeps a future caller that builds
    one directly — which is how "a quick test against the real thing" gets
    written — from silently doing nothing and reporting success."""
    with pytest.raises(ChannelNotImplemented, match="DECLARED"):
        WhatsAppChannel()
