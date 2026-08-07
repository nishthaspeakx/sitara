"""API surface tests: happy paths + the §34.4 error envelope on every failure."""

from fastapi.testclient import TestClient

from sitara_astro.main import app

NATAL_PAYLOAD = {
    "birth": {
        "date": "1990-05-15",
        "time": "14:30:00",
        "fold": None,
        "place": {"name": "New Delhi, India", "lat": 28.6139, "lon": 77.2090, "tz": "Asia/Kolkata"},
    },
    "options": {
        "node_type": "mean",
        "bhava_system": "sripati",
        "dasha_year": "days_365_25",
        "gap_policy": "shift_forward",
    },
    "subject": "user123",
    "chart_version": 1,
}


def assert_envelope(body: dict, code: str) -> None:
    assert set(body) == {"code", "message_key", "trace_id", "retryable"}
    assert body["code"] == code


def client() -> TestClient:
    return TestClient(app)


def test_healthz_still_works() -> None:
    with client() as c:
        response = c.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_natal_happy_path() -> None:
    with client() as c:
        response = c.post("/v1/facts/natal", json=NATAL_PAYLOAD)
    assert response.status_code == 200
    facts = response.json()["facts"]
    assert len(facts) == 29
    sample = facts[0]
    assert set(sample) == {
        "fact_id", "kind", "value", "precision", "method",
        "valid_from", "valid_to", "engine_semver", "data_revision",
    }


def test_dasha_happy_path() -> None:
    with client() as c:
        response = c.post("/v1/facts/dasha", json=NATAL_PAYLOAD)
    assert response.status_code == 200
    assert len(response.json()["facts"]) == 9 + 81 + 729


def test_transits_happy_path() -> None:
    payload = {**NATAL_PAYLOAD, "transit_date_utc": "2026-07-28"}
    with client() as c:
        response = c.post("/v1/facts/transits", json=payload)
    assert response.status_code == 200
    facts = response.json()["facts"]
    assert len(facts) == 18
    # the SPEC §5.2 example id appears verbatim when chart_version=3:
    payload_v3 = {**payload, "chart_version": 3}
    with client() as c:
        response = c.post("/v1/facts/transits", json=payload_v3)
    assert any(
        f["fact_id"] == "fact:transit.saturn.house/2026-07-28/user123@v3"
        for f in response.json()["facts"]
    )


def test_malformed_body_returns_sys_validation_envelope() -> None:
    with client() as c:
        response = c.post("/v1/facts/natal", json={"birth": {"date": "not-a-date"}})
    assert response.status_code == 400
    assert_envelope(response.json(), "SYS_VALIDATION")


def test_gap_birth_with_error_policy_returns_astro_envelope() -> None:
    payload = {
        **NATAL_PAYLOAD,
        "birth": {
            "date": "2015-03-08",
            "time": "02:30:00",
            "fold": None,
            "place": {"name": "New York, USA", "lat": 40.7128, "lon": -74.0060,
                      "tz": "America/New_York"},
        },
        "options": {**NATAL_PAYLOAD["options"], "gap_policy": "error"},
    }
    with client() as c:
        response = c.post("/v1/facts/natal", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert_envelope(body, "ASTRO_INSUFFICIENT_BIRTH_DATA")
    assert body["retryable"] is False


def test_unknown_timezone_returns_place_unresolved() -> None:
    payload = {
        **NATAL_PAYLOAD,
        "birth": {**NATAL_PAYLOAD["birth"],
                  "place": {"name": "Atlantis", "lat": 0.0, "lon": 0.0, "tz": "Asia/Atlantis"}},
    }
    with client() as c:
        response = c.post("/v1/facts/natal", json=payload)
    assert response.status_code == 422
    assert_envelope(response.json(), "ASTRO_PLACE_UNRESOLVED")


NUMEROLOGY_PAYLOAD = {"dob": "1990-05-15", "subject": "user123", "chart_version": 1}


class TestNumerologyRoute:
    """Internal route (§6.3): sitara-api fronts this publicly, nothing else."""

    def test_date_only_returns_moolank_and_bhagyank(self) -> None:
        with client() as c:
            response = c.post("/v1/facts/numerology", json=NUMEROLOGY_PAYLOAD)
        assert response.status_code == 200
        facts = response.json()["facts"]
        assert {f["kind"] for f in facts} == {"numerology.moolank", "numerology.bhagyank"}
        moolank = next(f for f in facts if f["kind"] == "numerology.moolank")
        assert moolank["value"]["value"] == 6  # 15 → 6
        assert moolank["precision"] == {"tolerance": 0.0, "unit": "exact"}

    def test_confirmed_devanagari_name_adds_both_systems(self) -> None:
        payload = {**NUMEROLOGY_PAYLOAD, "name_as_entered": "लक्ष्मी", "name_confirmed": True}
        with client() as c:
            response = c.post("/v1/facts/numerology", json=payload)
        assert response.status_code == 200
        names = [f for f in response.json()["facts"] if f["kind"] == "numerology.name_number"]
        assert {f["value"]["system"] for f in names} == {"chaldean", "pythagorean"}
        assert all(f["value"]["latin_name"] == "Lakshmi" for f in names)

    def test_unconfirmed_name_is_refused_not_guessed(self) -> None:
        payload = {**NUMEROLOGY_PAYLOAD, "name_as_entered": "लक्ष्मी"}
        with client() as c:
            response = c.post("/v1/facts/numerology", json=payload)
        assert response.status_code == 422
        assert_envelope(response.json(), "ASTRO_NAME_UNCONFIRMED")

    def test_invalid_name_is_a_distinct_code(self) -> None:
        payload = {**NUMEROLOGY_PAYLOAD, "name_as_entered": "12345"}
        with client() as c:
            response = c.post("/v1/facts/numerology", json=payload)
        assert response.status_code == 400
        assert_envelope(response.json(), "ASTRO_NAME_INVALID")

    def test_error_body_never_echoes_the_name(self) -> None:
        payload = {**NUMEROLOGY_PAYLOAD, "name_as_entered": "Zzyzxqvw 1985"}
        with client() as c:
            response = c.post("/v1/facts/numerology", json=payload)
        assert "Zzyzxqvw" not in response.text  # §13
