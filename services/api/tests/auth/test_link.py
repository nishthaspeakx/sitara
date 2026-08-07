"""§22.5 account linking (step-up stub in M1) and the §32.12 choose-flow:
duplicate-provider conflict → the user chooses explicitly, side-by-side;
the losing record is archived, never merged; no automatic winner, ever.
"""

from fastapi.testclient import TestClient

from .conftest import FakeVerifier, assert_envelope, exchange


def _signed_in(client: TestClient, verifier: FakeVerifier, uid: str, phone: str) -> None:
    token = f"tok-{uid}"
    verifier.add(token, uid=uid, provider="phone", phone=phone)
    assert exchange(client, token).status_code == 200


def test_link_new_provider_succeeds(client: TestClient, verifier: FakeVerifier) -> None:
    _signed_in(client, verifier, "fb-uid-1", "+911234500001")
    verifier.add("tok-g", uid="fb-uid-1g", provider="google", email="n@example.com")

    resp = client.post("/auth/link", json={"id_token": "tok-g", "step_up_token": "stub"})
    assert resp.status_code == 200
    assert resp.json()["linked"] is True
    assert resp.json()["provider"] == "google"


def test_link_same_identity_is_idempotent(client: TestClient, verifier: FakeVerifier) -> None:
    _signed_in(client, verifier, "fb-uid-1", "+911234500001")
    verifier.add("tok-g", uid="fb-uid-1g", provider="google", email="n@example.com")
    client.post("/auth/link", json={"id_token": "tok-g", "step_up_token": "stub"})

    resp = client.post("/auth/link", json={"id_token": "tok-g", "step_up_token": "stub"})
    assert resp.status_code == 200
    assert resp.json()["linked"] is True


def test_duplicate_provider_conflict_returns_choose_flow(
    client: TestClient, verifier: FakeVerifier
) -> None:
    # User B owns the google identity...
    verifier.add("tok-b", uid="fb-uid-b", provider="google", email="b@example.com")
    exchange(client, "tok-b")
    client.cookies.clear()

    # ...and user A tries to link that same identity.
    _signed_in(client, verifier, "fb-uid-a", "+911234500001")
    resp = client.post("/auth/link", json={"id_token": "tok-b", "step_up_token": "stub"})

    assert resp.status_code == 409
    assert_envelope(resp.json(), "AUTH_PROVIDER_CONFLICT", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.provider_conflict"

    # §32.12 choose-flow contract, fetched as its own resource (the error body
    # stays the frozen §34.4 envelope).
    flow = client.get("/auth/link/conflict")
    assert flow.status_code == 200
    contract = flow.json()
    assert contract["provider"] == "google"
    assert contract["conflict_id"]
    choices = {opt["choice"] for opt in contract["options"]}
    assert choices == {"keep_current", "keep_other"}
    for opt in contract["options"]:
        assert "user_id" in opt["account"]
        assert "birth_details" in opt["account"]  # side-by-side data (null until M-birth)
    assert contract["losing_record"] == "archived"  # never merged
    assert contract["automatic_winner"] is False  # no automatic winner, ever


def test_link_requires_authentication(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-g", uid="fb-uid-1g", provider="google", email="n@example.com")
    resp = client.post("/auth/link", json={"id_token": "tok-g", "step_up_token": "stub"})
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_INVALID_TOKEN", retryable=False)


def test_link_apple_while_flag_off_rejected(client: TestClient, verifier: FakeVerifier) -> None:
    _signed_in(client, verifier, "fb-uid-1", "+911234500001")
    verifier.add("tok-a", uid="fb-uid-1a", provider="apple", email="n@icloud.com")
    resp = client.post("/auth/link", json={"id_token": "tok-a", "step_up_token": "stub"})
    assert resp.status_code == 403
    assert_envelope(resp.json(), "AUTH_FORBIDDEN", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.apple_unavailable"
