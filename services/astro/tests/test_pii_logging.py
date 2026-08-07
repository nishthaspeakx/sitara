"""§13 canary: names and birth data must never reach a log sink.

This is the structural guard. It drives every path that touches user data with
sentinel values, then asserts those sentinels appear NOWHERE in the captured
log stream — message, args, or formatted traceback. A future change that
interpolates a name into an exception fails here, not in production.
"""

import logging
from datetime import date

import pytest
from sitara_schemas import ErrorCode
from sitara_schemas.facts import NameSource

from sitara_astro.errors import AstroError
from sitara_astro.numerology.core import letter_breakdown, name_number, normalise_name
from sitara_astro.numerology.factbuild import ConfirmedName, numerology_facts
from sitara_astro.numerology.inputs import NumerologyOptions
from sitara_astro.numerology.translit import propose_transliteration
from sitara_astro.pii import PiiScrubbingFormatter, redact, scrub_text

# Distinctive enough that an accidental substring match is impossible.
SENTINEL_NAME = "Zzyzxqvw Bqhrtplm"
SENTINEL_NATIVE = "ज़्ज़िज़्क्व"
SENTINEL_DOB = date(1987, 3, 11)
SENTINELS = (SENTINEL_NAME, SENTINEL_NATIVE, "1987-03-11", "Zzyzxqvw", "Bqhrtplm")


def _assert_clean(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text, f"§13 leak: {sentinel!r} found in {text!r}"


class TestExceptionsCarryNoPii:
    @pytest.mark.parametrize(
        "bad_name",
        [
            f"{SENTINEL_NAME} 1985",  # digits
            f"{SENTINEL_NAME}@example",  # symbol
            SENTINEL_NATIVE,  # non-Latin
            "",
        ],
    )
    def test_normalise_name_never_echoes_the_name(self, bad_name: str) -> None:
        with pytest.raises(AstroError) as exc_info:
            normalise_name(bad_name)
        error = exc_info.value
        _assert_clean(str(error))
        _assert_clean(error.detail or "")
        _assert_clean(repr(error.args))

    def test_confirmed_name_rejection_carries_no_pii(self) -> None:
        with pytest.raises(AstroError) as exc_info:
            ConfirmedName(
                latin=SENTINEL_NATIVE, source=NameSource.USER_EDITED, original=SENTINEL_NATIVE
            )
        _assert_clean(str(exc_info.value))

    def test_unconfirmed_flow_error_carries_no_pii(self) -> None:
        with pytest.raises(AstroError) as exc_info:
            ConfirmedName.from_confirmation(SENTINEL_NATIVE, confirmed=False)
        _assert_clean(str(exc_info.value))


class TestNothingReachesTheLogStream:
    """The canary proper: exercise real call paths, capture ALL logging."""

    def _exercise(self) -> None:
        options = NumerologyOptions()
        # happy paths — these must not log user data either
        proposal = propose_transliteration(SENTINEL_NATIVE)
        name = ConfirmedName.from_confirmation(SENTINEL_NATIVE, confirmed=True)
        numerology_facts(SENTINEL_DOB, name, options, subject="s", chart_version=1)
        numerology_facts(SENTINEL_DOB, None, options, subject="s", chart_version=1)
        letter_breakdown(proposal.suggested_latin, list(options.systems)[0])
        # failure paths
        for bad in (f"{SENTINEL_NAME} 1985", "", SENTINEL_NATIVE):
            try:
                normalise_name(bad)
            except AstroError:
                pass
            try:
                ConfirmedName.from_confirmation(bad, confirmed=False)
            except AstroError:
                pass

    def test_no_sentinel_in_captured_records(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG):
            self._exercise()
        for record in caplog.records:
            _assert_clean(record.getMessage())
            _assert_clean(str(record.args))
        _assert_clean(caplog.text)

    def test_unhandled_error_traceback_is_scrubbed_at_the_sink(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Even if a future traceback carries a raw value, the formatter nets it."""
        logger = logging.getLogger("sitara_astro.test")
        try:
            raise RuntimeError(f"boom for {SENTINEL_NATIVE} born {SENTINEL_DOB.isoformat()}")
        except RuntimeError:
            logger.exception("unhandled")
        formatter = PiiScrubbingFormatter("%(message)s")
        for record in caplog.records:
            _assert_clean(formatter.format(record))


class TestRedaction:
    def test_redact_is_stable_and_non_reversible(self) -> None:
        token = redact(SENTINEL_NAME)
        assert token == redact(SENTINEL_NAME)  # correlatable across reports
        assert redact("other") != token
        _assert_clean(token)
        assert f"len={len(SENTINEL_NAME)}" in token

    def test_redact_handles_none_and_empty(self) -> None:
        assert "len=0" in redact(None)
        assert "len=0" in redact("")

    @pytest.mark.parametrize(
        "text",
        [
            f"born {SENTINEL_DOB.isoformat()}",
            f"name {SENTINEL_NATIVE}",
            f"{SENTINEL_NATIVE} on 1987-03-11",
        ],
    )
    def test_scrub_text_removes_dates_and_scripts(self, text: str) -> None:
        _assert_clean(scrub_text(text))

    def test_scrub_leaves_ordinary_log_vocabulary_intact(self) -> None:
        message = "computed 4 facts for subject s at chart_version=1"
        assert scrub_text(message) == message

    def test_scrub_redacts_iso_dates_anywhere(self) -> None:
        assert "1987-03-11" not in scrub_text("valid_from=1987-03-11T00:00:00Z")


class TestErrorCodeSeparation:
    """Finding 3: one code, one meaning (§34.4)."""

    def test_unconfirmed_is_only_for_the_confirmation_flow(self) -> None:
        with pytest.raises(AstroError) as exc_info:
            ConfirmedName.from_confirmation(SENTINEL_NATIVE, confirmed=False)
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_UNCONFIRMED

    @pytest.mark.parametrize("bad", ["123", "", "   ", "Priya@example.com"])
    def test_malformed_input_is_name_invalid(self, bad: str) -> None:
        with pytest.raises(AstroError) as exc_info:
            normalise_name(bad)
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_INVALID

    def test_the_two_codes_have_different_http_status(self) -> None:
        from sitara_schemas.errors import HTTP_STATUS

        assert HTTP_STATUS[ErrorCode.ASTRO_NAME_INVALID] == 400  # validation (§6.3)
        assert HTTP_STATUS[ErrorCode.ASTRO_NAME_UNCONFIRMED] == 422  # domain state

    def test_valid_name_still_computes(self) -> None:
        assert name_number("Lakshmi", list(NumerologyOptions().systems)[0],
                           NumerologyOptions().master_numbers)[1] == 19
