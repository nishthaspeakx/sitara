"""§27 account-recovery row (P0): 5 OTP fails → 15-minute lock, Redis-backed.
The server backstops Firebase's client-side limits at the exchange endpoint.
"""

from fastapi.testclient import TestClient

from .conftest import FakeVerifier, assert_envelope, exchange


def test_five_failures_lock_the_caller(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-good", uid="fb-uid-1", provider="phone", phone="+911234500001")

    for _ in range(5):
        assert exchange(client, "tok-bad").status_code == 401

    # Locked now — even a VALID token is refused for the lock window.
    resp = exchange(client, "tok-good")
    assert resp.status_code == 429
    assert_envelope(resp.json(), "AUTH_OTP_THROTTLED", retryable=True)
    assert resp.json()["message_key"] == "errors.auth.otp_throttled"


def test_four_failures_do_not_lock(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-good", uid="fb-uid-1", provider="phone", phone="+911234500001")
    for _ in range(4):
        exchange(client, "tok-bad")
    assert exchange(client, "tok-good").status_code == 200


def test_success_resets_the_fail_counter(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-good", uid="fb-uid-1", provider="phone", phone="+911234500001")
    for _ in range(4):
        exchange(client, "tok-bad")
    assert exchange(client, "tok-good").status_code == 200

    # Counter reset on success: four more failures still don't lock.
    for _ in range(4):
        exchange(client, "tok-bad")
    assert exchange(client, "tok-good").status_code == 200
