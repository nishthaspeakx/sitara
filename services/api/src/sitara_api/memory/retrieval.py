"""Retrieval: vector top-k + recency + decay + type filter, then the gates.

Diagram 8's retrieval step, in order: "vector top-k (cosine) + recency boost +
type filter + decay score" → visibility gate → injected with a memory-ID
citation, or withheld this turn.

Two backends, one ranking. Atlas runs `$vectorSearch`; Community mongo — what
§6 gives development — cannot, so an exact cosine scan stands in. The scan is
not a toy: it computes the same cosine over the same vectors and feeds the same
ranking, so a query ranks identically on a laptop and in production. What it
lacks is the index, which is a scale property, not a correctness one. It is
capped and logs when it truncates rather than silently searching less.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from bson import ObjectId

from sitara_api.memory.embeddings import Embedding, cosine
from sitara_api.memory.models import Memory, Retrieved, recomputed_decay
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import (
    ALWAYS_AVAILABLE,
    CONTEXT_GATED,
    NEVER_IN_CASUAL,
    RETRIEVAL_FLOOR,
    MemoryType,
)

logger = logging.getLogger(__name__)

#: Ranking weights. Similarity dominates; recency and decay adjust. Tunable,
#: and the properties that matter are asserted as behaviour rather than pinned
#: to these numbers.
W_SIMILARITY = 0.70
W_DECAY = 0.20
W_RECENCY = 0.10

#: A memory stops earning a recency boost after this long. Beyond it, decay is
#: the only thing still moving.
RECENCY_HORIZON_DAYS = 90.0

#: The dev fallback scans; this bounds what it will scan before it says so.
EXACT_SEARCH_CAP = 500


@dataclass(frozen=True)
class SearchHit:
    memory: Memory
    similarity: float


class VectorSearch(Protocol):
    async def search(
        self,
        *,
        user_id: ObjectId,
        query: Embedding,
        top_k: int,
        types: Sequence[MemoryType] | None = None,
    ) -> list[SearchHit]: ...


class AtlasVectorSearch:
    """§6.4's `memories_vector` index, 1024-d cosine, filtered by user."""

    def __init__(self, db: Any, index_name: str = "memories_vector") -> None:
        self._db = db
        self._index = index_name

    async def search(
        self,
        *,
        user_id: ObjectId,
        query: Embedding,
        top_k: int,
        types: Sequence[MemoryType] | None = None,
    ) -> list[SearchHit]:
        # The user filter is part of the INDEX definition (§6.4 filters), not a
        # post-filter: a $vectorSearch that ranked across users first and
        # filtered after would leak one person's neighbours into another's
        # candidate set and waste the k budget.
        criteria: dict[str, Any] = {"user_id": user_id}
        if types:
            criteria["type"] = {"$in": [t.value for t in types]}

        pipeline = [
            {
                "$vectorSearch": {
                    "index": self._index,
                    "path": "embedding",
                    "queryVector": list(query.vector),
                    "numCandidates": max(top_k * 20, 100),
                    "limit": top_k,
                    "filter": criteria,
                }
            },
            {"$addFields": {"_similarity": {"$meta": "vectorSearchScore"}}},
        ]
        hits: list[SearchHit] = []
        async for doc in await self._db.memories.aggregate(pipeline):
            if doc.get("embedding_model") not in (None, query.model):
                # §32.5: vectors from a different model live in a different
                # space. Comparing them is noise; the re-embedding batch job
                # is what reconciles them.
                continue
            hits.append(SearchHit(memory=Memory.from_doc(doc), similarity=doc["_similarity"]))
        return hits


