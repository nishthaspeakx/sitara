"""Fixture replay transport — CI never touches a live vendor.

Fixtures are matched by request path, so a provider that changes its base URL
in config still replays. A request with no matching fixture raises rather than
falling through to the network, which is what makes the guarantee real.
"""

import json
from pathlib import Path
from typing import Any

import httpx

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


class NoFixture(AssertionError):
    """A test asked for a call nobody recorded."""


def load(provider: str, name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / provider / f"{name}.json").read_text(encoding="utf-8"))


def all_fixtures() -> list[tuple[str, str, dict[str, Any]]]:
    out = []
    for provider_dir in sorted(FIXTURE_ROOT.iterdir()):
        if not provider_dir.is_dir():
            continue
        for path in sorted(provider_dir.glob("*.json")):
            out.append((provider_dir.name, path.stem, json.loads(path.read_text("utf-8"))))
    return out


def transport_for(
    provider: str,
    names: list[str] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    """Replay every fixture for a provider, keyed by the path it recorded.

    `overrides` swaps in a modified body/status for one fixture — used to prove
    the adapter's failure paths without hand-rolling a second transport.
    """
    routes: dict[str, dict[str, Any]] = {}
    for name in names or [p.stem for p in (FIXTURE_ROOT / provider).glob("*.json")]:
        fixture = (overrides or {}).get(name) or load(provider, name)
        routes[fixture["_recording"]["request"]["path"]] = fixture

    def handler(request: httpx.Request) -> httpx.Response:
        fixture = routes.get(request.url.path)
        if fixture is None:
            raise NoFixture(f"no fixture for {request.method} {request.url.path}")
        return httpx.Response(
            status_code=fixture["status_code"],
            json=fixture.get("body", {}),
            request=request,
        )

    return httpx.MockTransport(handler)


def failing_transport(status_code: int = 503) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json={"error": "upstream"}, request=request)

    return httpx.MockTransport(handler)


def exploding_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.MockTransport(handler)
