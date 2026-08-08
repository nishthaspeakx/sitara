"""Shared vendor-payload parsing helpers.

Vendors report wall-clock times in the queried place's local zone, usually
without an offset. Converting those to UTC is OUR job using the IANA tzdb — no
astrology vendor is trusted for timezone handling (§5.2), which is precisely
why a naive string here would be a §5.3 wrong-timezone bug.
"""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

_LOCAL_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
)


class ShapeError(ValueError):
    """The payload did not contain what we needed, in a form we understood."""


def pick(payload: Any, *paths: str) -> Any:
    """First present value among dotted paths, e.g. "data.tithi.start".

    Vendors move fields between releases and nest inconsistently; naming the
    candidates explicitly beats a recursive search that might grab the wrong
    "start" from somewhere else in the document.
    """
    for path in paths:
        cursor: Any = payload
        for part in path.split("."):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            elif isinstance(cursor, list) and part.isdigit() and int(part) < len(cursor):
                cursor = cursor[int(part)]
            else:
                cursor = None
                break
        if cursor is not None:
            return cursor
    return None


def require(payload: Any, *paths: str) -> Any:
    value = pick(payload, *paths)
    if value is None:
        raise ShapeError(f"missing any of {paths}")
    return value


def to_utc(value: Any, tz: str) -> dt.datetime:
    """Vendor timestamp → aware UTC datetime.

    An offset-bearing string is trusted as given; a bare wall-clock string is
    localised through the place's IANA zone. Anything else is a shape error —
    we never guess at a timestamp that drives a user's timing.
    """
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = _parse_string(value.strip())
    else:
        raise ShapeError(f"not a timestamp: {value!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(tz))
    return parsed.astimezone(dt.UTC)


def _parse_string(raw: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in _LOCAL_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ShapeError(f"unparseable timestamp: {raw!r}")


def to_index(value: Any) -> int:
    """Vendors give an index as a number or a numeric string."""
    if isinstance(value, bool):
        raise ShapeError(f"not an index: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ShapeError(f"not an index: {value!r}")
