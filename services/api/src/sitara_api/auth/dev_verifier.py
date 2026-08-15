"""A dev-only phone sign-in, for local verification runs (§33.2, §22.12).

**This is a credential-issuing code path. Read the containment before the code.**

Why it exists
-------------

`apps/web` needs `NEXT_PUBLIC_FIREBASE_*` to talk to Firebase from the browser,
and a local checkout has none — so the sign-in screen fails before it can send
an OTP, and nobody can reach the app on their own machine to verify anything.
The alternative is a Firebase console round trip (web config + a test phone
number) for every developer, every machine. §6.3's adapter rule and
`firebase.py`'s own docstring ("behind an interface so the boundary is fakeable
in tests and swappable") anticipate exactly this seam.

The four things that contain it
--------------------------------

1. **It refuses to exist outside dev.** The constructor raises unless
   `environment == "dev"`. Same rule as `db.seed` (refuses a non-dev host) and
   the local CSFLE KMS provider — this codebase already has the pattern and
   this follows it rather than inventing a softer one.

2. **It is off by default** and needs `AUTH_DEV_BYPASS=true` set deliberately.
   There is no "if Firebase is unconfigured, fall back to this": an
   unconfigured production build must fail loudly at sign-in, which is the rule
   `auth-client.ts` already states for the browser half.

3. **It can only ever sign in as a SEEDED SYNTHETIC PERSONA.** The phone is
   matched against `db.seed`'s own generated numbers — imported, not copied, so
   the two cannot drift — and anything else is refused. It therefore cannot
   mint a session for a real person's phone number even on a dev machine
   pointed at a real database: those rows have no synthetic phone.

4. **It changes nothing downstream.** It returns the same `VerifiedIdentity`
   the real verifier returns, carrying the persona's `firebase_uid`, so
   §33.2's `auth_identities` mapping resolves to the existing seeded user and
   §22.4's age gate still runs on the E.164 country exactly as it would for a
   real sign-in. Nothing is skipped — only the Firebase round trip is replaced.

What it deliberately does NOT do
---------------------------------

It does not create users. A phone with no seeded persona behind it is refused
rather than onboarded, because a bypass that can create accounts is a bypass
that can create one in production the day somebody mis-sets an env var.
"""

from __future__ import annotations

import logging

from sitara_api.auth.firebase import InvalidFirebaseToken, VerifiedIdentity

logger = logging.getLogger(__name__)

#: The shape the browser sends. `auth-client.ts`'s fake adapter builds it, and
#: it is deliberately unlike a JWT: nothing that reaches the real verifier can
#: be mistaken for this, and nothing that reaches this can be mistaken for a
#: Firebase token.
TOKEN_PREFIX = "dev:"


class DevPhoneVerifier:
    """Accepts `dev:<E.164 phone>` for a seeded synthetic persona. Nothing else."""

    def __init__(self, *, environment: str) -> None:
        if environment != "dev":
            # Not a log line, not a degraded mode. The same refusal `db.seed`
            # makes, for the same reason: a convenience that can reach real
            # data is not a convenience.
            raise RuntimeError(
                "DevPhoneVerifier refuses to run outside environment=dev "
                f"(got {environment!r}). This issues sessions; there is no "
                "safe non-dev use of it."
            )
        self._environment = environment

    def verify(self, id_token: str) -> VerifiedIdentity:
        if not id_token.startswith(TOKEN_PREFIX):
            raise InvalidFirebaseToken()

        phone = id_token[len(TOKEN_PREFIX) :].strip()
        uid = _seeded_uid_for(phone)
        if uid is None:
            # §13: the phone is NOT logged. A refused sign-in attempt is the
            # one moment a contact detail is most likely to be someone's real
            # one, and a dev log is still a log.
            logger.warning("dev sign-in refused: phone is not a seeded synthetic persona")
            raise InvalidFirebaseToken()

        return VerifiedIdentity(uid=uid, provider="phone", phone=phone)


def _seeded_uid_for(phone: str) -> str | None:
    """The `firebase_uid` `db.seed` wrote for this synthetic phone, or None.

    Imported from the seeder rather than restated here. A second copy of the
    phone-numbering rule is a second thing to keep in step, and the failure it
    produces — a dev bypass that silently stops matching the seeded users after
    someone renumbers the personas — would look like a broken database.
    """
    from sitara_api.db.seed import PERSONAS, _phone, is_synthetic_contact

    if not is_synthetic_contact(phone):
        return None
    for index, persona in enumerate(PERSONAS, start=1):
        if _phone(index) == phone:
            return f"synthetic-{persona.handle}"
    return None


def seeded_phone_book() -> tuple[tuple[str, str], ...]:
    """`(phone, handle)` for every seeded persona — for the operator banner.

    A developer needs to know which number to type, and reading it off the
    seeder is better than a wiki page that goes stale.
    """
    from sitara_api.db.seed import PERSONAS, _phone

    return tuple((_phone(i), p.handle) for i, p in enumerate(PERSONAS, start=1))
