"""Fixture provenance and the no-live-network guarantee.

CI must never call a paid vendor: it is slow, flaky, costs money per request,
and would make the suite depend on someone else's uptime. The guarantee is
enforced, not documented.
"""

import json

import pytest

from tests.panchang.replay import FIXTURE_ROOT, NoFixture, all_fixtures, transport_for


class TestProvenance:
    def test_every_fixture_declares_its_provenance(self) -> None:
        """An undeclared fixture is one nobody can tell is real."""
        for provider, name, fixture in all_fixtures():
            recording = fixture.get("_recording")
            assert recording is not None, f"{provider}/{name} has no _recording block"
            assert recording["status"] in {"provisional", "recorded"}
            assert recording["request"]["path"].startswith("/")
            assert "status_code" in fixture

    def test_no_fixture_contains_a_credential(self) -> None:
        """§13 + the recorder's scrubbing contract. A leaked trial key in git
        is a real incident, so this runs over the raw file text rather than the
        parsed body — a secret hiding in an unexpected field still trips it."""
        banned = ("api_key", "client_secret", "authorization", "bearer ")
        for path in FIXTURE_ROOT.rglob("*.json"):
            text = path.read_text(encoding="utf-8").lower()
            for token in banned:
                assert token not in text, f"{path.name} may contain a credential ({token})"

    def test_recorded_access_tokens_are_scrubbed(self) -> None:
        for provider, name, fixture in all_fixtures():
            token = fixture.get("body", {}).get("access_token")
            if token is not None:
                assert token == "SCRUBBED", f"{provider}/{name} kept a live token"

    def test_all_fixtures_recorded_from_live_api(self) -> None:
        """Turns green once `python -m sitara_api.panchang.record --all` has run
        against the trial accounts.

        While it skips, the vendor request paths and field names in the adapters
        are ASSUMPTIONS from documentation — the contract tests prove our parse
        layer works, not that DivineAPI and Prokerala actually answer this way.
        Do not delete this test to make the suite look finished.
        """
        provisional = [
            f"{provider}/{name}"
            for provider, name, fixture in all_fixtures()
            if fixture["_recording"]["status"] != "recorded"
        ]
        if provisional:
            pytest.skip(
                "PROVIDER SHAPES UNVERIFIED — still provisional: "
                + ", ".join(sorted(provisional))
                + ". Record with trial keys (see fixtures/README.md)."
            )

    def test_fixture_bodies_are_valid_json_documents(self) -> None:
        for path in FIXTURE_ROOT.rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))


class TestReplayIsClosed:
    def test_an_unrecorded_path_raises_rather_than_dialling_out(self) -> None:
        """The transport has no fall-through: a call nobody recorded fails the
        test instead of quietly becoming a live request."""
        import httpx

        transport = transport_for("divineapi")
        request = httpx.Request("POST", "https://divineapi.test/some/new/endpoint")
        with pytest.raises(NoFixture):
            transport.handler(request)  # type: ignore[attr-defined]
