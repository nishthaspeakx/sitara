"""The dev sign-in bypass, and the four things that contain it.

This is a credential-issuing path added for local verification runs, so the
tests that matter are the REFUSALS. A bypass whose containment is untested is
a backdoor with a comment on it.
"""

from __future__ import annotations

import pytest

from sitara_api.auth.dev_verifier import DevPhoneVerifier, seeded_phone_book
from sitara_api.auth.firebase import InvalidFirebaseToken
from sitara_api.config import Settings


def _verifier() -> DevPhoneVerifier:
    return DevPhoneVerifier(environment="dev")


# ---------------------------------------------------------------------------
# containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["test", "staging", "production", "prod", ""])
def test_it_refuses_to_exist_outside_dev(environment: str) -> None:
    """Not a log line, not a degraded mode — a raise, at construction.

    Same refusal `db.seed` makes for a non-dev host and the local CSFLE KMS
    makes outside dev/test. A convenience that can reach real data is not a
    convenience, and the failure has to happen before anything can call it.
    """
    with pytest.raises(RuntimeError, match="refuses to run outside environment=dev"):
        DevPhoneVerifier(environment=environment)


def test_it_is_off_by_default() -> None:
    """There is no "Firebase looks unconfigured, so fall back to this".

    A production build with a missing key must fail loudly at sign-in rather
    than quietly accepting everybody — the rule `auth-client.ts` already states
    for the browser half, asserted here for the server half.
    """
    assert Settings().auth_dev_bypass is False


def test_it_can_only_sign_in_as_a_seeded_synthetic_persona() -> None:
    """The containment that survives a mis-set env var on a real database.

    A dev machine pointed at real data has no synthetic phone rows, so this
    refuses everything there. The numbers it does accept are §22.12's reserved
    unroutable range, which belongs to nobody.
    """
    verifier = _verifier()
    for phone, handle in seeded_phone_book():
        identity = verifier.verify(f"dev:{phone}")
        assert identity.uid == f"synthetic-{handle}"
        assert identity.provider == "phone"
        assert identity.phone == phone


@pytest.mark.parametrize(
    "phone",
    [
        "+918130225222",  # a real-looking Indian mobile
        "+14155550100",
        "+919999900099",  # right prefix, no such persona
        "",
        "not-a-phone",
    ],
)
def test_it_refuses_any_phone_without_a_seeded_persona(phone: str) -> None:
    """It does not CREATE users. A bypass that can onboard is a bypass that can
    onboard in production the day somebody mis-sets an env var."""
    with pytest.raises(InvalidFirebaseToken):
        _verifier().verify(f"dev:{phone}")


@pytest.mark.parametrize(
    "token",
    [
        "eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMyJ9.eyJzdWIiOiJ4In0.sig",  # a real-shaped JWT
        "fake-id-token",  # what the fake adapter used to send
        "+919999900003",  # the phone with no prefix
        "",
    ],
)
def test_a_token_that_is_not_ours_is_refused(token: str) -> None:
    """The `dev:` prefix is deliberately unlike a JWT in both directions:
    nothing reaching the real Firebase verifier can be mistaken for this, and
    nothing reaching this can be mistaken for a Firebase token."""
    with pytest.raises(InvalidFirebaseToken):
        _verifier().verify(token)


# ---------------------------------------------------------------------------
# it stays in step with the seeder
# ---------------------------------------------------------------------------


def test_the_phone_mapping_is_sourced_from_the_seeder_not_restated() -> None:
    """A second copy of the numbering rule is a second thing to keep in step,
    and the failure it produces — a bypass that silently stops matching after
    someone renumbers the personas — looks like a broken database."""
    from sitara_api.db.seed import PERSONAS, _phone

    book = seeded_phone_book()
    assert len(book) == len(PERSONAS)
    assert book[0] == (_phone(1), PERSONAS[0].handle)


def test_it_returns_the_same_shape_the_real_verifier_returns() -> None:
    """Nothing downstream is skipped or special-cased.

    §33.2's `auth_identities` mapping resolves the uid to the seeded user, and
    §22.4's age gate still runs on the E.164 country — the bypass replaces the
    Firebase round trip and nothing else.
    """
    from sitara_api.auth.firebase import VerifiedIdentity

    identity = _verifier().verify(f"dev:{seeded_phone_book()[0][0]}")
    assert isinstance(identity, VerifiedIdentity)
    assert identity.phone is not None and identity.phone.startswith("+91")
    assert identity.email is None and identity.display_name is None


def test_the_app_refuses_to_boot_with_the_bypass_on_outside_dev() -> None:
    """The end-to-end containment: setting the flag in the wrong environment
    fails at BOOT, loudly, before a single session can be issued."""
    from sitara_api.app import create_app

    with pytest.raises(RuntimeError, match="refuses to run outside environment=dev"):
        create_app(Settings(auth_dev_bypass=True, environment="production"))
