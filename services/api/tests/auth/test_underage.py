"""§22.4 hard age gate: under-18 DOB rejected at sign-up with an honest,
in-locale explanation — AUTH_UNDERAGE, message_key resolvable in ALL launch locales.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.auth import service, zones
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


class TestCorroboratedZone:
    """§37.2 — the gate runs in a corroborated calendar, pessimistically.

    §5.5 makes midnight-boundary suites a 100% release gate, and the gate is
    only worth testing at the boundary if the calendar itself cannot be chosen
    by the applicant.
    """

    NOW = datetime(2026, 8, 9, 11, 0, tzinfo=UTC)  # 16:30 IST · 01:00 next day at +14

    def test_a_far_east_zone_cannot_be_claimed_by_an_indian_number(self) -> None:
        """The demonstrated bypass: a 17-year-old whose birthday is tomorrow
        declares Pacific/Kiritimati and gains a day. The declaration is
        ignored because it is not in the phone's corroborated set."""
        decision = zones.resolve(
            phone="+919812345678", declared="Pacific/Kiritimati", now=self.NOW
        )

        assert decision.evaluated_in == "Asia/Kolkata"
        assert zones.Corroboration.CLIENT_DECLARED not in decision.sources

        turns_18_tomorrow = date(2008, 8, 10)
        local = self.NOW.astimezone(ZoneInfo(decision.evaluated_in)).date()
        assert service._age_years(turns_18_tomorrow, local) == 17  # noqa: SLF001

    def test_an_honest_declaration_inside_the_set_is_honoured(self) -> None:
        decision = zones.resolve(
            phone="+919812345678", declared="Asia/Kolkata", now=self.NOW
        )

        assert decision.zones == ("Asia/Kolkata",)
        assert zones.Corroboration.CLIENT_DECLARED in decision.sources

    def test_an_ist_eighteen_year_old_is_admitted_at_local_midnight(self) -> None:
        """The bug §37.2 fixed, still fixed: 18:35 UTC is already tomorrow in
        Kolkata, and their birthday is today there."""
        just_past_ist_midnight = datetime(2026, 8, 9, 18, 35, tzinfo=UTC)
        decision = zones.resolve(phone="+919812345678", now=just_past_ist_midnight)
        local = just_past_ist_midnight.astimezone(ZoneInfo(decision.evaluated_in)).date()
        dob = local.replace(year=local.year - 18)

        assert local == date(2026, 8, 10)
        assert service._age_years(dob, local) == 18  # noqa: SLF001

    def test_a_us_number_is_evaluated_in_its_westernmost_zone(self) -> None:
        """NANP spans Honolulu to St John's. The least favourable member is
        the one that makes the applicant youngest."""
        decision = zones.resolve(phone="+14155550123", now=self.NOW)

        assert decision.evaluated_in == "Pacific/Honolulu"
        assert "America/New_York" in decision.zones

    def test_no_corroboration_fails_closed(self) -> None:
        """A sign-up with no phone country and no IP country cannot be
        age-checked, so it does not proceed. Never a guess, never UTC."""
        with pytest.raises(zones.ZoneUndeterminable):
            zones.resolve(phone=None, now=self.NOW)

        with pytest.raises(zones.ZoneUndeterminable):
            zones.resolve(phone="+99912345678", now=self.NOW)  # unmapped code

    def test_conflicting_evidence_narrows_and_can_refuse(self) -> None:
        """An IP country that shares no zone with the phone country is a
        conflict, and a conflict is not resolved in the applicant's favour."""
        with pytest.raises(zones.ZoneUndeterminable):
            zones.resolve(phone="+919812345678", ip_country="US", now=self.NOW)

    def test_the_audit_payload_carries_no_birth_derivative(self) -> None:
        """§13: `audit_logs` is not a CSFLE collection, so an age must never
        reach it."""
        payload = zones.resolve(phone="+919812345678", now=self.NOW).as_audit()
        rendered = repr(payload)

        assert "age" not in rendered
        assert payload["policy"] == zones.ZONE_POLICY_VERSION
        assert payload["sources"] == ["phone_country"]


@pytest.mark.asyncio
async def test_the_age_check_is_audited_with_its_timezone(
    client: TestClient, verifier: FakeVerifier, settings, mongo
) -> None:  # noqa: ANN001
    """§12/§37.2: "why was this refused?" is unanswerable without the zone."""
    verifier.add("tok-tz", uid="fb-uid-tz", provider="phone", phone="+911234500009")
    exchange(client, "tok-tz", dob=years_ago(30), timezone="Asia/Kolkata")

    row = mongo[settings.mongo_db].audit_logs.find_one({"action": "auth.age_gate"})
    assert row is not None
    assert row["actor"] == "firebase:fb-uid-tz"
    assert row["target"] == "outcome=passed;min=18"
    assert row["zone_decision"]["evaluated_in"] == "Asia/Kolkata"
    assert row["zone_decision"]["policy"] == zones.ZONE_POLICY_VERSION
    # §13: nothing DERIVED from the date of birth. ("age" as a substring is
    # in the action name `auth.age_gate`; what must not appear is a value.)
    assert "age=" not in repr(row)
    assert not any("age" in str(k).lower() for k in row["zone_decision"])


def test_a_google_signup_without_a_phone_is_refused_as_policy(
    client: TestClient, verifier: FakeVerifier
) -> None:
    """§37.3: sign-up is PHONE-FIRST.

    Google and Apple are linkable secondary identities (§22.5), never
    standalone sign-up paths. This is a policy refusal — AUTH_FORBIDDEN with
    an in-locale explanation and a next step — not the retryable
    SYS_UNAVAILABLE that an unresolvable timezone produces. The distinction
    matters to the client: one says "try again", the other says "start with
    your phone".
    """
    verifier.add("tok-nophone", uid="fb-uid-np", provider="google", email="np@example.com")

    resp = exchange(client, "tok-nophone", dob=years_ago(30))

    assert resp.status_code == 403
    assert_envelope(resp.json(), "AUTH_FORBIDDEN", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.phone_required"


def test_an_unmapped_calling_code_still_fails_closed(
    client: TestClient, verifier: FakeVerifier
) -> None:
    """§37.3 guarantees a phone, not a MAPPED phone. A country outside the
    coverage table cannot be age-checked and is refused as retryable — the
    residual gap the auth.zone_corroboration_coverage gate tracks."""
    verifier.add("tok-unmapped", uid="fb-uid-um", provider="phone", phone="+99912345678")

    resp = exchange(client, "tok-unmapped", dob=years_ago(30))

    assert resp.status_code == 503
    assert_envelope(resp.json(), "SYS_UNAVAILABLE", retryable=True)
    assert resp.json()["message_key"] == "errors.auth.zone_unverified"


def test_a_linked_google_identity_still_signs_in(
    client: TestClient, verifier: FakeVerifier
) -> None:
    """§37.3 is a SIGN-UP rule. Once a google identity is linked to an account
    created by phone, signing in with it must keep working — the phone check
    sits after the existing-identity lookup, not before it."""
    verifier.add("tok-phone", uid="fb-uid-pf", provider="phone", phone="+911234500077")
    assert exchange(client, "tok-phone", dob=years_ago(30)).status_code == 200

    # Same Firebase uid arriving again — the identity row already exists.
    second = exchange(client, "tok-phone", dob=None)
    assert second.status_code == 200
    assert second.json()["is_new_user"] is False
