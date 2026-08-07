"""Shared HTTP plumbing for the panchang vendors (SPEC §6.3, §8, §34.4).

Every external provider sits behind an adapter with a circuit breaker and typed
errors. Two invariants live here so neither adapter can forget them:

* A vendor's response body NEVER escapes. Callers see the §34.4 envelope's
  codes; the upstream JSON is not logged either, because vendor payloads echo
  the coordinates and dates we sent (§13).
* An open breaker fails fast, without spending the caller's timeout, so the §8
  degradation ladder gets its turn inside the latency budget.
"""

import logging
from collections.abc import Mapping
from typing import Any

import httpx
from sitara_schemas import ErrorCode

from sitara_api.errors import ApiError
from sitara_api.panchang.providers.base import ProviderName
from sitara_api.panchang.providers.breaker import BreakerOpen, CircuitBreaker

logger = logging.getLogger(__name__)


class ProviderUnavailable(Exception):
    """This vendor cannot answer right now.

    Distinct from ApiError on purpose: it is an input to the §8 ladder, not an
    outcome. Only the service layer, having exhausted every rung, converts the
    situation into a user-visible envelope.
    """

    def __init__(self, provider: ProviderName, reason: str) -> None:
        super().__init__(f"{provider.value}: {reason}")
        self.provider = provider
        self.reason = reason


class ProviderMisconfigured(ProviderUnavailable):
    """No credentials configured. Treated as 'down', never as a crash — a
    missing key must degrade like an outage (the playbook's kill-the-key
    acceptance), not 500 the request."""


class VendorClient:
    """One vendor's HTTP surface: breaker, timeout, and error translation."""

    def __init__(
        self,
        provider: ProviderName,
        base_url: str,
        timeout_seconds: float,
        breaker: CircuitBreaker,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._breaker = breaker
        self._transport = transport

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            self._breaker.check()
        except BreakerOpen as exc:
            raise ProviderUnavailable(self.provider, "circuit open") from exc

        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(
                    method, url, params=params, json=json_body, data=data, headers=headers
                )
        except httpx.HTTPError as exc:
            self._breaker.record_failure()
            # Log the failure class, never the request: it carries coordinates
            # and dates (§13).
            logger.warning("panchang provider %s transport failure", self.provider.value)
            raise ProviderUnavailable(self.provider, "transport error") from exc

        if response.status_code >= 500:
            self._breaker.record_failure()
            logger.warning(
                "panchang provider %s returned %s", self.provider.value, response.status_code
            )
            raise ProviderUnavailable(self.provider, f"upstream {response.status_code}")

        if response.status_code in (401, 403):
            # Credentials rejected. Counts as a failure so a revoked key trips
            # the breaker instead of retrying forever.
            self._breaker.record_failure()
            logger.warning("panchang provider %s rejected our credentials", self.provider.value)
            raise ProviderUnavailable(self.provider, "unauthorised")

        if response.status_code == 429:
            self._breaker.record_failure()
            raise ProviderUnavailable(self.provider, "rate limited")

        if response.status_code >= 400:
            # A 4xx we caused. Not a provider outage, so it does not trip the
            # breaker — but it is still not an answer.
            logger.warning(
                "panchang provider %s rejected the request (%s)",
                self.provider.value,
                response.status_code,
            )
            raise ProviderUnavailable(self.provider, f"request rejected {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            self._breaker.record_failure()
            raise ProviderUnavailable(self.provider, "unparseable body") from exc

        self._breaker.record_success()
        return payload


def unparseable(provider: ProviderName, detail: str) -> ProviderUnavailable:
    """A 200 whose shape we do not recognise is an outage, not a fact.

    Serving a half-understood vendor payload would violate cite-or-die (§5.3):
    we would be asserting a timing we cannot actually vouch for.
    """
    logger.warning("panchang provider %s sent an unrecognised shape: %s", provider.value, detail)
    return ProviderUnavailable(provider, f"unrecognised response shape ({detail})")


def engine_unavailable() -> ApiError:
    """The §34.4 envelope for 'every rung of the ladder failed'."""
    return ApiError(ErrorCode.ASTRO_ENGINE_UNAVAILABLE)
