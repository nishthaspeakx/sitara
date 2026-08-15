"""Give each persona a CONVERSATION with Tara — through the real §9 pipeline.

    uv run python -m scripts.seed_demo_chat            # needs the API running
    uv run python -m scripts.seed_demo_chat --persona ritu

`seed_demo_history` fills the Journal, the vault and the reflections. It leaves
`messages` empty, so S18 opens on a blank thread for every persona and a demo's
first impression of Ask Tara is that nobody has ever used it.

── Why this drives HTTP rather than the pipeline directly ────────────────────

`seed_demo_history` builds its own service objects because §7.1's brief
generator is reachable that way. §9's is not, honestly: the turn pipeline reads
`app.state` for the model client, the fact tools, the safety ladder, the memory
service and the tracer, and reconstructing that here would be a second wiring
of the chat stack — the exact "two implementations drift" failure this codebase
keeps recording.

So this posts to `POST /v1/chat/turn` on the running API, with a real session
cookie, exactly as the browser does. Every citation in the seeded thread is one
the grounding validator actually produced, and a turn that §9 would refuse is
refused here too.

**It therefore requires the API to be up**, and says so rather than failing
obscurely. That is the trade: a seeder that needs a running service, in
exchange for a thread that could not contain a sentence the product would not
have said.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import httpx

from sitara_api.config import Settings
from sitara_api.db.seed import PERSONAS, UnsafeSeedError, _phone, assert_safe

#: Questions chosen to LAND ON FACTS, so the thread shows §30.4's citations
#: rather than pleasantries. The first is S18's own suggestion chip; the second
#: leans on the natal chart, so a persona with no birth time gets the honest
#: Moon-chart answer instead — which is worth having in a demo thread too.
ASKS: dict[str, tuple[str, ...]] = {
    "en": (
        "When is a good time today?",
        "What's the moon doing for me today?",
    ),
    "hi": (
        "आज कौन सा समय अच्छा है?",
        "आज चंद्रमा मेरे लिए क्या कह रहे हैं?",
    ),
    # The Hinglish second ask is a NAKSHATRA question rather than a "what is the
    # moon doing for me" one. The latter grounded twice and was rejected twice,
    # so §9 served the safe fallback — correct behaviour (she declined rather
    # than inventing) and a poor thing to seed a demo thread with. The
    # rejection is worth knowing about on its own and is recorded in the
    # runbook's known gaps rather than hidden by this swap.
    "hi-Latn": (
        "Aaj accha samay kaunsa hai?",
        "Aaj kaunsa nakshatra chal raha hai?",
    ),
}


async def _conversation_for(user_id: str) -> str | None:
    """The persona's seeded conversation id, read straight from Mongo.

    Read rather than created: `db.seed` already writes one `conversations` row
    per persona and §28.3 gives an account exactly one history. Posting to a
    fresh id would leave the seeded row empty and the thread orphaned.
    """
    from bson import ObjectId

    from sitara_api.db.connection import make_mongo

    client, db = make_mongo(Settings())
    try:
        row = await db.conversations.find_one({"user_id": ObjectId(user_id)})
        return str(row["_id"]) if row else None
    finally:
        client.close()


async def _seed_one(
    client: httpx.AsyncClient, base: str, persona: Any, index: int
) -> tuple[int, int]:
    """Sign in as one persona and ask two questions. Returns (turns, cited)."""
    phone = _phone(index)
    auth = await client.post(
        f"{base}/auth/session",
        json={"id_token": f"dev:{phone}", "locale": persona.locale},
    )
    if auth.status_code != 200:
        print(f"  {persona.handle}: sign-in failed ({auth.status_code}) — "
              "is AUTH_DEV_BYPASS on?", file=sys.stderr)
        return (0, 0)

    # §28.3 is ONE history per account, so the thread continues the persona's
    # own seeded conversation rather than opening a second one — a demo whose
    # Ask tab held a different conversation from the Journal's would be showing
    # two histories for one person.
    user_id = auth.json()["user_id"]
    conversation_id = await _conversation_for(user_id)
    if conversation_id is None:
        print(f"  {persona.handle}: no seeded conversation — run db.seed first",
              file=sys.stderr)
        return (0, 0)

    turns = cited = 0
    for ask in ASKS.get(persona.locale, ()):
        response = await client.post(
            f"{base}/v1/chat/turn",
            json={
                "conversation_id": conversation_id,
                "text": ask,
                "locale": persona.locale,
            },
            timeout=180.0,
        )
        if response.status_code != 200:
            print(f"  {persona.handle}: turn refused ({response.status_code})",
                  file=sys.stderr)
            continue
        body = response.json()
        turns += 1
        # §30.4's citation spans, computed by the grounding validator. Their
        # presence is the whole point of seeding through the real path.
        if body.get("citations"):
            cited += 1
        reply = (body.get("text") or "").replace("\n", " ")
        print(f"  {persona.handle} [{persona.locale}] «{ask}»")
        print(f"      → {reply[:110]}{'…' if len(reply) > 110 else ''}"
              f"   [{len(body.get('citations') or [])} citation(s)]")
    return (turns, cited)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.seed_demo_chat")
    parser.add_argument("--base", default="http://127.0.0.1:8001", help="API base URL")
    parser.add_argument("--persona", action="append", default=[], help="handle (repeatable)")
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        assert_safe(settings)
    except UnsafeSeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    wanted = set(args.persona)
    turns = cited = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            health = await client.get(f"{args.base}/healthz")
            health.raise_for_status()
        except Exception:  # noqa: BLE001
            print(
                f"the API is not answering at {args.base}. This seeder posts real "
                "turns through §9, so it needs the service running:\n"
                "  cd services/api && uv run uvicorn sitara_api.main:app --port 8001",
                file=sys.stderr,
            )
            return 1

        for index, persona in enumerate(PERSONAS, start=1):
            if wanted and persona.handle not in wanted:
                continue
            # A fresh client per persona: session cookies are per-account and
            # one jar would carry the last persona's session into the next.
            async with httpx.AsyncClient(timeout=30.0) as scoped:
                got, cite = await _seed_one(scoped, args.base, persona, index)
            turns += got
            cited += cite

    print(f"\nseeded demo chat:\n  {turns:3d}  turns\n  {cited:3d}  with citations")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
