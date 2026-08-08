"""Nightly consolidation: decay stale memories (§32.4, diagram 8).

Diagram 8's last box is "Nightly consolidation: dedupe · decay stale · theme
extraction". This is the decay third of it — the deterministic third. Dedupe
and theme extraction need the embedding space and a model, and land with the
consolidation worker; decay is arithmetic on a clock and needs neither.

What the job does NOT do is delete. §32.4 retains "until user deletes" and
§30.5 makes deletion the user's act; a decayed memory drops out of retrieval
and stays in the vault. A cleanup job that quietly removed what Tara had
promised to remember would be the opposite of §0.8's "the user always remains
in control of what is kept".

    uv run python -m sitara_api.memory.decay --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys
from dataclasses import dataclass

from bson import ObjectId

from sitara_api.memory.models import Memory, recomputed_decay
from sitara_api.memory.taxonomy import NEVER_DECAYS, RETRIEVAL_FLOOR

logger = logging.getLogger(__name__)

#: Skip a write when the score barely moved — a nightly full-collection
#: rewrite for six decimal places of drift is a lot of IO for nothing.
WRITE_THRESHOLD = 0.005


@dataclass(frozen=True)
class DecayReport:
    scanned: int = 0
    updated: int = 0
    below_floor: int = 0
    never_decays: int = 0

    def summary(self) -> str:
        return (
            f"scanned={self.scanned} updated={self.updated} "
            f"below_floor={self.below_floor} never_decays={self.never_decays}"
        )


def plan(
    memories: list[Memory], now: dt.datetime
) -> tuple[list[tuple[ObjectId, float]], DecayReport]:
    """Pure: decide the writes. Separated so the arithmetic is testable
    without a database, which is most of what could be wrong here."""
    updates: list[tuple[ObjectId, float]] = []
    below_floor = 0
    never = 0

    for memory in memories:
        if memory.type in NEVER_DECAYS:
            never += 1
            # §32.4: 1, 3 and 11 never auto-decay. If a stored score ever drifts
            # below 1.0 for one of them, correct it — that is a bug healing.
            if memory.decay_score < 1.0:
                updates.append((memory.memory_id, 1.0))
            continue
        fresh = recomputed_decay(memory, now)
        if fresh < RETRIEVAL_FLOOR:
            below_floor += 1
        if abs(fresh - memory.decay_score) >= WRITE_THRESHOLD:
            updates.append((memory.memory_id, fresh))

    return updates, DecayReport(
        scanned=len(memories),
        updated=len(updates),
        below_floor=below_floor,
        never_decays=never,
    )


async def run(db, *, now: dt.datetime | None = None, dry_run: bool = False) -> DecayReport:  # noqa: ANN001
    from sitara_api.memory.store import MemoryStore

    moment = now or dt.datetime.now(dt.UTC)
    store = MemoryStore(db)
    memories = [Memory.from_doc(doc) async for doc in db.memories.find({})]
    updates, report = plan(memories, moment)
    if not dry_run:
        await store.set_decay_scores(updates)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nightly memory decay (§32.4)")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    from sitara_api.config import Settings
    from sitara_api.db import make_mongo

    settings = Settings()
    client, db = make_mongo(settings)
    try:
        report = asyncio.run(run(db, dry_run=args.dry_run))
    finally:
        client.close()
    print(f"memory decay {'(dry run) ' if args.dry_run else ''}— {report.summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
