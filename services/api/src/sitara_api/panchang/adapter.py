"""Adapter over the internal sitara-astro service (§6.3).

This is the §8 ladder's INTERNAL rung: "DivineAPI down → internal panchang (if
within validated scope)". sitara-astro stays internal — this service is the
only path by which its facts reach a client.
"""

import datetime as dt
import logging

import httpx
from sitara_schemas.facts import FactSnapshot, Tradition

from sitara_api.panchang.providers.base import ResolvedPlace

logger = logging.getLogger(__name__)


class AstroPanchangAdapter:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def panchang(
        self,
        local_date: dt.date,
        place: ResolvedPlace,
        tradition: Tradition,
        *,
        include_day_timings: bool = True,
        chart_version: int = 1,
    ) -> list[FactSnapshot] | None:
        """Layer-A facts, or None when the engine cannot answer.

        None rather than an exception: to the ladder above, "our engine has no
        answer for this place" (polar night, unknown zone) is just the next rung
        being unavailable — not a failure worth surfacing on its own.
        """
        payload = {
            "local_date": local_date.isoformat(),
            "place": {
                "name": place.label,
                "lat": place.lat,
                "lon": place.lon,
                "tz": place.tz,
            },
            "tradition": tradition.value,
            "include_day_timings": include_day_timings,
            "chart_version": chart_version,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/facts/panchang", json=payload
                )
        except httpx.HTTPError:
            # Log the failure, not the payload: it carries coordinates (§13).
            logger.warning("sitara-astro panchang call failed")
            return None

        if response.status_code != 200:
            logger.warning("sitara-astro panchang returned %s", response.status_code)
            return None
        return [FactSnapshot.model_validate(f) for f in response.json()["facts"]]
