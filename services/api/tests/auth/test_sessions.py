"""§22.5 device/session management: sessions list (device, created, last active,
current) + remote sign-out; logout clears the current session.
"""

from fastapi.testclient import TestClient

from .conftest import FakeVerifier, assert_envelope, exchange


def test_sessions_list_requires_auth(client: TestClient) -> None:
    resp = client.get("/auth/sessions")
    assert resp.status_code == 401
    assert_envelope(resp.json(), "AUTH_INVALID_TOKEN", retryable=False)


def test_sessions_list_and_remote_revoke(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")

    # Device 1 signs up, device 2 signs in — one client, two cookie jars.
    exchange(client, "tok-1", device_name="Pixel 8")
    phone_cookies = dict(client.cookies)
    client.cookies.clear()
    exchange(client, "tok-1", dob=None, device_name="MacBook")

    listing = client.get("/auth/sessions").json()["sessions"]
    assert len(listing) == 2
    names = {s["device_name"] for s in listing}
    assert names == {"Pixel 8", "MacBook"}
    current = [s for s in listing if s["current"]]
    assert len(current) == 1
    assert current[0]["device_name"] == "MacBook"
    for s in listing:
        assert s["created_at"] and s["last_active_at"]

    # Remote sign-out of the phone (§22.5): its refresh dies immediately.
    other_id = next(s["session_id"] for s in listing if not s["current"])
    assert client.delete(f"/auth/sessions/{other_id}").status_code == 204

    client.cookies.clear()
    for name, value in phone_cookies.items():
        client.cookies.set(name, value)
    replay = client.post("/auth/session/refresh")
    assert replay.status_code == 401


def test_logout_clears_current_session(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    exchange(client, "tok-1")
    assert client.get("/auth/sessions").status_code == 200

    resp = client.delete("/auth/session")
    assert resp.status_code == 204

    assert client.get("/auth/sessions").status_code == 401
    assert client.post("/auth/session/refresh").status_code == 401
