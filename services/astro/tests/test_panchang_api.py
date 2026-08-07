"""POST /v1/facts/panchang — the Layer-A panchang endpoint (§5.2, §30.2).

Two things matter beyond shape: the facts are GLOBAL (no user id can leak into
a key), and a place with no sunrise declines through the §34.4 envelope instead
of inventing a day.
"""

from fastapi.testclient import TestClient
from sitara_schemas.facts import FACT_ID_PATTERN, FactKind, FactSource

from sitara_astro.main import app

client = TestClient(app)

MUMBAI = {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "tz": "Asia/Kolkata"}
TROMSO = {"name": "Tromso", "lat": 69.6496, "lon": 18.9560, "tz": "Europe/Oslo"}


def post(place=MUMBAI, local_date="2026-08-07", **extra):
    body = {"local_date": local_date, "place": place, "tradition": "amanta", **extra}
    return client.post("/v1/facts/panchang", json=body)


class TestShape:
    def test_returns_the_full_fact_set(self) -> None:
        response = post()
        assert response.status_code == 200
        facts = response.json()["facts"]
        kinds = [f["kind"] for f in facts]
        assert kinds.count(FactKind.PANCHANG_SUNRISE_SUNSET.value) == 1
        assert kinds.count(FactKind.PANCHANG_TITHI_BOUNDARY.value) == 1
        assert kinds.count(FactKind.PANCHANG_NAKSHATRA_BOUNDARY.value) == 1
        # rahu + yamaganda + gulikai + abhijit + 8 day + 8 night choghadiya
        assert kinds.count(FactKind.PANCHANG_DAY_TIMING.value) == 20

    def test_day_timings_can_be_omitted(self) -> None:
        """The Layer-D job comparing only astronomy does not need 20 windows."""
        facts = post(include_day_timings=False).json()["facts"]
        assert len(facts) == 3

    def test_every_fact_id_matches_the_grammar(self) -> None:
        for fact in post().json()["facts"]:
            assert FACT_ID_PATTERN.match(fact["fact_id"]), fact["fact_id"]

    def test_fact_ids_are_unique(self) -> None:
        """Sixteen choghadiya parts share a kind — each still needs its own ID
        or artefacts citing them would collide (§34.2)."""
        ids = [f["fact_id"] for f in post().json()["facts"]]
        assert len(ids) == len(set(ids))

    def test_facts_declare_layer_a_provenance(self) -> None:
        for fact in post().json()["facts"]:
            assert fact["source"] == FactSource.LAYER_A.value
            assert fact["method"]["rise_set"] == "upper_limb_refracted"
            assert fact["method"]["tradition"] == "amanta"


class TestGlobalNotPerUser:
    def test_subject_is_geohash_and_tradition(self) -> None:
        """§34.2/§7.2: panchang is shared across users, so the subject encodes
        PLACE and TRADITION — never an identity."""
        subjects = {f["fact_id"].split("/")[2].split("@")[0] for f in post().json()["facts"]}
        assert subjects == {"te7u-amanta"}

    def test_two_users_in_one_city_get_identical_facts(self) -> None:
        first = post().json()["facts"]
        second = post().json()["facts"]
        assert [f["fact_id"] for f in first] == [f["fact_id"] for f in second]

    def test_a_user_id_cannot_be_smuggled_in(self) -> None:
        """The request model has no subject field; an extra one is ignored, not
        honoured, so no caller can shard the global cache per user."""
        facts = post(subject="user123").json()["facts"]
        assert all("user123" not in f["fact_id"] for f in facts)

    def test_different_traditions_do_not_share_a_key(self) -> None:
        amanta = post().json()["facts"][0]["fact_id"]
        purnimanta = post(tradition="purnimanta").json()["facts"][0]["fact_id"]
        assert amanta != purnimanta

    def test_different_cities_do_not_share_a_key(self) -> None:
        """§30.2 acceptance: no cached timing ever crosses cities."""
        delhi = {"name": "Delhi", "lat": 28.6139, "lon": 77.2090, "tz": "Asia/Kolkata"}
        mumbai_id = post().json()["facts"][0]["fact_id"]
        delhi_id = post(place=delhi).json()["facts"][0]["fact_id"]
        assert mumbai_id != delhi_id


class TestHonestDecline:
    def test_polar_midnight_sun_returns_the_canonical_envelope(self) -> None:
        """§5.3: no sunrise means no fact — never a fabricated window."""
        response = post(place=TROMSO, local_date="2026-06-21")
        assert response.status_code == 422
        body = response.json()
        assert set(body) == {"code", "message_key", "trace_id", "retryable"}
        assert body["code"] == "ASTRO_INSUFFICIENT_BIRTH_DATA"
        assert body["retryable"] is False

    def test_unknown_timezone_is_rejected(self) -> None:
        bad = {**MUMBAI, "tz": "Mars/Olympus"}
        response = post(place=bad)
        assert response.status_code == 422
        assert response.json()["code"] == "ASTRO_PLACE_UNRESOLVED"

    def test_malformed_request_uses_the_envelope_too(self) -> None:
        response = client.post("/v1/facts/panchang", json={"local_date": "not-a-date"})
        assert response.status_code == 400
        assert response.json()["code"] == "SYS_VALIDATION"


class TestOrderingContract:
    def test_windows_are_internally_consistent(self) -> None:
        for fact in post().json()["facts"]:
            if fact["valid_to"] is not None:
                assert fact["valid_from"] <= fact["valid_to"]

    def test_tithi_and_nakshatra_are_named_at_sunrise(self) -> None:
        """The panchang day runs from sunrise, so the tithi named for a date is
        the one running at sunrise — not the one at local midnight."""
        facts = {f["kind"]: f for f in post().json()["facts"]}
        sunrise = facts[FactKind.PANCHANG_SUNRISE_SUNSET.value]["value"]["sunrise_utc"]
        for kind in (FactKind.PANCHANG_TITHI_BOUNDARY, FactKind.PANCHANG_NAKSHATRA_BOUNDARY):
            value = facts[kind.value]["value"]
            assert value["starts_utc"] <= sunrise <= value["ends_utc"]
