"""§34.5 token-exchange happy path: Firebase ID token → one-time POST /auth/session
→ httpOnly access + refresh cookies; §33.2 users + auth_identities created.
"""

from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.config import Settings

from .conftest import FakeVerifier, assert_envelope, exchange


def test_signup_happy_path_sets_httponly_cookies(
    client: TestClient, verifier: FakeVerifier
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")

    resp = exchange(client, "tok-1", locale="hi")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new_user"] is True
    assert body["locale"] == "hi"
    assert body["user_id"]

    # Both session cookies present and httpOnly (§34.5 / §6.2).
    cookie_headers = [h for h in resp.headers.get_list("set-cookie")]
    access = next(h for h in cookie_headers if h.startswith("sitara_access="))
    refresh = next(h for h in cookie_headers if h.startswith("sitara_refresh="))
    for h in (access, refresh):
        assert "httponly" in h.lower()
    # Refresh cookie is scoped to the auth surface only.
    assert "path=/auth" in refresh.lower()


def test_signup_creates_user_and_auth_identity(
    client: TestClient, verifier: FakeVerifier, mongo: MongoClient, settings: Settings
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    body = exchange(client, "tok-1").json()

    db = mongo[settings.mongo_db]
    user = db.users.find_one({"firebase_uid": "fb-uid-1"})
    assert user is not None
    assert str(user["_id"]) == body["user_id"]
    assert user["status"] == "active"
    assert user["phone"] == "+911234500001"  # contact REPLICA only (§33.2)
    for field in ("created_at", "updated_at", "schema_v"):  # §6.4 doc contract
        assert field in user

    identity = db.auth_identities.find_one({"provider": "phone", "provider_uid": "fb-uid-1"})
    assert identity is not None
    assert identity["user_id"] == user["_id"]
    assert identity["verified_at"] is not None
    assert identity["linked_at"] is not None


def test_returning_user_needs_no_dob(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    first = exchange(client, "tok-1")
    assert first.status_code == 200
    user_id = first.json()["user_id"]

    again = exchange(client, "tok-1", dob=None)
    assert again.status_code == 200
    assert again.json()["is_new_user"] is False
    assert again.json()["user_id"] == user_id


def test_signup_without_dob_is_rejected(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    resp = exchange(client, "tok-1", dob=None)
    assert resp.status_code == 400
    assert_envelope(resp.json(), "SYS_VALIDATION", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.dob_required"


def test_invalid_token_rejected_with_envelope(client: TestClient) -> None:
    resp = exchange(client, "not-a-real-token")
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_INVALID_TOKEN", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.invalid_token"


def test_apple_provider_is_config_flagged_stub(
    client: TestClient, verifier: FakeVerifier
) -> None:
    """§26.1 decision log: Apple deferred to M+2; slot exists, flag off → honest error."""
    verifier.add("tok-apple", uid="fb-uid-a", provider="apple", email="a@example.com")
    resp = exchange(client, "tok-apple")
    assert resp.status_code == 403
    assert_envelope(resp.json(), "AUTH_FORBIDDEN", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.apple_unavailable"


def test_duplicate_contact_offers_link_never_silent_merge(
    client: TestClient, verifier: FakeVerifier, mongo: MongoClient, settings: Settings
) -> None:
    """§27 sign-up row: same person, phone then Google → offer LINK at sign-in;
    never silently create a second account or merge (§32.12)."""
    verifier.add(
        "tok-phone", uid="fb-uid-1", provider="phone",
        phone="+911234500001", email="n@example.com",
    )
    assert exchange(client, "tok-phone").status_code == 200

    verifier.add("tok-google", uid="fb-uid-2", provider="google", email="n@example.com")
    resp = exchange(client, "tok-google")
    assert resp.status_code == 409
    assert_envelope(resp.json(), "AUTH_PROVIDER_CONFLICT", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.link_offer"

    db = mongo[settings.mongo_db]
    assert db.users.count_documents({}) == 1  # zero duplicate-account states
