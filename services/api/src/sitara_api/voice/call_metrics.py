"""§33.5's six measures, instrumented from the first call (§43.5).

`call_gate.py` is the RULER — six thresholds and six directions, written before
any call UI existed so that nothing could be graded on a curve drawn to fit it.
This module is what puts numbers against that ruler. They are deliberately
separate files: a gate that also collected its own evidence would be a gate
that could be made to pass by changing how it counts.

Four are measured, two are not, and the difference is the point
---------------------------------------------------------------

- `first_audio_p95_s` — **measured.** The call reports the gap between the
  user's finalised utterance and the first synthesised byte leaving for them.
- `barge_in_success` — **measured.** Every barge-in reports whether the stream
  actually stopped.
- `network_recovery_success` — **measured.** Every drop reports whether it
  ended in a resume or a handoff *carrying context*, which is what §33.5 means
  by "success" — a tidy close that lost the transcript is a failure here.
- `safety_interception` — **measured, per locale**, and BLOCKED outside `en` by
  CC-010, because there is no Hindi call in which to intercept anything.
- `cost_per_call_user` — **NOT measured.** Only the INPUTS are recorded
  (streamed seconds per provider, per user). Turning those into ₹/user/month
  needs a contracted rate card and §30.3's billing period, neither of which
  exists. A plausible constant here would make the cheapest measure to fake
  the one the gate reads.
- `call_naturalness` — **NOT measured.** It is a human rating in beta (§33.5's
  own words), collected through §24.3's RatingTap. No amount of
  instrumentation produces it.

`observed()` returns a SPARSE dict, and `call_gate.evaluate` treats an absent
key as UNMEASURED rather than as zero. That is the whole contract between the
two files: this one never invents a reading, and that one never reads an
invention.

Where the numbers come from physically
--------------------------------------

The call runs in `sitara-realtime`, which holds no database. So realtime
reports each observation over the media socket and this module records it —
the same shape as every other "realtime knows it, api stores it" fact in the
system. A reservoir (not a running mean) for the latency measure, because
§33.5 asks for a **p95** and a mean cannot be recovered from one.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

#: How many first-audio samples a p95 is computed over. Large enough that one
#: cold start does not move the percentile, small enough that a fix shows up
#: within a session of beta traffic rather than a week of it.
LATENCY_RESERVOIR = 500

_KEY = "call:metric:{name}"


class CallObservation(StrEnum):
    """What a call may report. A CLOSED set, for the same reason §34.6's is.

    A metric name invented at a call site is a metric no gate reads and nobody
    notices is missing — the amber-forever failure `call_gate._indic_blocked`
    already guards against from the other direction.
    """

    #: Seconds from the user's finalised utterance to the first synthesised
    #: byte leaving for them. §33.5's "first-response audio", end to end as the
    #: user experiences it — NOT the vendor's TTFB, which excludes §9 entirely
    #: and would report a number no user has ever waited.
    FIRST_AUDIO_SECONDS = "first_audio_seconds"
    #: One barge-in attempt: did the synthesis actually stop?
    BARGE_IN_ATTEMPT = "barge_in_attempt"
    BARGE_IN_STOPPED = "barge_in_stopped"
    #: One socket drop, and whether it ended in §32.11's resume or §34.6's
    #: handoff WITH CONTEXT. A handoff that lost the transcript is a failure
    #: here even though the socket closed tidily.
    RECOVERY_ATTEMPT = "recovery_attempt"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    #: An in-call L2+ interception (§9's ladder), counted per locale so §33.5's
    #: "in all 3 languages" can be read rather than assumed from one.
    SAFETY_TRIGGERED = "safety_triggered"
    SAFETY_INTERCEPTED = "safety_intercepted"
    #: §33.5's cost input, not the measure. Seconds of vendor stream, so a rate
    #: card can multiply it later without re-running any calls.
    STT_STREAM_SECONDS = "stt_stream_seconds"
    TTS_STREAM_SECONDS = "tts_stream_seconds"


class MetricStore(Protocol):
    async def incr(self, name: str, amount: float = 1.0) -> None: ...
    async def observe(self, name: str, value: float) -> None: ...
    async def counters(self) -> dict[str, float]: ...
    async def samples(self, name: str) -> Sequence[float]: ...


@dataclass
class InMemoryMetricStore:
    """The fake, and it obeys the same contract as the real one.

    Root CLAUDE.md rule: a fake that accepts what the real implementation
    rejects is a defect in the fake. So this caps its reservoir at exactly
    `LATENCY_RESERVOIR` too — an uncapped fake would compute a p95 over every
    sample ever taken and disagree with production on the one number the gate
    reads.
    """

    _counters: dict[str, float] = field(default_factory=dict)
    _samples: dict[str, list[float]] = field(default_factory=dict)

    async def incr(self, name: str, amount: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + amount

    async def observe(self, name: str, value: float) -> None:
        bucket = self._samples.setdefault(name, [])
        bucket.append(value)
        if len(bucket) > LATENCY_RESERVOIR:
            del bucket[: len(bucket) - LATENCY_RESERVOIR]

    async def counters(self) -> dict[str, float]:
        return dict(self._counters)

    async def samples(self, name: str) -> Sequence[float]:
        return tuple(self._samples.get(name, ()))


#: The observations stored as a RESERVOIR (a Redis list) rather than a counter.
#: Reading one with GET raises WRONGTYPE, which is exactly what happened the
#: first time a real call recorded a latency sample — see `counters`.
_RESERVOIRS = frozenset({CallObservation.FIRST_AUDIO_SECONDS})


class RedisMetricStore:
    """Counters and a capped reservoir in Redis.

    No TTL. §33.5 is a launch gate read once by a person deciding whether to
    ship calls, not a dashboard — and a window that expired would quietly reset
    the evidence the decision rests on.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def incr(self, name: str, amount: float = 1.0) -> None:
        await self._redis.incrbyfloat(_KEY.format(name=name), amount)

    async def observe(self, name: str, value: float) -> None:
        key = _KEY.format(name=name)
        await self._redis.rpush(key, value)
        await self._redis.ltrim(key, -LATENCY_RESERVOIR, -1)

    async def counters(self) -> dict[str, float]:
        """Every counter key, including the per-locale ones.

        **Two defects lived in the previous four lines, and one live call found
        both.** It iterated `CallObservation` and issued a GET for each:

        1. `first_audio_seconds` is a LIST (a reservoir), and GET on a list
           raises `WRONGTYPE` — so the whole §33.5 read crashed the moment a
           real call recorded its first latency sample. Every test passed:
           `InMemoryMetricStore` keeps counters and samples in separate dicts,
           so it has no way to make this mistake. A fake that cannot fail the
           way the real store fails is a fake that hides the failure.
        2. §33.5's safety measure is stored per LOCALE
           (`safety_triggered:en`), and an enum-name lookup never sees a
           suffixed key — so the one per-language measure the spec is most
           insistent about could never have produced a number.

        Scanning the namespace and skipping non-counters fixes both, and keeps
        working when a locale is added.
        """
        out: dict[str, float] = {}
        reservoirs = {o.value for o in _RESERVOIRS}
        async for key in self._redis.scan_iter(match=_KEY.format(name="*")):
            name = (key.decode() if isinstance(key, bytes) else str(key)).split(
                _KEY.format(name=""), 1
            )[-1]
            # `safety_triggered:en` → the reservoir check is on the STEM.
            if name.split(":", 1)[0] in reservoirs:
                continue
            raw = await self._redis.get(key)
            if raw is None:
                continue
            try:
                out[name] = float(raw)
            except (TypeError, ValueError):
                continue
        return out

    async def samples(self, name: str) -> Sequence[float]:
        raw = await self._redis.lrange(_KEY.format(name=name), 0, -1)
        values: list[float] = []
        for item in raw or ():
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                continue
        return tuple(values)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank p95. None on an empty sample, never 0.0.

    Zero would be a passing latency, and "we have never measured this" must
    never render as the best possible reading — which is precisely the
    substitution §33.5's UNMEASURED state exists to prevent.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(-(-len(ordered) * fraction // 1))))
    return ordered[rank - 1]


