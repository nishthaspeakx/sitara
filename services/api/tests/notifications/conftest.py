"""§23 test harness.

Mongo comes from the dev compose stack on 27018 and Redis from the same stack —
never a fake, the rule `tests/db`, `tests/panchang`, `tests/memory` and
`tests/payments` all follow. Here it earns its keep three times over:

**§23.4's idempotency IS the unique index.** `(user_id, message_id)` on
`notifications` is what makes a retried enqueue a no-op rather than a second
push, and §23.9 makes a duplicate delivery release-blocking. A dict-backed fake
would accept the second write and the suite would prove the application-level
check works while the thing that actually has to hold — two workers landing the
same message at once — went unexercised. That is the M5 lesson (root CLAUDE.md)
pointed at the one §23 rule a bug cannot be walked back from.

**§23.3's dedupe key IS `SET NX EX`.** The atomicity is the guarantee. A fake
Redis with a Python dict has no atomicity to test, and the window between a
GET and a SET is exactly where the double send lives.

**§23.6's unique endpoint index is what makes re-subscribe idempotent.** The
silent re-subscribe on every app open would otherwise accumulate a row per
launch, and the ladder would be choosing between several rows for one browser.

The channels are the REAL adapters. `WebPushChannel` performs real RFC 8291
encryption and posts to a real HTTP server that this file starts on loopback —
the push service's URL arrives inside the subscription and is data to the
adapter, so a loopback endpoint exercises the identical code path a browser
vendor's does. `SmtpChannel` speaks real SMTP to Mailpit when the compose stack
has it, and the tests that need it skip when it does not. Neither is a stand-in
for the protocol; both ARE the protocol.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import socket
import struct
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from bson import ObjectId
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.db import ensure_indexes
from sitara_api.notifications.emergency_stop import EmergencyStop
from sitara_api.notifications.ladder import Dedupe
from sitara_api.notifications.providers.base import PushSubscription
from sitara_api.notifications.providers.webpush import (
    VapidKeypair,
    _hkdf,
    b64url,
    b64url_decode,
)
from sitara_api.notifications.service import NotificationService, RecipientResolver
from sitara_api.notifications.store import (
    NotificationStore,
    PreferenceStore,
    PushSubscriptionStore,
)

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local
REDIS_URI = "redis://localhost:6379/9"  # db 9: the suite's own, never db 0

MAILPIT_SMTP = ("localhost", 1025)
MAILPIT_API = "http://localhost:8025"

#: A fixed instant. Every clock in these tests is injected, so nothing depends
#: on when the suite runs — which matters more than usual here, because half of
#: §23 is a boundary an hour either side of.
NOW = dt.datetime(2026, 8, 15, 4, 0, tzinfo=dt.UTC)  # 09:30 Asia/Kolkata

USER_ID = ObjectId("6c70000000000000000000a1")
OTHER_USER_ID = ObjectId("6c70000000000000000000a2")

IST = "Asia/Kolkata"


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    # `tz_aware=True`, exactly as `db.make_mongo` sets it in production. BSON
    # stores UTC and the DEFAULT codec hands it back NAIVE, so a notification
    # read back and compared against §23.4's aware expiry raises TypeError
    # mid-arithmetic. Three modules in this repo have hit that already.
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    # Written through the REAL §6.4 validator, which requires `firebase_uid`
    # and `status` — the first run of this harness omitted both and every test
    # errored at insert. That is the harness paying for itself before a single
    # assertion ran: a dict-backed fake would have accepted the row, and the
    # whole §23 suite would have been green against a user shape the real
    # collection rejects. It is the M5 lesson (root CLAUDE.md) one milestone on.
    #
    # §22.12: synthetic only — `@example.invalid`, a +9199999 phone.
    await database.users.insert_one(
        {
            "_id": USER_ID,
            "firebase_uid": "test-uid-notifications",
            "status": "active",
            "locale": "en",
            "timezone": IST,
            "email": "seeded@example.invalid",
            "phone": "+919999900001",
            "whatsapp_opted_in": False,
            "synthetic": True,
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    yield database
    await client.drop_database(name)
    client.close()


@pytest_asyncio.fixture()
async def redis() -> AsyncIterator:
    client = aioredis.from_url(REDIS_URI)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


# ---------------------------------------------------------------------------
# A real push service, on loopback.
# ---------------------------------------------------------------------------


class PushServiceStub:
    """An HTTP endpoint that behaves like a push service.

    NOT a fake adapter — the adapter under test is the real one. This is the
    other end of the wire, and it exists because RFC 8030 puts the push service
    outside our system by design: the endpoint URL comes from the browser and
    is data to us. Standing one up on loopback is what lets the suite exercise
    real ECDH, real HKDF, real AES128GCM and real ES256 without reaching the
    internet, which is also why `test_no_live_network.py` needs no exception
    for `webpush.py`.

    It DECRYPTS what it receives, using the subscription's private key, so the
    tests can assert on the message a browser would actually show. A stub that
    only counted requests would pass against an adapter that encrypted to the
    wrong key — which is the single most likely defect in a push
    implementation and the one with no symptom short of a silent phone.
    """

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.status = 201
        self._private = ec.generate_private_key(ec.SECP256R1())
        self._auth = uuid.uuid4().bytes  # 16 bytes, as RFC 8291 requires
        self._server: asyncio.Server | None = None
        self.port = 0

    @property
    def subscription(self) -> PushSubscription:
        public = self._private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return PushSubscription(
            endpoint=f"http://127.0.0.1:{self.port}/push/{uuid.uuid4().hex}",
            p256dh=b64url(public),
            auth=b64url(self._auth),
        )

    def decrypt(self, body: bytes) -> dict:
        """RFC 8291 in reverse, with the receiver's key. See the class doc."""
        salt = body[:16]
        idlen = body[20]
        as_public_bytes = body[21 : 21 + idlen]
        ciphertext = body[21 + idlen :]
        ua_public_bytes = self._private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        shared = self._private.exchange(
            ec.ECDH(),
            ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), as_public_bytes
            ),
        )
        ikm = _hkdf(
            salt=self._auth,
            ikm=shared,
            info=b"WebPush: info\x00" + ua_public_bytes + as_public_bytes,
            length=32,
        )
        cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
        plaintext = AESGCM(cek).decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.rstrip(b"\x02\x01"))

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            headers_raw = await reader.readuntil(b"\r\n\r\n")
            head = headers_raw.decode("latin-1")
            headers = {}
            for line in head.split("\r\n")[1:]:
                name, _, value = line.partition(":")
                if name:
                    headers[name.strip().lower()] = value.strip()
            length = int(headers.get("content-length", "0"))
            body = await reader.readexactly(length) if length else b""
            self.received.append({"headers": headers, "body": body})
            writer.write(
                f"HTTP/1.1 {self.status} X\r\nContent-Length: 0\r\n"
                f"Location: https://push.invalid/m/{len(self.received)}\r\n\r\n".encode()
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()


@pytest_asyncio.fixture()
async def push_service() -> AsyncIterator[PushServiceStub]:
    stub = PushServiceStub()
    await stub.start()
    yield stub
    await stub.stop()


@pytest.fixture()
def vapid() -> VapidKeypair:
    """A keypair generated for this run. §6.2's applicationServerKey needs no
    account — which is what makes generating one per test reasonable."""
    return VapidKeypair.generate()


# ---------------------------------------------------------------------------
# Mailpit — a REAL SMTP server, when the compose stack has one.
# ---------------------------------------------------------------------------


def mailpit_available() -> bool:
    try:
        with socket.create_connection(MAILPIT_SMTP, timeout=0.5):
            return True
    except OSError:
        return False


requires_mailpit = pytest.mark.skipif(
    not mailpit_available(),
    reason=(
        "Mailpit is not running. `docker compose -f infra/docker-compose.dev.yml "
        "up -d mailpit`. Deliberately SKIPPED rather than substituted: a fake "
        "SMTP sink would accept messages a real server rejects, and §23.3's "
        "email rung is IMPLEMENTED precisely because it speaks the real protocol."
    ),
)


async def mailpit_messages() -> list[dict]:
    import httpx

    async with httpx.AsyncClient(base_url=MAILPIT_API, timeout=5.0) as client:
        response = await client.get("/api/v1/messages")
        return response.json().get("messages", [])


async def mailpit_clear() -> None:
    import httpx

    async with httpx.AsyncClient(base_url=MAILPIT_API, timeout=5.0) as client:
        await client.delete("/api/v1/messages")


# ---------------------------------------------------------------------------
# The service, wired the way `notifications.wiring` wires it.
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_service(db, redis):  # noqa: ANN001, ANN201
    """Build a `NotificationService` with a chosen adapter map.

    Takes the adapters as an argument rather than reading configuration,
    because the interesting §23.3 cases are about which channels EXIST: no
    push, push-that-fails, push-plus-email. Every other collaborator is the
    real one.
    """

    def build(adapters) -> NotificationService:  # noqa: ANN001
        subscriptions = PushSubscriptionStore(db)
        return NotificationService(
            store=NotificationStore(db),
            preferences=PreferenceStore(db, redis),
            subscriptions=subscriptions,
            adapters=adapters,
            dedupe=Dedupe(redis),
            emergency_stop=EmergencyStop(redis),
            recipients=RecipientResolver(db, subscriptions),
        )

    return build


class RecordingChannel:
    """An adapter that records what it was given and answers as told.

    This IS a test double and it is used only where the thing under test is the
    SERVICE — the gate order, the caps, the ladder's mode. The channels have
    their own tests against their own real protocols; using a real push service
    to assert that §23.1's cap blocks a fourth message would be testing the cap
    through two layers of crypto.
    """

    def __init__(self, channel, name, *, accept=True, failure=None) -> None:  # noqa: ANN001
        self.channel = channel
        self.name = name
        self.accept = accept
        self.failure = failure
        self.sent: list = []

    async def send(self, delivery):  # noqa: ANN001, ANN201
        from sitara_api.notifications.providers.base import DeliveryOutcome

        self.sent.append(delivery)
        if self.accept:
            return DeliveryOutcome(
                accepted=True, provider=self.name, provider_message_id="rec-1"
            )
        return DeliveryOutcome(accepted=False, provider=self.name, failure=self.failure)


__all__ = [
    "IST",
    "NOW",
    "OTHER_USER_ID",
    "USER_ID",
    "PushServiceStub",
    "RecordingChannel",
    "b64url",
    "b64url_decode",
    "mailpit_clear",
    "mailpit_messages",
    "requires_mailpit",
    "struct",
]
