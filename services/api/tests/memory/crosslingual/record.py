"""Record real provider vectors for §32.5's recall gate.

Run once, with a key, by a human. Never in CI — `test_no_live_network`-style
discipline applies: the suite must not depend on a paid vendor's uptime.

    COHERE_API_KEY=... uv run python -m tests.memory.crosslingual.record

It writes `vectors.json`, which flips `memory.crosslingual_recall` closed in
release_gates and un-skips the gate. The recording stamps the model, the
dimensions and BOTH input types, because a recording made with the wrong
`input_type` depresses recall in a way that looks like a provider failure
(§32.5's asymmetry) and would send someone hunting the wrong bug.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sitara_api.memory.embeddings import (
    EMBEDDING_DIMENSIONS,
    CohereEmbedder,
    EmbedPurpose,
)

HERE = Path(__file__).parent
PAIRS = HERE / "pairs.json"
OUT = HERE / "vectors.json"


async def main() -> int:
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        print("COHERE_API_KEY is not set — nothing recorded.", file=sys.stderr)
        return 1

    data = json.loads(PAIRS.read_text(encoding="utf-8"))
    pairs = data["pairs"]
    embedder = CohereEmbedder(api_key=key)

    async def embed(texts: list[str], purpose: EmbedPurpose) -> list[list[float]]:
        out: list[list[float]] = []
        # Batch politely; the vendor's per-call cap is well above 50 but the
        # recorder should not be the thing that discovers a new one.
        for start in range(0, len(texts), 32):
            chunk = texts[start : start + 32]
            out.extend(list(e.vector) for e in await embedder.embed(chunk, purpose))
        return out

    ids = [p["id"] for p in pairs]
    hi = [p["hi"] for p in pairs]
    en = [p["en"] for p in pairs]

    # Both directions, both input types — §32.5 says cross-lingual, and a
    # model strong in one direction only would still fail a real user.
    documents_hi = await embed(hi, EmbedPurpose.DOCUMENT)
    queries_en = await embed(en, EmbedPurpose.QUERY)
    documents_en = await embed(en, EmbedPurpose.DOCUMENT)
    queries_hi = await embed(hi, EmbedPurpose.QUERY)

    OUT.write_text(
        json.dumps(
            {
                "$comment": (
                    "Recorded from the live provider for §32.5's recall gate. "
                    "Regenerate on any model change — vectors from two models "
                    "live in different spaces and must never be mixed."
                ),
                "model": embedder.model,
                "dimensions": EMBEDDING_DIMENSIONS,
                "document_input_type": EmbedPurpose.DOCUMENT.value,
                "query_input_type": EmbedPurpose.QUERY.value,
                "documents_hi": dict(zip(ids, documents_hi, strict=True)),
                "queries_en": dict(zip(ids, queries_en, strict=True)),
                "documents_en": dict(zip(ids, documents_en, strict=True)),
                "queries_hi": dict(zip(ids, queries_hi, strict=True)),
            }
        ),
        encoding="utf-8",
    )
    print(f"recorded {len(ids)} pairs → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
