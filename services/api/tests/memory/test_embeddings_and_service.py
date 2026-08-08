"""§32.5's provider ladder, and the retriever the §9 pipeline now uses."""

from __future__ import annotations

import httpx
import pytest

from sitara_api.memory import MemorySettings, build_embedder
from sitara_api.memory.embeddings import (
    EMBEDDING_DIMENSIONS,
    CohereEmbedder,
    DeterministicEmbedder,
    Embedding,
    EmbeddingUnavailable,
    EmbedPurpose,
    FallbackEmbedder,
    OpenAIEmbedder,
    cosine,
)
from sitara_api.memory.retrieval import RetrievalContext
from sitara_api.memory.taxonomy import MemoryType
from tests.memory.conftest import USER_ID, consent_for


class TestEmbeddingContract:
    def test_a_wrong_width_vector_is_refused_at_construction(self) -> None:
        """§6.4's index is 1024-d. A 3072-d vector would fail at insert — in
        an outage, which is the worst time to discover it."""
        with pytest.raises(ValueError, match="1024"):
            Embedding(vector=tuple([0.1] * 3072), model="text-embedding-3-large")

    def test_the_deterministic_embedder_produces_index_width_vectors(self) -> None:
        vector = DeterministicEmbedder().embed_one("Priya is my sister").vector

        assert len(vector) == EMBEDDING_DIMENSIONS
        assert cosine(vector, vector) == pytest.approx(1.0)


class TestProviderRequests:
    """The request shapes, asserted without a network."""

    @pytest.mark.asyncio
    async def test_cohere_sends_the_input_type_that_purpose_names(self, monkeypatch) -> None:  # noqa: ANN001
        """§32.5's asymmetry: a document embedded as a query retrieves worse,
        so the caller states which it is and the adapter must send it."""
        seen: dict = {}

        async def fake_post(self, url, json=None, headers=None):  # noqa: ANN001, ARG001
            seen.update(json or {})
            return httpx.Response(
                200, json={"embeddings": {"float": [[0.1] * EMBEDDING_DIMENSIONS]}}
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        await CohereEmbedder(api_key="k").embed(["kal milte hain"], EmbedPurpose.QUERY)

        assert seen["input_type"] == "search_query"
        assert seen["model"] == "embed-multilingual-v3.0"

    @pytest.mark.asyncio
    async def test_openai_truncates_to_the_index_width(self, monkeypatch) -> None:  # noqa: ANN001
        """text-embedding-3-large is natively 3072-d; §6.4's index is 1024-d,
        so the fallback MUST ask for the truncation."""
        seen: dict = {}

        async def fake_post(self, url, json=None, headers=None):  # noqa: ANN001, ARG001
            seen.update(json or {})
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [0.1] * EMBEDDING_DIMENSIONS}]},
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        await OpenAIEmbedder(api_key="k").embed(["hello"], EmbedPurpose.DOCUMENT)

        assert seen["dimensions"] == EMBEDDING_DIMENSIONS

    @pytest.mark.asyncio
    async def test_a_blank_key_behaves_as_down_not_as_a_crash(self) -> None:
        """§8: the same way a blank panchang key does."""
        with pytest.raises(EmbeddingUnavailable, match="no api key"):
            await CohereEmbedder(api_key=None).embed(["x"], EmbedPurpose.QUERY)


class TestFallbackLadder:
    @pytest.mark.asyncio
    async def test_the_secondary_answers_when_the_primary_is_down(self) -> None:
        class Down:
            model = "down"

            async def embed(self, texts, purpose):  # noqa: ANN001, ARG002
                raise EmbeddingUnavailable("primary")

        ladder = FallbackEmbedder(Down(), DeterministicEmbedder())

        result = await ladder.embed(["x"], EmbedPurpose.DOCUMENT)

        assert result[0].model == DeterministicEmbedder.model

    @pytest.mark.asyncio
    async def test_with_no_secondary_the_failure_surfaces(self) -> None:
        class Down:
            model = "down"

            async def embed(self, texts, purpose):  # noqa: ANN001, ARG002
                raise EmbeddingUnavailable("primary")

        with pytest.raises(EmbeddingUnavailable):
            await FallbackEmbedder(Down()).embed(["x"], EmbedPurpose.DOCUMENT)


