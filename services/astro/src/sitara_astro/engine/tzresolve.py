"""Historical timezone resolution — pure IANA tzdb via zoneinfo (SPEC §5.2).

No external astrology API is EVER trusted for timezone handling. DST gaps and
folds are resolved explicitly and the resolution is recorded so §5.4 confidence
can downgrade upstream.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, reset_tzpath

from sitara_schemas import ErrorCode

from sitara_astro.engine.inputs import GapPolicy
from sitara_astro.errors import AstroError

# §5.2 D8: data_revision pins tzdata==<ver> as a fact input, so that exact
# package MUST be what answers every lookup. With a non-empty TZPATH, zoneinfo
# would silently prefer the host OS tzdb (present on macOS, CI runners, and
# debian-slim alike) and the recorded provenance would be a lie. Emptying
# TZPATH forces every ZoneInfo load through the pinned tzdata wheel.
reset_tzpath(())


@dataclass(frozen=True)
class ResolvedInstant:
    tz: str
    utc: datetime
    utc_offset_seconds: int
    fold_used: int
    ambiguous: bool
    gap_shifted_minutes: int


def resolve_local(
    d: date,
    t: time,
    tz: str,
    fold: int | None = None,
    gap_policy: GapPolicy = "shift_forward",
) -> ResolvedInstant:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AstroError(ErrorCode.ASTRO_PLACE_UNRESOLVED) from exc

    naive = datetime.combine(d, t)
    dt0 = naive.replace(tzinfo=zone, fold=0)
    dt1 = naive.replace(tzinfo=zone, fold=1)
    off0, off1 = dt0.utcoffset(), dt1.utcoffset()
    assert off0 is not None and off1 is not None

    def round_trips(aware: datetime) -> bool:
        return aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive

    if not round_trips(dt0) and not round_trips(dt1):
        # Nonexistent wall time (spring-forward gap).
        if gap_policy == "error":
            raise AstroError(ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA)
        gap = off1 - off0
        shifted = (naive + gap).replace(tzinfo=zone, fold=1)
        return ResolvedInstant(
            tz=tz,
            utc=shifted.astimezone(UTC),
            utc_offset_seconds=int(off1.total_seconds()),
            fold_used=0,
            ambiguous=False,
            gap_shifted_minutes=int(gap.total_seconds() // 60),
        )

    ambiguous = off0 != off1
    fold_used = fold if fold is not None else 0
    chosen = dt1 if fold_used == 1 else dt0
    offset = chosen.utcoffset()
    assert offset is not None
    return ResolvedInstant(
        tz=tz,
        utc=chosen.astimezone(UTC),
        utc_offset_seconds=int(offset.total_seconds()),
        fold_used=fold_used,
        ambiguous=ambiguous,
        gap_shifted_minutes=0,
    )
