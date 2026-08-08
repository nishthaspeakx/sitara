"""Langfuse-compatible tracing hooks (§9 cost controls).

§9 wants "Langfuse per-conversation cost traces, per-language dashboards,
alarms at ₹/DAU thresholds". This module emits Langfuse's own shapes — a
`trace` plus `span`/`generation` observations — through a `TraceSink`, so
wiring the real client later is a sink swap and not a pipeline change.

§13 is the constraint that shapes it: "birth data, message content, tokens can
structurally never appear in application logs". So the tracer records shapes,
counts and hashes, never text. `capture_content` exists for local debugging
and refuses to turn on outside dev — the refusal is the enforcement.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sitara_api.chat_orchestration.types import Stage

logger = logging.getLogger(__name__)


class TraceSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...


class NullSink:
    """Default. Traces are built and dropped — the pipeline still costs the
    same, so a sink swap never changes behaviour."""

    def emit(self, event: dict[str, Any]) -> None:  # noqa: D102
        return None


class MemorySink:
    """Test sink. Keeps every event in order."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class LoggingSink:
    """Structured log lines for environments without a Langfuse endpoint.

    Safe by construction: it can only see what the tracer already redacted.
    """

    def emit(self, event: dict[str, Any]) -> None:
        logger.info("trace", extra={"langfuse_event": event})


def _digest(text: str) -> str:
    """A stable handle for a string we are not allowed to record."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class TurnTrace:
    """One Langfuse trace per turn, with one observation per §9 stage."""

    sink: TraceSink
    user_id: str
    conversation_id: str
    locale: str
    capture_content: bool = False
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    _spans: list[dict[str, Any]] = field(default_factory=list)

    def start(self, *, intent: str | None = None) -> None:
        self.sink.emit(
            {
                "type": "trace",
                "id": self.trace_id,
                "name": "chat.turn",
                "userId": self.user_id,
                "sessionId": self.conversation_id,
                # Per-language dashboards (§9) are a tag query, so the locale
                # has to be a tag rather than buried in metadata.
                "tags": [f"locale:{self.locale}"] + ([f"intent:{intent}"] if intent else []),
                "metadata": {"locale": self.locale},
                "timestamp": _now(),
            }
        )

    def span(
        self,
        stage: Stage,
        *,
        status: str = "passed",
        metadata: dict[str, Any] | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """A non-model step. `content` is recorded only in dev (§13)."""
        event = self._observation("span", stage, status, metadata, content)
        self.sink.emit(event)
        return event

    def generation(
        self,
        stage: Stage,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        status: str = "passed",
        metadata: dict[str, Any] | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """A model call. `usage` is what the ₹/DAU alarm reads."""
        event = self._observation("generation", stage, status, metadata, content)
        event["model"] = model
        event["usage"] = {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
            "cache_read_input_tokens": cache_read_tokens,
            "cache_creation_input_tokens": cache_write_tokens,
        }
        self.sink.emit(event)
        return event

    def _observation(
        self,
        kind: str,
        stage: Stage,
        status: str,
        metadata: dict[str, Any] | None,
        content: str | None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "type": kind,
            "id": uuid.uuid4().hex,
            "traceId": self.trace_id,
            "name": stage.value,
            "stage": stage.value,
            "status": status,
            "level": "DEFAULT" if status == "passed" else "WARNING",
            "startTime": _now(),
            "metadata": dict(metadata or {}),
        }
        if content is not None:
            if self.capture_content:
                event["output"] = content
            else:
                # §13: the shape of the text, never the text.
                event["metadata"]["content_sha256_16"] = _digest(content)
                event["metadata"]["content_chars"] = len(content)
        self._spans.append(event)
        return event

    # -- test/inspection helpers ------------------------------------------

    def spans_for(self, stage: Stage) -> list[dict[str, Any]]:
        return [span for span in self._spans if span["stage"] == stage.value]


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def build_tracer(
    *,
    environment: str,
    capture_content: bool,
    langfuse_enabled: bool,
) -> tuple[TraceSink, bool]:
    """Pick a sink and settle the §13 question once, at wiring time."""
    if capture_content and environment not in ("dev", "test"):
        raise ValueError(
            "trace_capture_content records message content — refused outside dev/test (§13)"
        )
    sink: TraceSink = LoggingSink() if langfuse_enabled else NullSink()
    return sink, capture_content
