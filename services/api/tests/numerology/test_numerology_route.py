"""Public numerology facade (§6.3 boundary, §5.4 confidence, §22.10 flow).

The adapter is faked so these tests pin the facade's contract, not the engine's
arithmetic — that is covered by the astro service's own suite and the 500-case
hand-check set.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sitara_schemas import ErrorCode
from sitara_schemas.facts import (
    BhagyankValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    MasterNumberPolicy,
    MoolankValue,
    NameNumberValue,
    NameSource,
    NumerologySystem,
)

from sitara_api.app import create_app
from sitara_api.config import Settings
from sitara_api.errors import ApiError

EXACT = FactPrecision(tolerance=0.0, unit="exact")
BORN = datetime(1990, 5, 15, tzinfo=UTC)


def fact(kind: FactKind, fact_id: str, value: object, method: FactMethod) -> FactSnapshot:
    return FactSnapshot(
        fact_id=fact_id,
        kind=kind,
        value=value,  # type: ignore[arg-type]
        precision=EXACT,
        method=method,
        valid_from=BORN,
        valid_to=None,
        engine_semver="0.1.0",
        data_revision="tables=chaldean.v1+pythagorean.v1",
    )


DATE_METHOD = FactMethod(master_numbers=MasterNumberPolicy.REDUCE)
NAME_METHOD = FactMethod(
    master_numbers=MasterNumberPolicy.REDUCE,
    numerology_system=NumerologySystem.CHALDEAN,
    name_source=NameSource.CONFIRMED_TRANSLITERATION,
    transliteration_scheme="iso15919",
)

DATE_ONLY_FACTS = [
    fact(
        FactKind.NUMEROLOGY_MOOLANK,
        "fact:numerology.moolank/profile/user123@v1",
        MoolankValue(value=6, birth_day=15, reduction_steps=(15, 6)),
        DATE_METHOD,
    ),
    fact(
        FactKind.NUMEROLOGY_BHAGYANK,
        "fact:numerology.bhagyank/profile/user123@v1",
        BhagyankValue(value=3, digits=(1, 9, 9, 0, 0, 5, 1, 5), reduction_steps=(30, 3)),
        DATE_METHOD,
    ),
]

NAME_FACT = fact(
    FactKind.NUMEROLOGY_NAME_NUMBER,
    "fact:numerology.name_number.chaldean/profile/user123@v1",
    NameNumberValue(
        system=NumerologySystem.CHALDEAN,
        value=1,
        compound_value=19,
        latin_name="Lakshmi",
        letter_values=(("L", 3), ("A", 1), ("K", 2), ("S", 3), ("H", 5), ("M", 4), ("I", 1)),
        reduction_steps=(19, 10, 1),
    ),
    NAME_METHOD,
)


class FakeAdapter:
    """Records the payload the facade forwards, returns a scripted result."""

    def __init__(self, facts=None, error: ErrorCode | None = None) -> None:  # noqa: ANN001
        self.facts = facts if facts is not None else DATE_ONLY_FACTS
        self.error = error
        self.seen: dict | None = None

    async def compute(self, payload: dict):  # noqa: ANN201
        self.seen = payload
        if self.error:
            raise ApiError(self.error)
        return self.facts


@pytest.fixture()
def client_factory():  # noqa: ANN201
    def make(adapter: FakeAdapter) -> Iterator[TestClient]:
        app = create_app(Settings())
        app.state.numerology_adapter = adapter
        return TestClient(app)

    return make


def post(client: TestClient, **overrides):  # noqa: ANN201
    body = {"dob": "1990-05-15", "chart_version": 1}
    body.update(overrides)
    return client.post("/v1/numerology/profile", json=body)


class TestHappyPath:
    def test_date_only_reveal_returns_moolank_and_bhagyank(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter()
        with client_factory(adapter) as client:
            response = post(client)
        assert response.status_code == 200
        body = response.json()
        assert len(body["facts"]) == 2
        kinds = {f["kind"] for f in body["facts"]}
        assert kinds == {"numerology.moolank", "numerology.bhagyank"}

    def test_full_snapshots_are_returned_for_embedding(self, client_factory) -> None:  # noqa: ANN001
        """§34.2: the artefact embeds the whole snapshot, not a fact-ID."""
        with client_factory(FakeAdapter()) as client:
            body = post(client).json()
        assert set(body["facts"][0]) == {
            "fact_id", "kind", "value", "precision", "method",
            "valid_from", "valid_to", "engine_semver", "data_revision",
        }

    def test_confirmed_name_adds_name_numbers(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter(facts=[*DATE_ONLY_FACTS, NAME_FACT])
        with client_factory(adapter) as client:
            response = post(client, name_as_entered="लक्ष्मी", name_confirmed=True)
        assert response.status_code == 200
        assert len(response.json()["facts"]) == 3

    def test_forwards_the_confirmation_flags_verbatim(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter()
        with client_factory(adapter) as client:
            post(client, name_as_entered="लक्ष्मी", name_confirmed=True,
                 name_edited_latin="Laxmi")
        assert adapter.seen is not None
        assert adapter.seen["name_as_entered"] == "लक्ष्मी"
        assert adapter.seen["name_confirmed"] is True
        assert adapter.seen["name_edited_latin"] == "Laxmi"


class TestConfidenceState:
    """§5.4 — the state is computed, stored and rendered; never fabricated."""

    def test_name_plus_dob_is_verified(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter(facts=[*DATE_ONLY_FACTS, NAME_FACT])
        with client_factory(adapter) as client:
            assert post(client, name_as_entered="Lakshmi").json()["confidence"] == "verified"

    def test_date_only_is_verified_limited(self, client_factory) -> None:  # noqa: ANN001
        with client_factory(FakeAdapter()) as client:
            assert post(client).json()["confidence"] == "verified_limited_birth_data"

    def test_no_facts_is_cannot_calculate(self, client_factory) -> None:  # noqa: ANN001
        with client_factory(FakeAdapter(facts=[])) as client:
            assert post(client).json()["confidence"] == "cannot_calculate"

    def test_confidence_is_a_closed_enum_value(self, client_factory) -> None:  # noqa: ANN001
        from sitara_schemas.facts import ConfidenceState

        with client_factory(FakeAdapter()) as client:
            assert post(client).json()["confidence"] in {s.value for s in ConfidenceState}


class TestErrorEnvelopes:
    """§34.4 — one envelope, one taxonomy, upstream codes passed through."""

    def assert_envelope(self, body: dict, code: str) -> None:
        assert set(body) == {"code", "message_key", "trace_id", "retryable"}
        assert body["code"] == code

    def test_unconfirmed_name_reaches_the_client_as_422(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter(error=ErrorCode.ASTRO_NAME_UNCONFIRMED)
        with client_factory(adapter) as client:
            response = post(client, name_as_entered="लक्ष्मी")
        assert response.status_code == 422
        self.assert_envelope(response.json(), "ASTRO_NAME_UNCONFIRMED")

    def test_invalid_name_reaches_the_client_as_400(self, client_factory) -> None:  # noqa: ANN001
        """Finding 3: the two name codes are distinct all the way to the wire."""
        adapter = FakeAdapter(error=ErrorCode.ASTRO_NAME_INVALID)
        with client_factory(adapter) as client:
            response = post(client, name_as_entered="12345")
        assert response.status_code == 400
        self.assert_envelope(response.json(), "ASTRO_NAME_INVALID")

    def test_engine_down_is_retryable_503(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter(error=ErrorCode.ASTRO_ENGINE_UNAVAILABLE)
        with client_factory(adapter) as client:
            response = post(client)
        assert response.status_code == 503
        assert response.json()["retryable"] is True

    def test_malformed_body_is_sys_validation(self, client_factory) -> None:  # noqa: ANN001
        with client_factory(FakeAdapter()) as client:
            response = client.post("/v1/numerology/profile", json={"dob": "not-a-date"})
        assert response.status_code == 400
        self.assert_envelope(response.json(), "SYS_VALIDATION")

    def test_overlong_name_is_rejected_before_the_engine(self, client_factory) -> None:  # noqa: ANN001
        adapter = FakeAdapter()
        with client_factory(adapter) as client:
            response = post(client, name_as_entered="A" * 500)
        assert response.status_code == 400
        assert adapter.seen is None  # never forwarded


class TestNoPiiInLogs:
    """§13 — the facade must not log the name or the date of birth."""

    def test_error_path_logs_nothing_identifying(self, client_factory, caplog) -> None:  # noqa: ANN001
        import logging

        adapter = FakeAdapter(error=ErrorCode.ASTRO_ENGINE_UNAVAILABLE)
        with caplog.at_level(logging.DEBUG), client_factory(adapter) as client:
            post(client, name_as_entered="Zzyzxqvw")
        for sentinel in ("Zzyzxqvw", "1990-05-15"):
            assert sentinel not in caplog.text
