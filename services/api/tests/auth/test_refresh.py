"""§22.5 refresh-token rotation: every refresh mints a new token; a reused
(rotated-away) token means theft → the whole session dies; expiry honoured.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.config import Settings

from .conftest import FakeVerifier, assert_envelope, exchange


def _refresh_cookie(client: TestClient) -> str:
    value = client.cookies.get("sitara_refresh")
    assert value
    return value


def test_refresh_rotates_tokens(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    exchange(client, "tok-1")
    old_refresh = _refresh_cookie(client)
    old_access = client.cookies.get("sitara_access")

    resp = client.post("/auth/session/refresh")
    assert resp.status_code == 200
    assert _refresh_cookie(client) != old_refresh
    assert client.cookies.get("sitara_access") != old_access

    # The rotated-to session still works.
    assert client.get("/auth/sessions").status_code == 200


def test_reused_refresh_token_revokes_the_session(
    client: TestClient, verifier: FakeVerifier
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    exchange(client, "tok-1")
    stolen = _refresh_cookie(client)

    assert client.post("/auth/session/refresh").status_code == 200
    fresh = _refresh_cookie(client)

    # Replay of the rotated-away token → theft signal → 401 and full revocation.
    client.cookies.set("sitara_refresh", stolen)
    replay = client.post("/auth/session/refresh")
    assert replay.status_code == 401
    assert_envelope(replay.json(), "AUTH_SESSION_EXPIRED", retryable=False)

    # Even the newest token is now dead — stolen sessions don't limp on (§22.5).
    client.cookies.set("sitara_refresh", fresh)
    resp = client.post("/auth/session/refresh")
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_SESSION_EXPIRED", retryable=False)


def test_expired_refresh_token_rejected(
    client: TestClient, verifier: FakeVerifier, mongo: MongoClient, settings: Settings
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    exchange(client, "tok-1")

    mongo[settings.mongo_db].sessions.update_many(
        {}, {"$set": {"refresh_expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )
    resp = client.post("/auth/session/refresh")
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_SESSION_EXPIRED", retryable=False)


def test_refresh_without_cookie_rejected(client: TestClient) -> None:
    resp = client.post("/auth/session/refresh")
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_SESSION_EXPIRED", retryable=False)
