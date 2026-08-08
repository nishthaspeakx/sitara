"""The memory module's public face (§6.3: "memory (Vector Search retrieval,
consent gates)").

This is what `chat_orchestration` talks to, and it satisfies P6a's
`MemoryRetriever` protocol so the pipeline's stub is replaced without the
pipeline changing shape.

Retrieval degrades rather than fails. An embedding-provider outage means Tara
answers without remembered context — worse, but honest and still correct, since
memory is context and facts are correctness (§5.3). It never means a 500.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Any

from bson import ObjectId

from sitara_api.memory.embeddings import (
    Embedder,
    EmbeddingUnavailable,
    EmbedPurpose,
)
from sitara_api.memory.models import (
    ConsentAction,
    ConsentEvent,
    ConsentRecord,
    Memory,
    MemoryCandidate,
    Retrieved,
)
from sitara_api.memory.retrieval import (
    RetrievalContext,
    VectorSearch,
    apply_gates,
    rank,
)
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import RECONFIRM_WORDING, MemoryType

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        *,
        store: MemoryStore,
        search: VectorSearch,
        embedder: Embedder,
        top_k: int = 6,
    ) -> None:
        self._store = store
        self._search = search
        self._embedder = embedder
        self._top_k = top_k

    # -- write -------------------------------------------------------------

    async def accept_chip(
        self,
        *,
        user_id: ObjectId,
        candidate: MemoryCandidate,
        wording_reconfirmed: bool = False,
        now: dt.datetime | None = None,
    ) -> Memory:
        """The user tapped the chip. §32.4's only path into the collection.

        Types 7–9 arrive with `wording_reconfirmed=True` or the store refuses
        them — the check lives there so no caller can route around it.
        """
        moment = now or dt.datetime.now(dt.UTC)
        consent = ConsentRecord(
            granted=True,
            granted_at=moment,
            wording_reconfirmed=(
                wording_reconfirmed or candidate.type not in RECONFIRM_WORDING
            ),
            history=(
                ConsentEvent(
                    action=(
                        ConsentAction.RECONFIRMED
                        if candidate.type in RECONFIRM_WORDING
                        else ConsentAction.GRANTED
                    ),
                    at=moment,
                    wording=candidate.content,
                ),
            ),
        )
        # §32.5: memories embed in their ORIGINAL language — no translation
        # anywhere. Cross-lingual retrieval is the model's job, by design.
        embedding = None
        try:
            embedding = (
                await self._embedder.embed([candidate.content], EmbedPurpose.DOCUMENT)
            )[0]
        except EmbeddingUnavailable:
            # Store it anyway: consent was given, and the memory is the source
            # of truth while the embedding is derived data (§32.5). The
            # re-embedding batch job picks up the null.
            logger.warning("embedding unavailable — storing memory unembedded (§32.5)")

        return await self._store.create(
            user_id=user_id,
            memory_type=candidate.type,
            content=candidate.content,
            consent=consent,
            embedding=embedding,
            source_message_id=candidate.source_message_id,
            now=moment,
        )

    # -- read --------------------------------------------------------------

    async def recall(
        self,
        *,
        user_id: ObjectId,
        query: str,
        context: RetrievalContext,
        top_k: int | None = None,
        now: dt.datetime | None = None,
    ) -> tuple[list[Retrieved], list[str]]:
        """Diagram 8's retrieval path. Returns (allowed, withheld reasons)."""
        moment = now or dt.datetime.now(dt.UTC)
        try:
            embedded = (await self._embedder.embed([query], EmbedPurpose.QUERY))[0]
        except EmbeddingUnavailable:
            logger.warning("embedding unavailable — answering without memory")
            return [], ["embedder_unavailable"]

        hits = await self._search.search(
            user_id=user_id, query=embedded, top_k=(top_k or self._top_k)
        )
        return apply_gates(rank(hits, moment), context)

    # -- the P6a protocol --------------------------------------------------

    async def retrieve(
        self, *, user_id: str, query: str, locale: str, top_k: int
    ) -> Sequence[Any]:
        """`chat_orchestration.memory.MemoryRetriever`, satisfied.

        The pipeline applies its own §32.4 gates over whatever comes back —
        deliberately, since it knows the intent and the safety level and this
        method does not. The gates therefore run twice on a chat turn, which is
        the cheap direction to be wrong in.
        """
        from sitara_api.chat_orchestration.types import MemoryItem

        try:
            oid = ObjectId(user_id)
        except Exception:  # noqa: BLE001 — a bad id is not a 500 on this path
            logger.warning("memory recall skipped: user id is not a Mongo _id")
            return ()

        allowed, _ = await self.recall(
            user_id=oid, query=query, context=RetrievalContext(), top_k=top_k
        )
        return [
            MemoryItem(
                memory_id=item.memory_id,
                type=item.memory.type,
                content=item.memory.content,
                score=item.score,
            )
            for item in allowed
        ]

    # -- vault -------------------------------------------------------------

    async def vault(
        self, user_id: ObjectId, *, types: Sequence[MemoryType] | None = None
    ) -> list[Memory]:
        return await self._store.list_vault(user_id, types=types)

    async def edit(
        self, *, user_id: ObjectId, memory_id: ObjectId, content: str
    ) -> Memory | None:
        embedding = None
        try:
            embedding = (await self._embedder.embed([content], EmbedPurpose.DOCUMENT))[0]
        except EmbeddingUnavailable:
            logger.warning("embedding unavailable — memory edited without re-embedding")
        return await self._store.edit(
            user_id=user_id, memory_id=memory_id, content=content, embedding=embedding
        )

    async def forget(self, *, user_id: ObjectId, memory_id: ObjectId) -> bool:
        """Hard delete + embedding removed (diagram 8)."""
        return await self._store.delete(user_id=user_id, memory_id=memory_id)

    async def mute(self, *, user_id: ObjectId, memory_id: ObjectId, muted: bool) -> Memory | None:
        return await self._store.set_muted(user_id=user_id, memory_id=memory_id, muted=muted)

    # -- §30.5 scoped deletion --------------------------------------------

    async def on_journal_entry_deleted(
        self, *, user_id: ObjectId, message_ids: Sequence[ObjectId], delete_memories: bool
    ) -> int:
        """"memories sourced from it survive unless also deleted — offered as
        a checkbox" (§30.5). `delete_memories` IS the checkbox."""
        if delete_memories:
            return await self._store.delete_sourced_from_messages(
                user_id=user_id, message_ids=message_ids
            )
        return 0

    async def on_conversation_deleted(
        self, *, user_id: ObjectId, message_ids: Sequence[ObjectId]
    ) -> int:
        """"dependent memory sources marked 'source removed'" (§30.5).

        The memory survives: consent was given to Tara knowing it, and that
        consent did not expire with the thread it came from.
        """
        return await self._store.mark_source_removed(
            user_id=user_id, message_ids=message_ids
        )
