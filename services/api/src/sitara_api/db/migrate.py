"""`python -m sitara_api.db.migrate --phase expand|migrate|contract` (§14-deploy)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from sitara_api.config import Settings
from sitara_api.db.connection import make_mongo
from sitara_api.db.migrations import ALL, MigrationError, run_phase
from sitara_api.db.migrations.runner import PHASES


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sitara_api.db.migrate")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="skip the advisory lock (single-process local use only)",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    client, db = make_mongo(settings)
    try:
        report = await run_phase(db, ALL, args.phase, lock=not args.no_lock)
    except MigrationError as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    print(f"{settings.mongo_db} · {report.summary()}")
    for migration_id in report.applied:
        print(f"  applied  {migration_id}")
    for migration_id in report.skipped:
        print(f"  skipped  {migration_id} (already recorded)")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
