"""§13 — birth data and names must never reach a log sink.

Two layers, because one is not enough:

1. **At the source.** Never interpolate a name or a date into an exception
   message. `redact()` gives a stable, non-reversible token you can log instead,
   so a support engineer can still correlate two reports without ever seeing
   the value.
2. **At the sink.** `PiiScrubbingFormatter` scrubs anything that slipped
   through — including third-party tracebacks we do not control, which is
   exactly where a raw value would otherwise surface.

Layer 1 is the fix; layer 2 is the net. `tests/test_pii_logging.py` is the
canary that fails the build if either regresses.
"""

import hashlib
import logging
import re

_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
# Any run of non-Latin letters is script-bearing user input (a name), never
# our own log vocabulary — this service's messages are ASCII by construction.
_NON_LATIN_RUN = re.compile(r"[^\x00-\x7F]{2,}")


def redact(value: object) -> str:
    """A stable token that identifies a value without revealing it.

    Correlatable across reports (same input → same token), non-reversible, and
    length-bearing so "why did this fail" stays debuggable.
    """
    text = "" if value is None else str(value)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"<redacted len={len(text)} sha256={digest}>"


def scrub_text(text: str) -> str:
    """Remove birth dates and script-bearing runs from an arbitrary string."""
    text = _ISO_DATE.sub("<redacted date>", text)
    return _NON_LATIN_RUN.sub("<redacted text>", text)


class PiiScrubbingFormatter(logging.Formatter):
    """Formats as usual, then scrubs — so tracebacks are covered too."""

    def format(self, record: logging.LogRecord) -> str:
        return scrub_text(super().format(record))


def install_log_scrubbing(logger: logging.Logger | None = None) -> None:
    """Attach the scrubbing formatter to every handler on `logger` (root by
    default). Call once at service startup, after logging is configured."""
    target = logger or logging.getLogger()
    for handler in target.handlers:
        existing = handler.formatter
        handler.setFormatter(
            PiiScrubbingFormatter(
                fmt=getattr(existing, "_fmt", None),
                datefmt=getattr(existing, "datefmt", None),
            )
        )
