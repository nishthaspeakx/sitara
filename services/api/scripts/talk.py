"""Talk to Tara from a terminal — DEV ONLY (M5 acceptance harness).

The web app has no chat surface yet: §24/§25's chat screens are M8's
(Prompt P9c), a parallel frontend track. This is the stand-in that makes M5's
acceptance test runnable — "chat with Tara locally in three locales; ask her a
chart question and open the payload; try to trick her into inventing a
muhurat".

It bypasses the HTTP layer and its §34.5 session cookie ONLY. Everything below
the router is the real thing: the real Claude models, the real astrology
facade, the real §6.4 collections, and every validator in §9's pipeline. What
you see is what a user would get.

    cd services/api
    set -a; . ./.env; set +a          # ANTHROPIC_API_KEY, COHERE_API_KEY
    uv run python scripts/talk.py --locale en

Commands inside the REPL:
    :en :hi :hi-Latn   switch locale mid-conversation
    :facts             print the full fact snapshots behind the last reply
    :why               print the last turn's stage-by-stage trace
    :quit
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sitara_api.chat_orchestration import ChatSettings, build_pipeline  # noqa: E402
from sitara_api.chat_orchestration.tracing import MemorySink  # noqa: E402
from sitara_api.chat_orchestration.types import BirthProfile, TurnRequest  # noqa: E402
from sitara_api.config import Settings  # noqa: E402
from sitara_api.db import ensure_indexes, make_mongo  # noqa: E402
from sitara_api.memory import MemorySettings, build_memory_service  # noqa: E402
from sitara_api.panchang.adapter import AstroPanchangAdapter  # noqa: E402
from sitara_api.panchang.cache import PanchangCache  # noqa: E402
from sitara_api.panchang.places import default_resolver  # noqa: E402
from sitara_api.panchang.registry import build_registry  # noqa: E402
from sitara_api.panchang.service import PanchangService  # noqa: E402

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chat with Tara locally (dev only)")
    parser.add_argument("--locale", default="en", choices=["en", "hi", "hi-Latn"])
    parser.add_argument("--city", default="Delhi", help="current location for timings (§30.2)")
    parser.add_argument(
        "--no-birth-data",
        action="store_true",
        help="pretend the profile is empty, to see the §5.4 cannot-calculate path",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.environment not in ("dev", "test"):
        print(f"refusing to run against environment={settings.environment!r}", file=sys.stderr)
        return 1

    client, db = make_mongo(settings)
    await ensure_indexes(db)
    registry = build_registry(settings)
    panchang = PanchangService(
        cache=PanchangCache(db),
        divineapi=registry.divineapi,
        prokerala=registry.prokerala,
        astro=AstroPanchangAdapter(settings.astro_base_url, settings.astro_timeout_seconds),
    )
    memory = await build_memory_service(
        db=db, settings=MemorySettings(), environment=settings.environment
    )
    sink = MemorySink()
    pipeline = build_pipeline(
        chat_settings=ChatSettings(),
        environment=settings.environment,
        db=db,
        panchang_service=panchang,
        numerology_adapter=None,
        place_resolver=default_resolver(),
        memory_retriever=memory,
    )
    if pipeline is None:
        print("no ANTHROPIC_API_KEY in the environment — did you source .env?", file=sys.stderr)
        return 1
    pipeline._sink = sink  # noqa: SLF001 — dev harness wants the trace

    locale = args.locale
    conversation = ObjectId()
    user = ObjectId("6a70000000000000000000a1")
    profile = (
        BirthProfile()
        if args.no_birth_data
        else BirthProfile(has_date=True, has_exact_time=True, has_place=True, tz="Asia/Kolkata")
    )
    last = None

    print(f"{BOLD}Tara — dev harness{RESET}  locale={locale} city={args.city}")
    print(f"{DIM}:en :hi :hi-Latn to switch · :facts · :why · :quit{RESET}\n")

    while True:
        try:
            text = input(f"{BOLD}you [{locale}]{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in (":quit", ":q"):
            break
        if text.lstrip(":") in ("en", "hi", "hi-Latn"):
            locale = text.lstrip(":")
            print(f"{DIM}locale → {locale}{RESET}")
            continue
        if text == ":facts":
            if not last or not last.fact_snapshots:
                print(f"{DIM}no facts behind the last reply{RESET}")
            for snap in last.fact_snapshots if last else []:
                print(f"\n{BOLD}{snap.fact_id}{RESET}")
                print(f"  kind={snap.kind.value} source={snap.source.value} "
                      f"confidence={snap.confidence}")
                print(f"  value={snap.value.model_dump_json()}")
                print(f"  valid {snap.valid_from.isoformat()} → "
                      f"{snap.valid_to.isoformat() if snap.valid_to else 'open'}")
            continue
        if text == ":why":
            for event in sink.events:
                stage = event.get("stage")
                if stage:
                    meta = {k: v for k, v in event["metadata"].items()
                            if not k.startswith("content_")}
                    print(f"  {stage:<18} [{event['status']}] {meta}")
            continue

        sink.events.clear()
        last = await pipeline.run(
            TurnRequest(
                user_id=str(user),
                conversation_id=str(conversation),
                text=text,
                locale=locale,
                now=dt.datetime.now(dt.UTC),
                profile=profile,
                place_label=args.city,
            )
        )
        print(f"\n{BOLD}Tara{RESET} {last.text}")
        print(
            f"{DIM}  intent={last.intent.value} · confidence={last.confidence.value} · "
            f"safety={last.safety.level.name} · facts={len(last.fact_ids)} · "
            f"regens={last.regenerations}"
            + (" · FELL BACK" if last.message_key else "")
            + f"{RESET}\n"
        )

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
