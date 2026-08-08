"""Corroborated timezone resolution for the §22.4 age gate (§37.2).

The gate is a birthday, and a birthday is a local-calendar fact — so it cannot
run in UTC (§37.2). But it must not run in a calendar the *caller* chooses
either: the world spans ~25 hours of local date, so an unverified
`timezone` field lets a seventeen-year-old claim `Pacific/Kiritimati` and be
admitted a day early. A legal gate cannot take its own criterion from the
party it is gating.

So the zone is CORROBORATED, and the check is pessimistic:

1. Derive a plausible zone set from evidence we did not get from the form —
   the E.164 country of the Firebase-verified phone number, intersected with
   the request-IP country when a geo lookup is available.
2. The client's declared zone is honoured ONLY if it is a member of that set,
   in which case it narrows the set to itself.
3. Age is evaluated in the WESTERNMOST member — the smallest local date, and
   therefore the smallest age the evidence permits.
4. If no set can be derived, the request is REFUSED as retryable. Never a
   guess, never a fall back to client input, never UTC.

Step 4 has teeth: a sign-up with no phone number and no IP country cannot be
age-checked and does not proceed. That is the intended failure direction for a
hard gate, and it is visible rather than silent — see the
`auth.zone_corroboration_coverage` release gate.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DATA = Path(__file__).parent / "phone_country_zones.json"

#: Bumped whenever the resolution rule or its data changes. Recorded on every
#: audit row so a decision can be replayed against the policy that made it.
ZONE_POLICY_VERSION = "zone-policy-1"


class Corroboration(StrEnum):
    """What evidence produced the zone set. Recorded on the audit row."""

    PHONE_COUNTRY = "phone_country"
    IP_COUNTRY = "ip_country"
    CLIENT_DECLARED = "client_declared"


class ZoneUndeterminable(Exception):
    """No corroborated zone set — the age gate cannot run (fail closed)."""


@dataclass(frozen=True)
class ZoneDecision:
    """The zone set and the single zone the gate actually used."""

    zones: tuple[str, ...]
    evaluated_in: str
    sources: tuple[Corroboration, ...]
    country: str | None

    def as_audit(self) -> dict[str, object]:
        """§13-safe: zones and provenance, nothing derived from a birth date."""
        return {
            "zones": list(self.zones),
            "evaluated_in": self.evaluated_in,
            "sources": [source.value for source in self.sources],
            "country": self.country,
            "policy": ZONE_POLICY_VERSION,
        }


@lru_cache(maxsize=1)
def _table() -> dict[str, dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["calling_codes"]


def country_for_phone(phone: str | None) -> tuple[str, tuple[str, ...]] | None:
    """(ISO country, zones) for an E.164 number, by longest calling-code match.

    Returns None for an unknown code rather than a guess — an unmapped country
    is a coverage gap to be closed with data, not papered over at runtime.
    """
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None
    table = _table()
    for length in (4, 3, 2, 1):
        entry = table.get(digits[:length])
        if entry:
            return entry["country"], tuple(entry["zones"])
    return None


def zones_for_country(iso_country: str | None) -> tuple[str, ...]:
    if not iso_country:
        return ()
    for entry in _table().values():
        if entry["country"] == iso_country.upper():
            return tuple(entry["zones"])
    return ()


def westernmost(zones: tuple[str, ...], now: dt.datetime) -> str:
    """The zone with the smallest UTC offset — the least advanced local date.

    Least favourable to the applicant by construction: whatever the true zone
    is, their local date is no earlier than this one, so an age of 18 here is
    18 everywhere the evidence allows.
    """
    def offset(name: str) -> dt.timedelta:
        delta = now.astimezone(ZoneInfo(name)).utcoffset()
        return delta if delta is not None else dt.timedelta(0)

    return min(sorted(zones), key=offset)


def resolve(
    *,
    phone: str | None,
    ip_country: str | None = None,
    declared: str | None = None,
    now: dt.datetime,
) -> ZoneDecision:
    """The corroborated zone set, and the zone the gate will use."""
    sources: list[Corroboration] = []
    candidate: tuple[str, ...] = ()
    country: str | None = None

    from_phone = country_for_phone(phone)
    if from_phone is not None:
        country, candidate = from_phone
        sources.append(Corroboration.PHONE_COUNTRY)

    from_ip = zones_for_country(ip_country)
    if from_ip:
        sources.append(Corroboration.IP_COUNTRY)
        # Intersect when both exist; a disagreement narrows rather than widens,
        # and an empty intersection means the evidence conflicts — refuse.
        candidate = tuple(sorted(set(candidate) & set(from_ip))) if candidate else from_ip
        country = country or (ip_country or "").upper() or None

    if not candidate:
        raise ZoneUndeterminable(
            "no corroborated timezone: the phone number has no mapped country "
            "and no IP country was supplied"
        )

    if declared and declared in candidate:
        # Honoured only because the evidence already contained it.
        candidate = (declared,)
        sources.append(Corroboration.CLIENT_DECLARED)
    elif declared:
        logger.info("declared timezone is outside the corroborated set — ignored")

    return ZoneDecision(
        zones=tuple(sorted(candidate)),
        evaluated_in=westernmost(candidate, now),
        sources=tuple(sources),
        country=country,
    )


def is_known_zone(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
