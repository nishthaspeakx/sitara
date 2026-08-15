"""Migrations, in application order.

Adding one: create `mNNNN_<slug>.py` exposing `id`, `description`, `expand`,
`migrate` and `contract`, then append it to `ALL` below. Order is explicit
rather than discovered by filename glob — a deploy should never depend on how a
directory listing sorts.
"""

from sitara_api.db.migrations import (
    m0001_baseline,
    m0002_journal_saves,
    m0003_memorial_state,
)
from sitara_api.db.migrations.runner import (
    ContractTooEarlyError,
    DestructiveExpandError,
    Migration,
    MigrationError,
    MigrationReport,
    run_phase,
)

ALL: tuple[Migration, ...] = (  # type: ignore[assignment]
    m0001_baseline,
    m0002_journal_saves,
    m0003_memorial_state,
)

__all__ = [
    "ALL",
    "ContractTooEarlyError",
    "DestructiveExpandError",
    "Migration",
    "MigrationError",
    "MigrationReport",
    "run_phase",
]
