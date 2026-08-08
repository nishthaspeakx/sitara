"""memory — the 11 typed facts (§32.4), their embeddings (§32.5) and the vault.

The bounded context §6.3 names "memory (Vector Search retrieval, consent
gates)". `build_memory_service` is the only wiring the app factory needs.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sitara_api.memory.embeddings import (
    CohereEmbedder,
    DeterministicEmbedder,
    Embedder,
    EmbeddingUnavailable,
    EmbedPurpose,
    FallbackEmbedder,
    OpenAIEmbedder,
)
from sitara_api.memory.models import (
    ConsentRecord,
    ConsentRequired,
    MedicalContentDeclined,
    Memory,
    MemoryCandidate,
)
from sitara_api.memory.retrieval import (
    AtlasVectorSearch,
    ExactVectorSearch,
    RetrievalContext,
)
from sitara_api.memory.service import MemoryService
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import MEMORY_TYPE_ORDER, MemoryType

logger = logging.getLogger(__name__)

__all__ = [
    "MEMORY_TYPE_ORDER",
    "ConsentRecord",
    "ConsentRequired",
    "EmbedPurpose",
    "Embedder",
    "EmbeddingUnavailable",
    "MedicalContentDeclined",
    "Memory",
    "MemoryCandidate",
    "MemoryService",
    "MemorySettings",
    "MemoryStore",
    "MemoryType",
    "RetrievalContext",
    "build_memory_service",
]


class MemorySettings(BaseSettings):
    # populate_by_name: a `validation_alias` REPLACES the field name, so
    # `Settings(cohere_api_key=...)` would silently produce None while looking
    # like it worked. Both spellings must bind.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="MEMORY_",
        populate_by_name=True,
    )

    # §32.5 — Cohere primary, OpenAI text-embedding-3-large wired fallback.
    cohere_api_key: str | None = Field(default=None, validation_alias="COHERE_API_KEY")
    cohere_base_url: str = "https://api.cohere.com"
    cohere_model: str = "embed-multilingual-v3.0"

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = "https://api.openai.com"
    openai_model: str = "text-embedding-3-large"

    embed_timeout_seconds: float = 10.0
    top_k: int = 6

    #: Dev convenience: with no provider key, fall back to the deterministic
    #: embedder so the whole feature is exercisable offline. It is NOT
    #: cross-lingual and refuses to be selected outside dev/test.
    allow_deterministic_embedder: bool = True


def build_embedder(settings: MemorySettings, *, environment: str) -> Embedder:
    """§32.5's ladder, or an honest local stand-in."""
    if settings.cohere_api_key or settings.openai_api_key:
        primary: Embedder = CohereEmbedder(
            api_key=settings.cohere_api_key,
            base_url=settings.cohere_base_url,
            model=settings.cohere_model,
            timeout_seconds=settings.embed_timeout_seconds,
        )
        secondary: Embedder | None = (
            OpenAIEmbedder(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
                timeout_seconds=settings.embed_timeout_seconds,
            )
            if settings.openai_api_key
            else None
        )
        return FallbackEmbedder(primary, secondary)

    if environment in ("dev", "test") and settings.allow_deterministic_embedder:
        logger.warning(
            "no embedding provider key — using the deterministic embedder. "
            "It is NOT cross-lingual and must never back a §32.5 recall claim."
        )
        return DeterministicEmbedder()

    raise RuntimeError(
        "no embedding provider configured (§32.5 names Cohere primary, OpenAI fallback) "
        f"and the deterministic stand-in is refused in environment {environment!r}"
    )


async def supports_vector_search(db: Any) -> bool:
    """Does this deployment have Atlas Search? Asked, never assumed.

    `listSearchIndexes` is the cheapest question that distinguishes Atlas from
    the Community mongo §6 gives development.
    """
    try:
        await db.command({"listSearchIndexes": "memories"})
    except Exception:  # noqa: BLE001 — any refusal means "not Atlas"
        return False
    return True


async def build_memory_service(
    *,
    db: Any,
    settings: MemorySettings,
    environment: str,
    embedder: Embedder | None = None,
) -> MemoryService:
    store = MemoryStore(db)
    if await supports_vector_search(db):
        search = AtlasVectorSearch(db)
    else:
        # §6 runs Community mongo in development. Exact cosine over the same
        # vectors ranks identically; what it lacks is the index, which is a
        # scale property rather than a correctness one.
        logger.info("no Atlas Search on this deployment — exact memory search (§32.5)")
        search = ExactVectorSearch(store)  # type: ignore[assignment]

    return MemoryService(
        store=store,
        search=search,
        embedder=embedder or build_embedder(settings, environment=environment),
        top_k=settings.top_k,
    )