class ExactVectorSearch:
    """Dev/Community fallback: the same cosine, computed in Python."""

    def __init__(self, store: MemoryStore, cap: int = EXACT_SEARCH_CAP) -> None:
        self._store = store
        self._cap = cap

    async def search(
        self,
        *,
        user_id: ObjectId,
        query: Embedding,
        top_k: int,
        types: Sequence[MemoryType] | None = None,
    ) -> list[SearchHit]:
        rows = await self._store.candidates_for_search(user_id, limit=self._cap)
        if len(rows) >= self._cap:
            # Never a silent cap (§9's no-silent-truncation habit).
            logger.warning(
                "exact memory search hit its %s-row cap — results are partial", self._cap
            )
        wanted = {t for t in types} if types else None

        hits: list[SearchHit] = []
        for memory, vector, model in rows:
            if vector is None or (model is not None and model != query.model):
                continue
            if wanted is not None and memory.type not in wanted:
                continue
            hits.append(SearchHit(memory=memory, similarity=cosine(query.vector, vector)))
        hits.sort(key=lambda hit: hit.similarity, reverse=True)
        return hits[:top_k]


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def rank(hits: Sequence[SearchHit], now: dt.datetime) -> list[Retrieved]:
    """Similarity + recency boost + decay (diagram 8), floor applied.

    Decay is recomputed here rather than read from the stored `decay_score`:
    the nightly job writes that value, and retrieval must be right about a
    memory that aged since the job last ran.
    """
    ranked: list[Retrieved] = []
    for hit in hits:
        decay = recomputed_decay(hit.memory, now)
        if decay < RETRIEVAL_FLOOR:
            # Quiet, not deleted — §32.4 retains until the user deletes, and
            # the vault still shows it.
            continue
        recency = _recency(hit.memory, now)
        score = W_SIMILARITY * hit.similarity + W_DECAY * decay + W_RECENCY * recency
        ranked.append(Retrieved(memory=hit.memory, similarity=hit.similarity, score=score))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _recency(memory: Memory, now: dt.datetime) -> float:
    stamped = memory.updated_at or memory.created_at
    if stamped is None:
        return 0.0
    days = max(0.0, (now - stamped).total_seconds() / 86400.0)
    return max(0.0, 1.0 - days / RECENCY_HORIZON_DAYS)


# --------------------------------------------------------------------------
# Visibility gates (§32.4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalContext:
    """What the gates need to know about the turn asking for memories."""

    #: Classifier-tagged conversational context — §32.4's own wording for what
    #: opens types 7–9.
    topics: frozenset[str] = frozenset()
    casual: bool = False
    #: L2+ (§9). A constrained turn is not a memory-recall moment.
    constrained: bool = False


#: Which classifier topics open each context-gated type (§32.4: "retrieved
#: only in matching conversational context (classifier-tagged)").
GATED_TOPICS: dict[MemoryType, frozenset[str]] = {
    MemoryType.MOOD_PATTERN: frozenset({"emotional_support", "daily_guidance", "reflection"}),
    MemoryType.HEALTH_ADJACENT: frozenset({"emotional_support", "health_adjacent"}),
    MemoryType.WORK_FINANCE: frozenset(
        {"daily_guidance", "timing_question", "natal_chart_question", "work", "finance"}
    ),
}


def apply_gates(
    items: Sequence[Retrieved], context: RetrievalContext
) -> tuple[list[Retrieved], list[str]]:
    """§32.4's gates. Returns (allowed, withheld reasons) — diagram 8's
    "injected" and "withheld this turn" branches, both recorded."""
    allowed: list[Retrieved] = []
    withheld: list[str] = []

    for item in items:
        memory_type = item.memory.type
        always = memory_type in ALWAYS_AVAILABLE

        if item.memory.visibility.muted:
            withheld.append(f"{memory_type.value}:muted_by_user")
            continue
        # Type 11 is "always available" — including at L2+, because knowing how
        # to say someone's name is not astrology and not a personal disclosure.
        if always:
            allowed.append(item)
            continue
        if context.constrained:
            withheld.append(f"{memory_type.value}:constrained_turn")
            continue
        if memory_type in NEVER_IN_CASUAL and context.casual:
            withheld.append(f"{memory_type.value}:casual_turn")
            continue
        if memory_type in CONTEXT_GATED:
            if not (context.topics & GATED_TOPICS.get(memory_type, frozenset())):
                withheld.append(f"{memory_type.value}:context_mismatch")
                continue
        allowed.append(item)

    return allowed, withheld
