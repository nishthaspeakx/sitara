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
