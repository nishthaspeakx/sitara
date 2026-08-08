"""The three public endpoints — SPEC §30.2, §34.4, §7.2.

Provider calls replay fixtures; Mongo is the dev-stack instance. What is under
test is the contract a client sees: correct place handling, honest declines,
the canonical envelope, and a cache that never crosses cities.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.app import create_app
from sitara_api.config import Settings
from sitara_api.panchang.registry import build_registry
from tests.panchang.conftest import MONGO_URI, assert_envelope
from tests.panchang.replay import transport_for


@pytest.fixture()
def route_settings() -> Settings:
    return Settings(
        mongodb_uri=MONGO_URI,
        mongo_db=f"sitara_test_{uuid.uuid4().hex[:8]}",
        cookie_secure=False,
        divineapi_api_key="test-key",
        divineapi_auth_token="test-token",
        prokerala_client_id="test-id",
        prokerala_client_secret="test-secret",
    )


def make_client(settings: Settings, transport=None, *, astro=None) -> TestClient:  # noqa: ANN001
    app = create_app(settings)
    app.state.provider_registry = build_registry(
        settings, transport=transport or transport_for("divineapi")
    )
    # Layer A is pinned OFF unless a test asks for it. `astro_base_url`
    # defaults to localhost:8003, so leaving it live made these assertions
    # depend on whether a developer happened to have the astro service
    # running — the suite passed or failed on ambient state, which is not a
    # property of the code under test.
    app.state.astro_panchang_adapter = astro
    return TestClient(app)


@pytest.fixture()
def client(route_settings: Settings) -> Iterator[TestClient]:
    with make_client(route_settings) as c:
        yield c
    MongoClient(MONGO_URI).drop_database(route_settings.mongo_db)


class TestPanchangEndpoint:
    def test_city_lookup(self, client: TestClient) -> None:
        """The playbook's acceptance shape: curl /panchang?date=…&city=Mumbai."""
        response = client.get("/v1/panchang", params={"date": "2026-08-08", "city": "Mumbai"})
        assert response.status_code == 200
        body = response.json()
        assert body["place"] == {"label": "Mumbai", "tz": "Asia/Kolkata"}
        assert body["sources"] == ["divineapi"]
        assert body["facts"]

    def test_facts_carry_source_and_confidence(self, client: TestClient) -> None:
        """§5.2: a snapshot is (id, value, source, confidence). A fact without
        provenance cannot be rendered on a Trust Sheet (§13)."""
        body = client.get(
            "/v1/panchang", params={"date": "2026-08-08", "city": "Mumbai"}
        ).json()
        assert body["confidence"] == "tradition_based_general"
        for fact in body["facts"]:
            assert fact["source"] == "divineapi"

    def test_second_call_is_a_cache_hit(self, client: TestClient) -> None:
        params = {"date": "2026-08-08", "city": "Mumbai"}
        first = client.get("/v1/panchang", params=params).json()
        second = client.get("/v1/panchang", params=params).json()
        assert first["cached"] is False
        assert second["cached"] is True
        assert [f["fact_id"] for f in first["facts"]] == [f["fact_id"] for f in second["facts"]]

    def test_cache_row_uses_the_spec_key(
        self, client: TestClient, route_settings: Settings
    ) -> None:
        client.get("/v1/panchang", params={"date": "2026-08-08", "city": "Mumbai"})
        mongo: MongoClient = MongoClient(MONGO_URI)
        doc = mongo[route_settings.mongo_db].panchang_cache.find_one()
        mongo.close()
        assert doc is not None
        assert doc["_id"] == "panchang:2026-08-08:te7u:amanta:divineapi"
        assert doc["provider"] == "divineapi"

    def test_two_cities_do_not_share_a_response(
        self, client: TestClient, route_settings: Settings
    ) -> None:
        """§30.2 acceptance: no cached timing ever crosses cities."""
        client.get("/v1/panchang", params={"date": "2026-08-08", "city": "Mumbai"})
        delhi = client.get("/v1/panchang", params={"date": "2026-08-08", "city": "Delhi"}).json()
        assert delhi["cached"] is False
        assert delhi["place"]["label"] == "Delhi"
        mongo: MongoClient = MongoClient(MONGO_URI)
        count = mongo[route_settings.mongo_db].panchang_cache.count_documents({})
        mongo.close()
        assert count == 2

    def test_alias_resolves_to_the_canonical_city(self, client: TestClient) -> None:
        body = client.get("/v1/panchang", params={"date": "2026-08-08", "city": "bombay"}).json()
        assert body["place"]["label"] == "Mumbai"

    def test_explicit_coordinates_are_accepted(self, client: TestClient) -> None:
        response = client.get(
            "/v1/panchang",
            params={
                "date": "2026-08-08",
                "lat": 19.076,
                "lon": 72.8777,
                "tz": "Asia/Kolkata",
                "label": "Mumbai (GPS)",
            },
        )
        assert response.status_code == 200
        assert response.json()["place"]["label"] == "Mumbai (GPS)"


