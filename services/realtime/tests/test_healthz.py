import json

from fastapi.testclient import TestClient
from sitara_schemas import ControlEventType

from sitara_realtime.main import app

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["service"] == "sitara-realtime"


def test_ws_session_ready_is_typed_from_shared_schema() -> None:
    with client.websocket_connect("/call/session") as ws:
        event = json.loads(ws.receive_text())
        assert event["type"] == ControlEventType.SESSION_READY.value
        assert set(event.keys()) == {"type", "seq", "ts", "payload"}
