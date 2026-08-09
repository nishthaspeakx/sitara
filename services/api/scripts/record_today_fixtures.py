#!/usr/bin/env python3
"""Record §28.2's sixteen variants from the real pipeline into committed JSON.

    uv run python scripts/record_today_fixtures.py

The output lands in `apps/web/tests/__fixtures__/today/<variant>.<locale>.json`
and is replayed by `apps/web/scripts/stub-api.mjs` over the real request path.

**Why record rather than author.** The web suite has to run without Python,
Mongo or a provider — `pnpm design-qa` is meant to be runnable on a laptop and
CI never calls a vendor. The tempting alternative is to hand-write the payloads
in the stub, and it fails in a way that is invisible until it matters: every
§24.8 baseline would be a picture of a brief no engine ever produced, and the
first real regression in ranking, composition or the degradation ladder would
leave all 108 of them green.

So the payloads come from `dev_router`, which runs the real ranking engine, the
real composer and the real §7.1 ladder over the fact fixtures. What is committed
is engine output. `apps/web/tests/today-fixtures.spec.ts` re-validates every
file against the generated schema, so a recording cannot drift into something
the engine would never emit.

**Re-record whenever the engine's output changes** — a template edit, a ranking
change, a new module gate. The diff is the review artefact: if a wording change
alters sixteen files, that is the blast radius, visible before it ships.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "apps" / "web" / "tests" / "__fixtures__" / "today"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sitara_schemas.today import Density  # noqa: E402

from sitara_api.daily_guidance import dev_fixtures  # noqa: E402
from sitara_api.daily_guidance.dev_router import LOCALES, dev_today  # noqa: E402


async def record() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for variant in dev_fixtures.VARIANTS:
        for locale in LOCALES:
            payload = await dev_today(variant=variant, density=Density.MED, locale=locale)
            path = OUT / f"{variant}.{locale}.json"
            path.write_text(
                json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            written += 1

    # The density modes are recorded for ONE variant only. §28.2 is explicit
    # that density "changes ranking-engine output count, never facts", so LOW
    # and HIGH differ from MED by how many cards there are — a property worth
    # one baseline each, not sixteen.
    for density in (Density.LOW, Density.HIGH):
        for locale in LOCALES:
            payload = await dev_today(
                variant="normal_morning", density=density, locale=locale
            )
            path = OUT / f"normal_morning_{density.value}.{locale}.json"
            path.write_text(
                json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            written += 1

    print(f"recorded {written} payloads → {OUT.relative_to(REPO)}")
    return written


if __name__ == "__main__":
    asyncio.run(record())
