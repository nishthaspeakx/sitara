import json

from fastapi.testclient import TestClient
from sitara_schemas import ControlEventType

from sitara_realtime.main import app

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["service"] == "sitara-realtime"


def test_the_call_socket_says_nothing_until_it_knows_who_is_calling() -> None:
    """§34.5/§34.6 — a socket is not a session.

    **This test used to assert the opposite**, because through M9 `/call/session`
    was the M0 stub: it accepted, volunteered a typed `session.ready` to anyone
    who connected, and echoed. That was honest as a stub and is a hole as a
    service — a call grants microphone access, spends §7.3 minutes and runs §9
    on behalf of a user id, and none of those may happen for a connection that
    has presented no ticket.

    So the assertion is inverted, and the old one is recorded here rather than
    deleted: an unauthenticated connection gets an `error`, never a `ready`.
    """
    with client.websocket_connect("/call/session") as ws:
        ws.send_text(
            json.dumps({"type": "session.start", "seq": 0, "ts": 0, "payload": {}})
        )
        event = json.loads(ws.receive_text())

    assert event["type"] == ControlEventType.ERROR.value
    assert event["payload"]["code"] == "AUTH_INVALID_TOKEN"


def test_every_event_carries_the_shared_envelope() -> None:
    """The §34.6 five-field frame, from `sitara_schemas` and not re-declared.

    Kept from the M0 test, because the thing it was really guarding — that the
    envelope is the schema package's and that `ack` is on it — is still worth
    guarding, and is now checkable on a frame the socket sends for a reason.
    """
    with client.websocket_connect("/call/session") as ws:
        ws.send_text(
            json.dumps({"type": "session.start", "seq": 7, "ts": 0, "payload": {}})
        )
        event = json.loads(ws.receive_text())

    assert set(event.keys()) == {"type", "seq", "ts", "ack", "payload"}