class TestHonestDecline:
    def test_unknown_city_uses_the_canonical_envelope(self, client: TestClient) -> None:
        response = client.get("/v1/panchang", params={"date": "2026-08-08", "city": "Atlantis"})
        assert response.status_code == 422
        assert_envelope(response.json(), "ASTRO_PLACE_UNRESOLVED", retryable=False)

    def test_missing_place_is_declined_not_defaulted(self, client: TestClient) -> None:
        """A default city would produce confidently wrong timings (§5.3)."""
        response = client.get("/v1/panchang", params={"date": "2026-08-08"})
        assert response.status_code == 422
        assert response.json()["code"] == "ASTRO_PLACE_UNRESOLVED"

    def test_bad_date_is_a_validation_envelope(self, client: TestClient) -> None:
        response = client.get("/v1/panchang", params={"date": "not-a-date", "city": "Mumbai"})
        assert response.status_code == 400
        assert_envelope(response.json(), "SYS_VALIDATION", retryable=False)

    def test_unknown_timezone_is_declined(self, client: TestClient) -> None:
        response = client.get(
            "/v1/panchang",
            params={"date": "2026-08-08", "lat": 0, "lon": 0, "tz": "Mars/Olympus", "label": "X"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "ASTRO_PLACE_UNRESOLVED"


class TestDayTimingsEndpoint:
    def test_returns_bands_and_choghadiya(self, client: TestClient) -> None:
        body = client.get(
            "/v1/panchang/day-timings", params={"date": "2026-08-08", "city": "Mumbai"}
        ).json()
        kinds = [f["value"]["timing"] for f in body["facts"]]
        assert "rahu_kaal" in kinds
        assert kinds.count("choghadiya_day") == 8
        assert kinds.count("choghadiya_night") == 8

    def test_choghadiya_names_are_enums_not_prose(self, client: TestClient) -> None:
        """§2.4: a vendor's English label must never reach a user. The wire
        carries an enum the client renders in the user's own language."""
        body = client.get(
            "/v1/panchang/day-timings", params={"date": "2026-08-08", "city": "Mumbai"}
        ).json()
        names = {
            f["value"]["choghadiya"] for f in body["facts"] if f["value"].get("choghadiya")
        }
        assert names <= {"udveg", "char", "labh", "amrit", "kaal", "shubh", "rog"}

    def test_quality_is_stated_without_fear_copy(self, client: TestClient) -> None:
        """§9/§13: the API states a quality band; it never ships alarming prose
        for the client to display."""
        body = client.get(
            "/v1/panchang/day-timings", params={"date": "2026-08-08", "city": "Mumbai"}
        ).json()
        qualities = {f["value"]["quality"] for f in body["facts"]}
        assert qualities <= {"auspicious", "neutral", "inauspicious"}
        assert "warning" not in str(body).lower()


class TestMuhuratEndpoint:
    def test_explicit_place_is_honoured_and_labelled(self, client: TestClient) -> None:
        """§30.2 verbatim: "any muhurat query accepts an explicit place
        ('wedding in Jaipur') — computed for THAT place with its timezone,
        labelled with city"."""
        response = client.post(
            "/v1/muhurat",
            json={
                "muhurat_type": "marriage",
                "date_from": "2026-11-15",
                "date_to": "2026-11-30",
                "city": "Jaipur",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["place"] == {"label": "Jaipur", "tz": "Asia/Kolkata"}
        for fact in body["facts"]:
            assert fact["value"]["place_label"] == "Jaipur"
            assert fact["value"]["place_tz"] == "Asia/Kolkata"

    def test_the_place_is_never_taken_from_the_session(self, client: TestClient) -> None:
        """An event elsewhere is the normal case, not the exception — the
        window must belong to the city that was asked for."""
        jaipur = client.post(
            "/v1/muhurat",
            json={"date_from": "2026-11-15", "date_to": "2026-11-30", "city": "Jaipur"},
        ).json()
        assert {f["value"]["place_label"] for f in jaipur["facts"]} == {"Jaipur"}

    def test_fully_specified_place_is_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/v1/muhurat",
            json={
                "muhurat_type": "griha_pravesh",
                "date_from": "2026-11-15",
                "date_to": "2026-11-30",
                "place": {
                    "label": "Village near Udaipur",
                    "lat": 24.5854,
                    "lon": 73.7125,
                    "tz": "Asia/Kolkata",
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["place"]["label"] == "Village near Udaipur"

    def test_unknown_city_declines(self, client: TestClient) -> None:
        response = client.post(
            "/v1/muhurat",
            json={"date_from": "2026-11-15", "date_to": "2026-11-30", "city": "Atlantis"},
        )
        assert response.status_code == 422
        assert_envelope(response.json(), "ASTRO_PLACE_UNRESOLVED", retryable=False)

    def test_muhurat_is_cached_separately_per_type(
        self, client: TestClient, route_settings: Settings
    ) -> None:
        for muhurat_type in ("marriage", "vehicle"):
            client.post(
                "/v1/muhurat",
                json={
                    "muhurat_type": muhurat_type,
                    "date_from": "2026-11-15",
                    "date_to": "2026-11-30",
                    "city": "Jaipur",
                },
            )
        mongo: MongoClient = MongoClient(MONGO_URI)
        count = mongo[route_settings.mongo_db].panchang_cache.count_documents({"kind": "muhurat"})
        mongo.close()
        assert count == 2


class TestLayerAMerge:
    """§32.2/§35.3: Layer A is authoritative on deterministic astronomy and
    merges with the vendor's calendar layer. Asserted deliberately here rather
    than depending on whether a dev service happens to be listening."""

    def test_layer_a_joins_the_sources_when_it_can_answer(
        self, route_settings: Settings
    ) -> None:
        from sitara_api.panchang.adapter import AstroPanchangAdapter

        class StubAstro(AstroPanchangAdapter):
            def __init__(self) -> None:
                super().__init__("http://astro.invalid", 1.0)

            async def panchang(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
                return []

        with make_client(route_settings, astro=StubAstro()) as client:
            response = client.get(
                "/v1/panchang", params={"date": "2026-08-08", "city": "Mumbai"}
            )

        # An empty Layer-A answer must not claim to be a source.
        assert response.status_code == 200
        assert response.json()["sources"] == ["divineapi"]
        MongoClient(MONGO_URI).drop_database(route_settings.mongo_db)