class TestEmbedderWiring:
    def test_no_key_in_dev_falls_back_to_the_deterministic_embedder(self) -> None:
        embedder = build_embedder(
            MemorySettings(cohere_api_key=None, openai_api_key=None), environment="dev"
        )

        assert isinstance(embedder, DeterministicEmbedder)

    def test_no_key_in_production_is_refused(self) -> None:
        """The deterministic embedder is not cross-lingual. Serving real users
        with it would quietly break §32.5's whole promise."""
        with pytest.raises(RuntimeError, match="§32.5"):
            build_embedder(
                MemorySettings(cohere_api_key=None, openai_api_key=None),
                environment="production",
            )

    def test_a_key_selects_the_provider_ladder(self) -> None:
        embedder = build_embedder(
            MemorySettings(cohere_api_key="k", openai_api_key="k2"), environment="production"
        )

        assert isinstance(embedder, FallbackEmbedder)
        assert embedder.model == "embed-multilingual-v3.0"


class TestServiceRetrieval:
    @pytest.mark.asyncio
    async def test_a_stored_memory_is_retrievable(self, service) -> None:  # noqa: ANN001
        from sitara_api.memory.models import MemoryCandidate

        await service.accept_chip(
            user_id=USER_ID,
            candidate=MemoryCandidate(
                type=MemoryType.PERSON, content="my sister Priya lives in Bangalore"
            ),
        )

        allowed, _ = await service.recall(
            user_id=USER_ID, query="Priya Bangalore sister", context=RetrievalContext()
        )

        assert [r.memory.content for r in allowed] == ["my sister Priya lives in Bangalore"]

    @pytest.mark.asyncio
    async def test_retrieval_never_crosses_users(self, service, store) -> None:  # noqa: ANN001
        from bson import ObjectId

        other = ObjectId("6a70000000000000000000a2")
        await store.create(
            user_id=other,
            memory_type=MemoryType.PERSON,
            content="someone else's sister Priya",
            consent=consent_for(MemoryType.PERSON),
            embedding=DeterministicEmbedder().embed_one("someone else's sister Priya"),
        )

        allowed, _ = await service.recall(
            user_id=USER_ID, query="sister Priya", context=RetrievalContext()
        )

        assert allowed == []

    @pytest.mark.asyncio
    async def test_an_embedder_outage_degrades_to_no_memory(self, store) -> None:  # noqa: ANN001
        """Memory is context, not correctness (§5.3). Losing it is a worse
        answer, never a failed turn."""
        from sitara_api.memory.retrieval import ExactVectorSearch
        from sitara_api.memory.service import MemoryService

        class Down:
            model = "down"

            async def embed(self, texts, purpose):  # noqa: ANN001, ARG002
                raise EmbeddingUnavailable("down")

        service = MemoryService(store=store, search=ExactVectorSearch(store), embedder=Down())

        allowed, withheld = await service.recall(
            user_id=USER_ID, query="anything", context=RetrievalContext()
        )

        assert allowed == []
        assert withheld == ["embedder_unavailable"]

    @pytest.mark.asyncio
    async def test_an_unembedded_memory_is_stored_and_simply_not_searchable(
        self, store
    ) -> None:  # noqa: ANN001
        """§32.5: embeddings are derived data. The re-embedding batch job picks
        up the null; the memory is never lost in the meantime."""
        from sitara_api.memory.models import MemoryCandidate
        from sitara_api.memory.retrieval import ExactVectorSearch
        from sitara_api.memory.service import MemoryService

        class Down:
            model = "down"

            async def embed(self, texts, purpose):  # noqa: ANN001, ARG002
                raise EmbeddingUnavailable("down")

        service = MemoryService(store=store, search=ExactVectorSearch(store), embedder=Down())
        memory = await service.accept_chip(
            user_id=USER_ID,
            candidate=MemoryCandidate(type=MemoryType.PERSON, content="Priya"),
        )

        assert not memory.has_embedding
        assert len(await store.list_vault(USER_ID)) == 1


class TestPipelineProtocol:
    """P6a's `MemoryRetriever` stub, now satisfied by the real service."""

    @pytest.mark.asyncio
    async def test_the_service_satisfies_the_chat_pipelines_protocol(self, service) -> None:  # noqa: ANN001
        from sitara_api.chat_orchestration.types import MemoryItem
        from sitara_api.memory.models import MemoryCandidate

        await service.accept_chip(
            user_id=USER_ID,
            candidate=MemoryCandidate(type=MemoryType.PERSON, content="Priya is my sister"),
        )

        items = await service.retrieve(
            user_id=str(USER_ID), query="Priya sister", locale="en", top_k=6
        )

        assert items and isinstance(items[0], MemoryItem)
        assert items[0].type is MemoryType.PERSON

    @pytest.mark.asyncio
    async def test_a_non_mongo_user_id_degrades_instead_of_raising(self, service) -> None:  # noqa: ANN001
        """The pipeline calls this on every turn; a bad id must not 500 a
        conversation over missing context."""
        assert await service.retrieve(user_id="not-an-id", query="x", locale="en", top_k=6) == ()
