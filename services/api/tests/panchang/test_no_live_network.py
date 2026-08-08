"""Socket guard — CI can never reach a live vendor.

Fixture replay is a convention; this is the enforcement. With outbound sockets
blocked, any adapter that slips past MockTransport fails loudly here instead of
silently spending trial-account requests on every CI run.

Mongo is deliberately still reachable: it is our own dev-stack dependency on
localhost, not a paid third party.
"""

import datetime as dt  # noqa: E402
import socket

import pytest

from sitara_api.panchang.providers.base import PanchangQuery, ProviderName
from sitara_api.panchang.providers.breaker import CircuitBreaker
from sitara_api.panchang.providers.divineapi import DivineApiProvider
from sitara_api.panchang.providers.http import VendorClient
from tests.panchang.conftest import MUMBAI

QUERY = PanchangQuery(local_date=dt.date(2026, 8, 8), place=MUMBAI)


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture()
def no_outbound_sockets(monkeypatch: pytest.MonkeyPatch):
    """Block every connection except loopback (our own Mongo/Redis).

    Both DNS resolution and connect are guarded. Guarding connect alone makes
    the check depend on whether the CI runner can resolve the vendor's
    hostname — on a sandboxed runner the call dies at DNS and the guard never
    fires, so the test would pass without proving anything.
    """
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo
    blocked: list[object] = []

    def refuse(target: object) -> AssertionError:
        blocked.append(target)
        return AssertionError(
            f"a test tried to reach the live network at {target!r} — provider "
            "calls must replay fixtures (tests/panchang/fixtures/README.md)"
        )

    def guarded_getaddrinfo(host, *args, **kwargs):  # noqa: ANN001, ANN202
        if host not in LOOPBACK:
            raise refuse(host)
        return real_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(self, address, *args, **kwargs):  # noqa: ANN001, ANN202
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in LOOPBACK:
            raise refuse(address)
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    return blocked


class TestGuard:
    @pytest.mark.asyncio
    async def test_a_real_provider_call_is_blocked(self, no_outbound_sockets) -> None:  # noqa: ANN001
        """A VendorClient with no MockTransport is the mistake we are guarding
        against — here it must fail, not reach the vendor.

        The exception type is deliberately not pinned: anyio wraps whatever the
        socket layer raises in an ExceptionGroup, and which wrapper arrives is
        an httpx implementation detail. What matters is that the call did not
        succeed AND that the guard actually fired on an outbound address.
        """
        client = VendorClient(
            ProviderName.DIVINEAPI,
            "https://astroapi-4.divineapi.com",
            1.0,
            CircuitBreaker("divineapi"),
            transport=None,
        )
        provider = DivineApiProvider(client, api_key="k", auth_token="t")
        with pytest.raises(BaseException):  # noqa: B017, PT011
            await provider.panchang(QUERY)
        assert no_outbound_sockets, "the call resolved without hitting the guard"

    def test_loopback_is_still_permitted(self, no_outbound_sockets) -> None:  # noqa: ANN001
        """Mongo on 27018 is our own dev stack, not a paid third party."""
        probe = socket.socket()
        probe.settimeout(1.0)
        try:
            probe.connect(("127.0.0.1", 27018))
        except OSError:
            pytest.skip("dev-stack mongo not running on 27018")
        finally:
            probe.close()
