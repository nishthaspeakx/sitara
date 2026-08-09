"""Adapter over sitara-astro's natal / dasha / transit endpoints (§5.2 Layer A).

The third and last adapter over the internal engine, alongside
`panchang.adapter` and `numerology.adapter`, and it follows their shape exactly:
a breaker in front, typed `FactSnapshot`s out, and never a raw upstream body.

Two properties are load-bearing and neither is visible from the call site:

* **Nothing here is cached by this class.** §7.2 makes `natal_chart:{subject}:
  {engine_v}:{ayanamsa}` permanent until an engine bump, and §6.4 gives
  `charts` the "keep last 3 versions" rule — that is a STORE's job, and putting
  a second cache here would give the same fact two lifetimes. `ChartFacts`
  below reads the store and calls this only on a miss.

* **The subject is never a user id in a shared key, and never a raw one here
  either.** §7.2 separates user-specific from global keys by construction; the
  natal key IS user-specific, so the id may appear — but the engine's `subject`
  field also lands inside every `fact_id` it mints (§34.2's grammar), and those
  ids travel into `guidance_logs` and a Trust Sheet. The product id is what
  belongs there, not a Firebase uid or a phone.

§13 governs the logging: birth details are the crown jewels, so a failure logs
the failure and never the payload — the same rule the numerology adapter
already follows, for the same reason.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sitara_schemas import ErrorCode
from sitara_schemas.facts import FactSnapshot

from sitara_api.panchang.providers.breaker import BreakerOpen, CircuitBreaker

logger = logging.getLogger(__name__)

#: The engine declines rather than guessing when birth data is too thin
#: (§5.3). Passed through so the caller can tell "no data" from "engine down".
_PASSTHROUGH_CODES = {ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA}


class ChartEngineUnavailable(Exception):
    """The engine could not answer. The caller degrades; it never approximates."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class InsufficientBirthData(Exception):
    """§5.3: not enough to compute, and we do not guess at the rest.

    Distinct from `ChartEngineUnavailable` because the two degrade differently:
    an outage is temporary and worth retrying, while a missing birth time is a
    thing to ASK THE USER for (§28.2's missing-birth-time variant).
    """


@dataclass(frozen=True)
class BirthInput:
    """What the engine needs, and nothing else.

    Deliberately not the `birth_details` document: that row is CSFLE-encrypted
    field by field and carries rectification notes the engine has no use for.
    The facade decrypts, narrows to this, and passes it on — so the blast
    radius of an adapter bug is these five fields.
    """

    date: dt.date
    time: dt.time | None
    place_name: str
    lat: float
    lon: float
    tz: str
    fold: int | None = None

    @property
    def has_exact_time(self) -> bool:
        return self.time is not None

    def to_payload(self) -> dict[str, Any]:
        # §5.3: a chart with no birth time is a MOON chart, not a chart with a
        # guessed ascendant. The engine owns that distinction; what this must
        # not do is invent a noon default and let the lagna look computed.
        if self.time is None:
            raise InsufficientBirthData("birth time is required for a natal chart")
        payload: dict[str, Any] = {
            "date": self.date.isoformat(),
            "time": self.time.isoformat(),
            "place": {
                "name": self.place_name,
                "lat": self.lat,
                "lon": self.lon,
                "tz": self.tz,
            },
        }
        if self.fold is not None:
            payload["fold"] = self.fold
        return payload


class AstroChartAdapter:
    """natal · dasha · transits, behind one breaker (§8)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._breaker = breaker or CircuitBreaker(name="sitara-astro-chart")

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def natal(
        self, birth: BirthInput, *, subject: str, chart_version: int = 1
    ) -> list[FactSnapshot]:
        return await self._facts(
            "natal",
            {
                "birth": birth.to_payload(),
                "subject": subject,
                "chart_version": chart_version,
            },
        )

    async def dasha(
        self, birth: BirthInput, *, subject: str, chart_version: int = 1
    ) -> list[FactSnapshot]:
        return await self._facts(
            "dasha",
            {
                "birth": birth.to_payload(),
                "subject": subject,
                "chart_version": chart_version,
            },
        )

    async def transits(
        self,
        birth: BirthInput,
        on: dt.date,
        *,
        subject: str,
        chart_version: int = 1,
    ) -> list[FactSnapshot]:
        """Gochar for one UTC date, against this person's natal chart.

        `on` is a UTC date by the endpoint's own contract. The caller passes
        the user's LOCAL date's UTC instant rather than `date.today()`: a brief
        for the 12th in Kolkata must not be computed against the 11th because
        the worker happened to be in London.
        """
        return await self._facts(
            "transits",
            {
                "birth": birth.to_payload(),
                "transit_date_utc": on.isoformat(),
                "subject": subject,
                "chart_version": chart_version,
            },
        )

    # -- transport ---------------------------------------------------------

    async def _facts(self, path: str, payload: dict[str, Any]) -> list[FactSnapshot]:
        try:
            self._breaker.check()
        except BreakerOpen:
            # §8: fail fast rather than spend the caller's timeout discovering
            # what we already know. The ladder above gets its turn sooner.
            raise ChartEngineUnavailable(f"{path}:breaker_open") from None

        url = f"{self._base_url}/v1/facts/{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError:
            # §13: the payload carries a date, time and place of birth.
            self._breaker.record_failure()
            logger.warning("sitara-astro %s call failed (transport)", path)
            raise ChartEngineUnavailable(f"{path}:transport") from None

        if response.status_code == 200:
            self._breaker.record_success()
            return [FactSnapshot.model_validate(f) for f in response.json()["facts"]]

        code = _upstream_code(response)
        if code is not None and code in _PASSTHROUGH_CODES:
            # A declining engine is a HEALTHY engine — it is telling us the
            # birth data is thin. Recording it as a breaker failure would trip
            # the circuit on a population of users with no birth time.
            self._breaker.record_success()
            raise InsufficientBirthData(f"{path}:{code.value}")

        self._breaker.record_failure()
        logger.warning("sitara-astro %s returned %s", path, response.status_code)
        raise ChartEngineUnavailable(f"{path}:http_{response.status_code}")


def _upstream_code(response: httpx.Response) -> ErrorCode | None:
    try:
        return ErrorCode(response.json().get("code"))
    except (ValueError, KeyError, TypeError):
        return None
