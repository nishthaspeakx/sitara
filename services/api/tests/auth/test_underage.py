"""§22.4 hard age gate: under-18 DOB rejected at sign-up with an honest,
in-locale explanation — AUTH_UNDERAGE, message_key resolvable in ALL launch locales.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.config import Settings

from .conftest import FakeVerifier, assert_envelope, exchange, years_ago

CATALOGS = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "messages"


def test_underage_dob_rejected(
    client: TestClient, verifier: FakeVerifier, mongo: MongoClient, settings: Settings
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    resp = exchange(client, "tok-1", dob=years_ago(18, plus_days=1))  # 18 tomorrow

    assert resp.status_code == 422
    assert_envelope(resp.json(), "AUTH_UNDERAGE", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.underage"
    assert "set-cookie" not in resp.headers

    # No account is created for a rejected sign-up.
    db = mongo[settings.mongo_db]
    assert db.users.count_documents({}) == 0
    assert db.auth_identities.count_documents({}) == 0


def test_exactly_eighteen_today_is_allowed(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    resp = exchange(client, "tok-1", dob=years_ago(18))
    assert resp.status_code == 200


def test_underage_message_key_exists_in_all_three_locales() -> None:
    """§2.4 whole-app native language — the rejection must be translatable
    everywhere, no silent English fallback."""
    for locale in ("en", "hi-Latn", "hi"):
        catalog = json.loads((CATALOGS / f"{locale}.json").read_text())
        node = catalog
        for part in "errors.auth.underage".split("."):
            assert part in node, f"{locale} catalog missing errors.auth.underage"
            node = node[part]
        assert isinstance(node, str) and node.strip()


class TestMidnightBoundary:
    """§36.4 — the §22.4 gate runs on the user's LOCAL calendar date.

    §5.5 makes midnight-boundary suites a 100% release gate, and this is the
    boundary that matters most: refusing an adult an account is a legal act,
    and the same date of birth is 17 or 18 depending on the zone the check
    ran in. Both directions are covered — a zone AHEAD of UTC and one BEHIND.
    """

    def test_local_today_uses_the_zone_it_is_given(self) -> None:
        from sitara_api.auth.service import local_today

        ahead, zone_ahead = local_today("Asia/Kolkata")
        behind, zone_behind = local_today("America/Los_Angeles")

        assert zone_ahead == "Asia/Kolkata"
        assert zone_behind == "America/Los_Angeles"
        # Never more than a day apart, and Kolkata is never behind LA.
        assert (ahead - behind).days in (0, 1)

    def test_an_unknown_zone_falls_back_to_the_launch_market_not_utc(self) -> None:
        """UTC is the one choice guaranteed to be wrong for every user we
        currently have."""
        from sitara_api.auth.service import DEFAULT_AGE_TIMEZONE, local_today

        _, zone = local_today("Mars/Olympus")
        assert zone == DEFAULT_AGE_TIMEZONE

        _, zone_none = local_today(None)
        assert zone_none == DEFAULT_AGE_TIMEZONE

    @pytest.mark.parametrize(
        ("zone", "utc_instant", "expected_local"),
        [
            # 19:00 UTC is already tomorrow in Kolkata (+5:30).
            ("Asia/Kolkata", "2026-08-08T19:00:00+00:00", date(2026, 8, 9)),
            # 02:00 UTC is still yesterday in Los Angeles (-7).
            ("America/Los_Angeles", "2026-08-09T02:00:00+00:00", date(2026, 8, 8)),
        ],
    )
    def test_the_local_date_is_the_users_date_in_both_directions(
        self, monkeypatch, zone: str, utc_instant: str, expected_local: date
    ) -> None:  # noqa: ANN001
        from datetime import datetime

        from sitara_api.auth import service

        monkeypatch.setattr(service, "_now", lambda: datetime.fromisoformat(utc_instant))
        today, used = service.local_today(zone)

        assert today == expected_local
        assert used == zone

    @pytest.mark.parametrize(
        ("zone", "utc_instant"),
        [
            ("Asia/Kolkata", "2026-08-08T19:00:00+00:00"),
            ("America/Los_Angeles", "2026-08-09T02:00:00+00:00"),
        ],
    )
    def test_someone_exactly_eighteen_locally_is_admitted(
        self, monkeypatch, zone: str, utc_instant: str
    ) -> None:  # noqa: ANN001
        """The bug this fixes: on their 18th birthday, in their own timezone,
        the UTC date disagrees for several hours a day and refused them."""
        from datetime import datetime

        from sitara_api.auth import service

        monkeypatch.setattr(service, "_now", lambda: datetime.fromisoformat(utc_instant))
        today_local, _ = service.local_today(zone)
        dob = today_local.replace(year=today_local.year - 18)

        assert service._age_years(dob, today_local) == 18  # noqa: SLF001
        # …and one day short is still refused. The gate did not move.
        assert service._age_years(dob.replace(day=dob.day + 1), today_local) == 17  # noqa: SLF001


@pytest.mark.asyncio
async def test_the_age_check_is_audited_with_its_timezone(
    client: TestClient, verifier: FakeVerifier, settings, mongo
) -> None:  # noqa: ANN001
    """§12/§36.4: "why was this refused?" is unanswerable without the zone."""
    verifier.add("tok-tz", uid="fb-uid-tz", provider="phone", phone="+911234500009")
    exchange(client, "tok-tz", dob=years_ago(30), timezone="America/Los_Angeles")

    row = mongo[settings.mongo_db].audit_logs.find_one({"action": "auth.age_gate"})
    assert row is not None
    assert row["timezone"] == "America/Los_Angeles"
    assert row["local_date"]
    assert row["actor"] == "firebase:fb-uid-tz"