def _ratio(counters: dict[str, float], numerator: str, denominator: str) -> float | None:
    total = counters.get(denominator, 0.0)
    if total <= 0:
        # No attempts is not a 100% success rate. It is no data, and §33.5's
        # gate treats no data as not-passing rather than as passing.
        return None
    return counters.get(numerator, 0.0) / total


class CallMetrics:
    """Record observations; read §33.5's measures back out."""

    def __init__(self, store: MetricStore) -> None:
        self._store = store

    async def record(
        self, observation: CallObservation, *, value: float = 1.0, locale: str | None = None
    ) -> None:
        """One observation. `locale` suffixes the key where §33.5 is per-language.

        Unknown names cannot be passed — `observation` is the enum, so a call
        site cannot mint a metric that nothing reads.
        """
        name = observation.value
        if locale and observation in _PER_LOCALE:
            name = f"{name}:{locale}"
        if observation is CallObservation.FIRST_AUDIO_SECONDS:
            await self._store.observe(name, value)
            return
        await self._store.incr(name, value)

    async def observed(self, locales: Sequence[str] = ("en", "hi", "hi-Latn")) -> dict[str, float]:
        """The sparse dict `call_gate.evaluate` takes.

        A measure with no data is ABSENT, not zero — see the module docstring.
        `cost_per_call_user` and `call_naturalness` are never present here at
        all, because nothing in a call produces either.
        """
        counters = await self._store.counters()
        out: dict[str, float] = {}

        p95 = percentile(
            await self._store.samples(CallObservation.FIRST_AUDIO_SECONDS.value), 0.95
        )
        if p95 is not None:
            out["first_audio_p95_s"] = p95

        barge_in = _ratio(
            counters,
            CallObservation.BARGE_IN_STOPPED.value,
            CallObservation.BARGE_IN_ATTEMPT.value,
        )
        if barge_in is not None:
            out["barge_in_success"] = barge_in

        recovery = _ratio(
            counters,
            CallObservation.RECOVERY_SUCCEEDED.value,
            CallObservation.RECOVERY_ATTEMPT.value,
        )
        if recovery is not None:
            out["network_recovery_success"] = recovery

        # §33.5 says "in all 3 languages", so the reading is the WORST locale,
        # never the average. An average would let a perfect English score carry
        # a language that intercepts nothing — which is the exact shape of
        # failure §18's "no averaging across languages, ever" already forbids
        # for the product metrics.
        per_locale = [
            _ratio(
                counters,
                f"{CallObservation.SAFETY_INTERCEPTED.value}:{locale}",
                f"{CallObservation.SAFETY_TRIGGERED.value}:{locale}",
            )
            for locale in locales
        ]
        if per_locale and all(value is not None for value in per_locale):
            out["safety_interception"] = min(value for value in per_locale if value is not None)

        return out


#: The measures §33.5 states per-language. Everything else is global.
_PER_LOCALE = frozenset(
    {CallObservation.SAFETY_TRIGGERED, CallObservation.SAFETY_INTERCEPTED}
)
