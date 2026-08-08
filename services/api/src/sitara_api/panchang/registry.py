"""Provider wiring (§5.2 Layer B, §8, §12).

One breaker per provider, held for the process lifetime so its rolling window
actually spans requests — a breaker rebuilt per call would never trip. The
breakers are exposed for the §12 admin "provider dashboards, circuit-breaker
states".
"""

from dataclasses import dataclass

import httpx

from sitara_api.config import Settings
from sitara_api.panchang.providers.base import ProviderName
from sitara_api.panchang.providers.breaker import CircuitBreaker
from sitara_api.panchang.providers.divineapi import DivineApiProvider
from sitara_api.panchang.providers.http import VendorClient
from sitara_api.panchang.providers.prokerala import ProkeralaProvider


@dataclass
class ProviderRegistry:
    divineapi: DivineApiProvider
    prokerala: ProkeralaProvider
    breakers: dict[str, CircuitBreaker]

    def health(self) -> list[dict]:
        """§12 admin: provider dashboards + circuit-breaker states."""
        return [breaker.snapshot() for breaker in self.breakers.values()]


def build_registry(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> ProviderRegistry:
    breakers = {
        name.value: CircuitBreaker(
            name=name.value,
            errors=settings.panchang_breaker_errors,
            window_seconds=settings.panchang_breaker_window_seconds,
            half_open_after_seconds=settings.panchang_breaker_half_open_seconds,
        )
        for name in ProviderName
    }

    divineapi = DivineApiProvider(
        VendorClient(
            ProviderName.DIVINEAPI,
            settings.divineapi_base_url,
            settings.divineapi_timeout_seconds,
            breakers[ProviderName.DIVINEAPI.value],
            transport=transport,
        ),
        api_key=settings.divineapi_api_key,
        auth_token=settings.divineapi_auth_token,
        paths=settings.divineapi_paths(),
    )
    prokerala = ProkeralaProvider(
        VendorClient(
            ProviderName.PROKERALA,
            settings.prokerala_base_url,
            settings.prokerala_timeout_seconds,
            breakers[ProviderName.PROKERALA.value],
            transport=transport,
        ),
        client_id=settings.prokerala_client_id,
        client_secret=settings.prokerala_client_secret,
        paths=settings.prokerala_paths(),
    )
    return ProviderRegistry(divineapi=divineapi, prokerala=prokerala, breakers=breakers)
