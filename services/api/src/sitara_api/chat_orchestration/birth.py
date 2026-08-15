"""What the pipeline is allowed to know about the subject (§5.3 step 2, §13).

Extracted from `chat_orchestration/router.py` in M9-P10b so the live call reaches
the SAME narrowing the typed and spoken paths reach. This is not tidying: the
bug this function was written to fix — every turn running with an all-False
`BirthProfile()`, so the chat could not answer a single chart question against a
real account — was invisible to every test, because every test passed a profile
in explicitly. It was found by the first live conversation. A call path that
built its own narrowing would be a second place for the same defect to reappear,
and it would be found the same way.

It takes an app STATE rather than a `Request` because a WebSocket route has no
request. Passing a websocket where a request was typed would have worked by
accident today and broken on the day either grew a body.
"""

from __future__ import annotations

import logging
from typing import Any

from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.chat_orchestration.types import BirthProfile

logger = logging.getLogger(__name__)


async def birth_profile_for(state: Any, user_id: str) -> BirthProfile:
    """Sufficiency, never values.

    §13's single door to birth details is the astrology facade, so this asks it
    rather than reading the collection, and it narrows to the four booleans and
    the zone §5.3 permits the orchestrator to see.

    A facade failure degrades to "we do not know" rather than raising. That is
    the honest direction — Tara asks for the birth date she cannot confirm she
    has, which is a worse answer but never a wrong one.
    """
    facade = getattr(state, "astrology", None)
    if facade is None:
        return BirthProfile()
    try:
        birth = await facade.birth_input(user_id)
    except Exception:
        logger.warning("birth profile unavailable; answering without a chart")
        return BirthProfile()
    if birth is None:
        return BirthProfile()

    place = bool(birth.place_name) and bool(birth.tz)
    return BirthProfile(
        has_date=True,
        has_exact_time=birth.has_exact_time,
        # §10-6's four accuracies collapse to two questions here: do we have a
        # usable instant, and failing that do we have a window? A row with no
        # time at all is the Moon-chart path (§5.3), not a window.
        has_time_window=not birth.has_exact_time,
        has_place=place,
        tz=birth.tz,
    )


async def place_label_for(state: Any, user_id: str, supplied: str | None = None) -> str | None:
    """The city a place-anchored answer is computed FOR (§30.2, §5.3 step 3).

    Same lesson as `birth_profile_for`, one field over: `place_label` arrived
    only in the request BODY, and no client sends one. So every live turn ran
    with `has_current_location: False`, §5.3's required-data check reported the
    current location missing, and the very first suggestion chip on S18 — "How
    is my day looking?" — was answered with "Timings change with where you are.
    Which city should I use?" against an account whose city was in `profiles`
    the whole time.

    Invisible to every test for exactly the reason the birth profile was: every
    test passes a `place_label` explicitly, so no test has ever exercised the
    path a real conversation takes.

    A caller-supplied label still WINS — §30.2 lets a user ask for a muhurat in
    Jaipur while sitting in Bengaluru, and that is a per-question override, not
    a profile change. This only fills the silence.

    §30.2's rule for what fills it: the STORED brief place. Never the timezone —
    "Asia/Kolkata" is not a city anybody chose — and never a guess.
    """
    if supplied:
        return supplied
    db = getattr(state, "db", None)
    if db is None:
        return None
    try:
        profile = await db.profiles.find_one({"user_id": to_object_id(user_id, field_name="profiles.user_id")})
    except Exception:
        logger.warning("profile unavailable; answering without a place")
        return None
    place = (profile or {}).get("brief_place") or {}
    label = place.get("label") or place.get("name")
    return label if isinstance(label, str) and label.strip() else None
