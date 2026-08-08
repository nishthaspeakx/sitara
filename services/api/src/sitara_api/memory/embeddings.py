"""Embeddings behind the model-abstraction layer (§32.5).

§32.5: "Cohere embed-multilingual-v3 (1024-d, strong Indic cross-lingual
retrieval) behind the model-abstraction layer … with OpenAI
text-embedding-3-large as the wired fallback."

Three details carry the cross-lingual promise and are easy to lose:

* **Asymmetry.** Cohere's v3 models are trained with distinct input types, and
  a document embedded as a query retrieves measurably worse. `EmbedPurpose`
  makes the caller state which it is; there is no default.
* **Dimensions.** text-embedding-3-large is natively 3072-d and §6.4's index is
  1024-d cosine. The fallback therefore MUST send `dimensions: 1024` — OpenAI
  supports the truncation natively. A fallback that silently returned 3072
  floats would fail at insert, in an outage, which is the worst time to find
  out.
* **Provenance.** A vector is only comparable to vectors from the same model.
  Every embedding records which model produced it, so the §32.5 re-embedding
  batch job can find the ones that need redoing instead of mixing spaces.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

#: §6.4 / §32.5. The index is built at this width; nothing else may be stored.
EMBEDDING_DIMENSIONS = 1024


class EmbedPurpose(StrEnum):
    """Cohere's `input_type`. Stated by the caller, never guessed."""

    DOCUMENT = "search_document"
    QUERY = "search_query"


@dataclass(frozen=True)
class Embedding:
    vector: tuple[float, ...]
    model: str

    def __post_init__(self) -> None:
        if len(self.vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"{self.model} returned {len(self.vector)}-d; §6.4's index is "
                f"{EMBEDDING_DIMENSIONS}-d and will not accept it"
            )


class EmbeddingUnavailable(Exception):
    """Every rung failed. The caller degrades; it does not store a bad vector."""


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    async def embed(
        self, texts: Sequence[str], purpose: EmbedPurpose
    ) -> list[Embedding]: ...


# --------------------------------------------------------------------------
# Cohere — primary (§32.5)
# --------------------------------------------------------------------------


class CohereEmbedder:
    """embed-multilingual-v3.0. Memories embed in their original language and
    retrieval is cross-lingual by model design (§32.5) — there is no
    translation step anywhere in this module, deliberately."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.cohere.com",
        model: str = "embed-multilingual-v3.0",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str], purpose: EmbedPurpose) -> list[Embedding]:
        if not self._api_key:
            # A blank key behaves as "down", the same way a blank panchang key
            # does (§8) — the ladder runs rather than the service crashing.
            raise EmbeddingUnavailable("cohere: no api key")
        payload = {
            "model": self._model,
            "texts": list(texts),
            "input_type": purpose.value,
            "embedding_types": ["float"],
            "truncate": "END",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/embed",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError:
            # §13: log the failure, never the texts — they are memory content.
            logger.warning("cohere embed call failed")
            raise EmbeddingUnavailable("cohere: transport") from None

        if response.status_code != 200:
            logger.warning("cohere embed returned %s", response.status_code)
            raise EmbeddingUnavailable(f"cohere: http {response.status_code}")

        body = response.json()
        vectors = body.get("embeddings", {}).get("float") or body.get("embeddings")
        if not vectors or len(vectors) != len(texts):
            raise EmbeddingUnavailable("cohere: malformed response")
        return [Embedding(vector=tuple(float(x) for x in v), model=self._model) for v in vectors]


# --------------------------------------------------------------------------
# OpenAI — the wired fallback (§32.5)
# --------------------------------------------------------------------------


class OpenAIEmbedder:
    """text-embedding-3-large, truncated to 1024-d at the API.

    §32.5 names this the wired fallback. "Wired" is the operative word: it is
    configured, dimension-matched and exercised by its own test, so the first
    time it runs is not during a Cohere outage.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com",
        model: str = "text-embedding-3-large",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str], purpose: EmbedPurpose) -> list[Embedding]:
        if not self._api_key:
            raise EmbeddingUnavailable("openai: no api key")
        # No input_type: the OpenAI models are symmetric, so `purpose` is
        # recorded for the trace and changes nothing about the request.
        payload = {
            "model": self._model,
            "input": list(texts),
            "dimensions": EMBEDDING_DIMENSIONS,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError:
            logger.warning("openai embed call failed")
            raise EmbeddingUnavailable("openai: transport") from None

        if response.status_code != 200:
            logger.warning("openai embed returned %s", response.status_code)
            raise EmbeddingUnavailable(f"openai: http {response.status_code}")

        data = response.json().get("data")
        if not data or len(data) != len(texts):
            raise EmbeddingUnavailable("openai: malformed response")
        ordered = sorted(data, key=lambda row: row.get("index", 0))
        return [
            Embedding(vector=tuple(float(x) for x in row["embedding"]), model=self._model)
            for row in ordered
        ]


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


class FallbackEmbedder:
    """§32.5's provider ladder behind one interface.

    A fallback embedding is NOT interchangeable with a primary one — different
    models, different vector spaces, cosine between them is noise. So the
    model is stamped on every vector and `retrieval` refuses to compare across
    spaces; the §32.5 re-embedding batch job is what reconciles them.
    """

    def __init__(self, primary: Embedder, secondary: Embedder | None = None) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def model(self) -> str:
        return self._primary.model

    async def embed(self, texts: Sequence[str], purpose: EmbedPurpose) -> list[Embedding]:
        try:
            return await self._primary.embed(texts, purpose)
        except EmbeddingUnavailable:
            if self._secondary is None:
                raise
            logger.warning("primary embedder unavailable — falling back (§32.5)")
            return await self._secondary.embed(texts, purpose)


# --------------------------------------------------------------------------
# Deterministic embedder — dev and tests only
# --------------------------------------------------------------------------


class DeterministicEmbedder:
    """A hash-based embedder for local dev and unit tests.

    It is NOT cross-lingual and makes no pretence of being: it hashes tokens
    into a fixed space, so "Diwali" matches "Diwali" and nothing else. Every
    plumbing test in this module can run on it — storage, gates, decay, vault
    CRUD, the ranking arithmetic — because none of those depend on semantics.

    The one thing it must never be used for is §32.5's recall gate. That gate
    measures the PROVIDER, and measuring it against this would produce a number
    that means nothing while looking like a pass. `test_crosslingual.py` skips
    unless real recorded vectors are present, and says so.
    """

    model = "deterministic-test-embedder-v1"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: Sequence[str], purpose: EmbedPurpose) -> list[Embedding]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> Embedding:
        vector = [0.0] * self._dimensions
        for token in _tokenise(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, 32, 8):
                slot = struct.unpack_from(">Q", digest, offset)[0] % self._dimensions
                vector[slot] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return Embedding(vector=tuple(x / norm for x in vector), model=self.model)


def _tokenise(text: str) -> list[str]:
    return [token for token in text.lower().split() if token]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity. §6.4's index uses cosine; the dev fallback must too,
    or a query would rank differently on a laptop than in production."""
    if len(left) != len(right):
        raise ValueError("cosine over vectors of different width — different models?")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
