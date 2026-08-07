"""The fixture recorder's safety rails.

The recorder is the one component allowed to touch a live vendor, so its guards
matter more than its happy path: it must refuse to run without an explicit
opt-in, and it must never write a credential to disk.
"""

from sitara_api.panchang.record import scrub


class TestRefusesWithoutOptIn:
    def test_refuses_without_the_env_flag(self, monkeypatch, capsys) -> None:  # noqa: ANN001
        """CI never sets SITARA_RECORD_FIXTURES, so CI can never record."""
        from sitara_api.panchang import record

        monkeypatch.delenv("SITARA_RECORD_FIXTURES", raising=False)
        monkeypatch.setattr(
            record, "Settings", lambda: _settings(record_fixtures=False, key="k")
        )
        assert record.main(["--all"]) == 2
        assert "SITARA_RECORD_FIXTURES=1" in capsys.readouterr().out

    def test_refuses_without_credentials(self, monkeypatch, capsys) -> None:  # noqa: ANN001
        from sitara_api.panchang import record

        monkeypatch.setattr(
            record, "Settings", lambda: _settings(record_fixtures=True, key=None)
        )
        assert record.main(["--all"]) == 2
        assert "no credentials" in capsys.readouterr().out


def _settings(*, record_fixtures: bool, key: str | None):  # noqa: ANN202
    from sitara_api.config import Settings

    return Settings(
        sitara_record_fixtures=record_fixtures,
        divineapi_api_key=key,
        divineapi_auth_token=key,
        prokerala_client_id=key,
        prokerala_client_secret=key,
    )


class TestScrubbing:
    def test_removes_credentials_by_key_name(self) -> None:
        cleaned = scrub(
            {
                "api_key": "live-key-123",
                "access_token": "abc.def",
                "data": {"client_secret": "shhh", "sunrise": "06:17"},
            }
        )
        assert cleaned["api_key"] == "SCRUBBED"
        assert cleaned["access_token"] == "SCRUBBED"
        assert cleaned["data"]["client_secret"] == "SCRUBBED"
        assert cleaned["data"]["sunrise"] == "06:17"  # real data survives

    def test_removes_bearer_tokens_hiding_in_string_values(self) -> None:
        """Belt and braces: a token in an unexpected field is still a leak."""
        cleaned = scrub({"echo": "Authorization: Bearer sk-live-abcdef"})
        assert "sk-live-abcdef" not in cleaned["echo"]
        assert "Bearer SCRUBBED" in cleaned["echo"]

    def test_scrubs_inside_lists(self) -> None:
        cleaned = scrub([{"token": "x"}, {"tithi": 10}])
        assert cleaned[0]["token"] == "SCRUBBED"
        assert cleaned[1]["tithi"] == 10

    def test_leaves_ordinary_payloads_untouched(self) -> None:
        payload = {"data": {"tithi": {"number": 10, "start": "2026-08-07 21:04:00"}}}
        assert scrub(payload) == payload
