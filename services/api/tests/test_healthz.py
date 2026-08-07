from fastapi.testclient import TestClient

from sitara_api.main import app

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "sitara-api"


def test_shared_schemas_importable() -> None:
    from sitara_schemas import ErrorCode, MorningModule

    assert len(list(MorningModule)) == 17
    assert ErrorCode.SYS_INTERNAL.value == "SYS_INTERNAL"
