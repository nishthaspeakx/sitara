"""§33.1's expiry job — hard-delete the audio, leave the tombstone.

§33.1: "Expiry job hard-deletes assets + writes deleted_at tombstones."

Both halves matter and they pull in opposite directions, which is why this is a
job and not a TTL index:

- **Hard-delete** means the bytes go. Not a flag, not an archive tier, not a
  soft-delete a support query could undo. A user was promised thirty days.
- **Tombstone** means the ROW stays. A bubble whose audio has expired must say
  so — §33.1 has the UI "honestly drop playback of expired/deleted audio and
  show the transcript with a 'voice input' marker" — and it cannot say so if the
  row is gone, because a missing row and a never-existed row are the same
  absence. §12 also needs to answer "was this deleted, or was it never stored?"
  without keeping the audio to prove it.

MongoDB's TTL reaper deletes the DOCUMENT. It cannot unset one field and stamp
another, so it can do the first half and destroys the second. §36.2 already
forbids a TTL index outside §6.4's declared cells; this collection would fail
that check anyway, and the reason above is why the check is right.

Run it the way the other nightly jobs run (§7.1, §12):

    uv run python -m sitara_api.voice.expiry --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from sitara_api.voice.storage import COLLECTION

logger = logging.getLogger(__name__)

#: A batch bound, so one very large day cannot hold the event loop. The job is
#: idempotent and safe to run twice (§6.1), so a partial sweep simply finishes
#: on the next tick rather than needing a cursor to resume from.
DEFAULT_BATCH = 500


@dataclass(frozen=True)
class ExpiryReport:
    scanned: int
    deleted: int
    dry_run: bool

    def __str__(self) -> str:
        verb = "would delete" if self.dry_run else "deleted"
        return f"voice-note expiry: scanned {self.scanned}, {verb} {self.deleted}"


async def run_expiry(
    db: Any,
    *,
    now: dt.datetime | None = None,
    batch: int = DEFAULT_BATCH,
    dry_run: bool = False,
) -> ExpiryReport:
    """Sweep every note whose 30 days are up (§33.1)."""
    moment = now or dt.datetime.now(dt.UTC)
    # `deleted_at: None` is what makes this idempotent: a tombstoned row is
    # never swept twice, so re-running the job is free.
    query = {"expires_at": {"$lte": moment}, "deleted_at": None}

    scanned = deleted = 0
    cursor = db[COLLECTION].find(query, {"_id": 1}).limit(batch)
    async for row in cursor:
        scanned += 1
        if dry_run:
            continue
        result = await db[COLLECTION].update_one(
            {"_id": row["_id"], "deleted_at": None},
            {
                # The bytes go...
                "$unset": {"audio": ""},
                # ...and the row stays, saying so.
                "$set": {"deleted_at": moment, "updated_at": moment},
            },
        )
        deleted += result.modified_count

    report = ExpiryReport(
        scanned=scanned,
        deleted=scanned if dry_run else deleted,
        dry_run=dry_run,
    )
    # The count is a shape, not content (§13) — no ids, no user references.
    logger.info("%s", report)
    return report


async def delete_note(db: Any, asset_id: str, *, now: dt.datetime | None = None) -> bool:
    """§33.1's per-note delete, which is the same operation on demand.

    Deliberately the same code path as expiry rather than a second one: a
    per-note delete that left the bytes behind while the expiry job removed
    them would be two different promises wearing one word.
    """
    from sitara_api.voice.storage import MongoVoiceAssetStore

    return await MongoVoiceAssetStore(db).hard_delete(asset_id, now=now)


def main() -> None:  # pragma: no cover - operator entry point
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    args = parser.parse_args()

    from sitara_api.config import Settings
    from sitara_api.db.connection import make_mongo

    logging.basicConfig(level=logging.INFO)
    settings = Settings()

    async def _run() -> None:
        client = make_mongo(settings.mongodb_uri)
        try:
            report = await run_expiry(
                client[settings.mongodb_db], batch=args.batch, dry_run=args.dry_run
            )
            print(report)
        finally:
            client.close()

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
