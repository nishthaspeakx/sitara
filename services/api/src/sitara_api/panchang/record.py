"""Fixture recorder — one real call per endpoint, then replay forever.

    DIVINEAPI_API_KEY=… DIVINEAPI_AUTH_TOKEN=… \\
    PROKERALA_CLIENT_ID=… PROKERALA_CLIENT_SECRET=… \\
    SITARA_RECORD_FIXTURES=1 \\
    uv run python -m sitara_api.panchang.record --all

Guarded twice on purpose: it needs both `SITARA_RECORD_FIXTURES=1` AND real
credentials. CI has neither, so it can never spend trial-account requests.

Everything written to disk is scrubbed of credentials. The recording carries
only a date, a place and public almanac data — no user data goes near it (§13).
"""

import argparse
import asyncio
import datetime as dt
import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
from sitara_schemas.facts import MuhuratType

from sitara_api.config import Settings
from sitara_api.panchang.providers.base import (
    MuhuratQuery,
    PanchangQuery,
    ProviderName,
    ResolvedPlace,
)
from sitara_api.panchang.registry import build_registry

logger = logging.getLogger(__name__)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3] / "tests" / "panchang" / "fixtures"
)

# Public, unremarkable inputs — a city and a date, nothing user-derived.
#
# SANDBOX CONSTRAINT: a Prokerala sandbox account rejects any date but January
# 1st ("In sandbox mode, only January 1st is allowed — any time and any year is
# accepted", error 1004). The fixtures exist to pin the response SHAPE and our
# parse of it, and a January date does that just as well as any other — so the
# default sits on Jan 1 and `--date` overrides it once production keys land.
SAMPLE_PLACE = ResolvedPlace(label="Mumbai", lat=19.076, lon=72.8777, tz="Asia/Kolkata")
SAMPLE_MUHURAT_PLACE = ResolvedPlace(
    label="Jaipur", lat=26.9124, lon=75.7873, tz="Asia/Kolkata"
)
SAMPLE_DATE = dt.date(2026, 1, 1)
SAMPLE_MUHURAT_RANGE = (dt.date(2026, 1, 1), dt.date(2026, 1, 1))

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "client_id",
    "client_secret",
    "access_token",
    "refresh_token",
    "token",
}
_BEARER = re.compile(r"bearer\s+\S+", re.IGNORECASE)


def scrub(value: Any) -> Any:
    """Remove anything that could be a credential, at any depth.

    Belt and braces: keys are matched by name AND string values are swept for
    bearer tokens, because a leaked trial key committed to git is a real
    incident, not a tidiness issue.
    """
    if isinstance(value, dict):
        return {
            key: ("SCRUBBED" if key.lower() in _SECRET_KEYS else scrub(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer SCRUBBED", value)
    return value


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes calls through to the live vendor and captures what came back."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.exchanges: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        await response.aread()
        try:
            body = response.json()
        except ValueError:
            body = {"_unparseable_body": response.text[:2000]}
        self.exchanges.append(
            {
                "request": {"method": request.method, "path": request.url.path},
                "status_code": response.status_code,
                "body": scrub(body),
            }
        )
        return response


def write_fixture(provider: str, name: str, exchange: dict[str, Any]) -> Path:
    path = FIXTURE_ROOT / provider / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "_recording": {
            "status": "recorded",
            "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
            "note": (
                "Recorded from the live API by sitara_api.panchang.record. "
                "Credentials scrubbed. Re-record only when the vendor's "
                "contract changes."
            ),
            "request": exchange["request"],
        },
        "status_code": exchange["status_code"],
        "body": exchange["body"],
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


async def _record(
    settings: Settings, providers: Sequence[str], sample_date: dt.date
) -> int:
    written: list[Path] = []
    seen_names: set[tuple[str, str]] = set()

    for provider_name in providers:
        transport = RecordingTransport()
        registry = build_registry(settings, transport=transport)
        provider = getattr(registry, provider_name)
        panchang_query = PanchangQuery(local_date=sample_date, place=SAMPLE_PLACE)
        muhurat_query = MuhuratQuery(
            # GENERAL, not a typed finder: Prokerala has no typed muhurat
            # endpoint (verified live), so a typed sample would record nothing
            # for it. DivineAPI answers both.
            muhurat_type=MuhuratType.GENERAL,
            date_from=sample_date,
            date_to=sample_date,
            place=SAMPLE_MUHURAT_PLACE,
        )

        # Exactly one call per endpoint.
        calls = (
            ("panchang", provider.panchang(panchang_query)),
            ("day_timings", provider.day_timings(panchang_query)),
            ("muhurat", provider.muhurat(muhurat_query)),
        )
        for label, coroutine in calls:
            before = len(transport.exchanges)
            try:
                await coroutine
            except Exception as exc:  # noqa: BLE001 - record the failure too
                logger.warning("%s %s failed: %s", provider_name, label, type(exc).__name__)
            # A provider may make an auth call first (Prokerala's /token), so
            # name each exchange from its own path rather than its position;
            # only a genuine repeat of the same name gets a numeric suffix.
            for exchange in transport.exchanges[before:]:
                path = exchange["request"]["path"]
                name = "token" if path.rstrip("/").endswith("token") else label
                candidate, suffix = name, 1
                while (provider_name, candidate) in seen_names:
                    candidate, suffix = f"{name}_{suffix}", suffix + 1
                seen_names.add((provider_name, candidate))
                written.append(write_fixture(provider_name, candidate, exchange))

    for path in written:
        print(f"wrote {path.relative_to(FIXTURE_ROOT.parents[2])}")
    if not written:
        print("nothing recorded — check credentials and connectivity")
        return 1
    print(
        "\nNext: run `uv run pytest tests/panchang -q`. Where a real payload "
        "disagrees with an adapter's assumed field names, fix the ADAPTER "
        "(or its configurable path in .env) — never the fixture."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record provider fixtures (one call each)")
    parser.add_argument("--all", action="store_true", help="record both providers")
    parser.add_argument("--provider", choices=[p.value for p in ProviderName], default=None)
    parser.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=SAMPLE_DATE,
        help=(
            "local date to record for (default 2026-01-01 — a Prokerala SANDBOX "
            "account rejects every other date)"
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()

    if not settings.sitara_record_fixtures:
        print(
            "refusing to record: set SITARA_RECORD_FIXTURES=1 to make one real "
            "call per endpoint (this spends trial-account requests)"
        )
        return 2

    providers = (
        ["divineapi", "prokerala"] if args.all or not args.provider else [args.provider]
    )
    missing = [
        name
        for name in providers
        if (name == "divineapi" and not settings.divineapi_api_key)
        or (name == "prokerala" and not settings.prokerala_client_id)
    ]
    if missing:
        print(f"refusing to record: no credentials configured for {', '.join(missing)}")
        return 2

    return asyncio.run(_record(settings, providers, args.date))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
