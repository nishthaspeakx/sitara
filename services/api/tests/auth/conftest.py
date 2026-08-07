"""Auth test harness (SPEC §33.2/§34.5): real Mongo+Redis from the dev stack,
Firebase Admin verification replaced by a fake — token verification is the ONE
external boundary in this module (§6.3 adapter rule).
"""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
import redis as redis_sync
from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.app import create_app
from sitara_api.auth.firebase import InvalidFirebaseToken, VerifiedIdentity, get_verifier
from sitara_api.config import Settings

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER a machine-local mongod
REDIS_URI = "redis://localhost:6379/15"  # db 15 reserved for tests, flushed per test

ADULT_DOB = "1990-01-15"


class FakeVerifier:
    """Maps opaque token strings to verified identities; unknown tokens raise."""

    def __init__(self) -> None:
        self.tokens: dict[str, VerifiedIdentity] = {}

    def add(
        self,
        token: str,
        uid: str,
        provider: str = "phone",
        phone: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> None:
        self.tokens[token] = VerifiedIdentity(
            uid=uid, provider=provider, phone=phone, email=email, display_name=display_name
        )

    def verify(self, id_token: str) -> VerifiedIdentity:
        try:
            return self.tokens[id_token]
        except KeyError:
            raise InvalidFirebaseToken() from None


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        mongodb_uri=MONGO_URI,
        mongo_db=f"sitara_test_{uuid.uuid4().hex[:8]}",
        redis_url=REDIS_URI,
        apple_signin_enabled=False,
        cookie_secure=False,
    )


@pytest.fixture()
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture()
def client(settings: Settings, verifier: FakeVerifier) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_verifier] = lambda: verifier
    with TestClient(app) as c:
        yield c
    MongoClient(MONGO_URI).drop_database(settings.mongo_db)
    r = redis_sync.Redis.from_url(REDIS_URI)
    r.flushdb()
    r.close()


@pytest.fixture()
def mongo(settings: Settings) -> Iterator[MongoClient]:
    mc: MongoClient = MongoClient(MONGO_URI)
    yield mc
    mc.close()


def exchange(
    client: TestClient,
    token: str,
    dob: str | None = ADULT_DOB,
    locale: str = "en",
    device_name: str | None = None,
):
    body: dict[str, object] = {"id_token": token, "locale": locale}
    if dob is not None:
        body["date_of_birth"] = dob
    if device_name is not None:
        body["device_name"] = device_name
    return client.post("/auth/session", json=body)


def assert_envelope(body: dict, code: str, retryable: bool) -> None:
    """§34.4 — the one canonical error shape, nothing more, nothing less."""
    assert set(body.keys()) == {"code", "message_key", "trace_id", "retryable"}
    assert body["code"] == code
    assert body["retryable"] is retryable
    assert body["trace_id"]


def years_ago(years: int, plus_days: int = 0) -> str:
    from datetime import timedelta

    today = date.today()
    try:
        d = today.replace(year=today.year - years)
    except ValueError:  # Feb 29
        d = today.replace(year=today.year - years, day=today.day - 1)
    return (d + timedelta(days=plus_days)).isoformat()
