"""Adapter over the internal sitara-astro service (§6.3).

Every external provider sits behind an adapter with typed errors — the §34.4
envelope, never a raw upstream body. sitara-astro stays internal: this is the
only path by which its numerology facts reach a client.
"""

import logging

import httpx
from sitara_schemas import ErrorCode
from sitara_schemas.facts import FactSnapshot

from sitara_api.errors import ApiError

logger = logging.getLogger(__name__)

# §13: never log a request body — it carries the name and date of birth.
_ASTRO_CODES = {
    ErrorCode.ASTRO_NAME_UNCONFIRMED,
    ErrorCode.ASTRO_NAME_INVALID,
    ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA,
}


class AstroNumerologyAdapter:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def compute(self, payload: dict) -> list[FactSnapshot]:
        url = f"{self._base_url}/v1/facts/numerology"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError:
            # Log the failure, not the payload.
            logger.warning("sitara-astro numerology call failed", exc_info=False)
            raise ApiError(ErrorCode.ASTRO_ENGINE_UNAVAILABLE) from None

        if response.status_code == 200:
            return [FactSnapshot.model_validate(f) for f in response.json()["facts"]]

        # Pass a known ASTRO_* code straight through so the client sees one
        # taxonomy; anything else becomes an engine-unavailable envelope.
        code = self._upstream_code(response)
        if code is not None and code in _ASTRO_CODES:
            raise ApiError(code)
        logger.warning("sitara-astro returned %s", response.status_code)
        raise ApiError(ErrorCode.ASTRO_ENGINE_UNAVAILABLE)

    @staticmethod
    def _upstream_code(response: httpx.Response) -> ErrorCode | None:
        try:
            return ErrorCode(response.json().get("code"))
        except (ValueError, KeyError, TypeError):
            return None
