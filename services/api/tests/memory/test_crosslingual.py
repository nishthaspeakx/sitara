"""§32.5's cross-lingual recall gate: store in Hindi, retrieve in English.

The honest shape of this test matters more than its result.

§32.5 makes a claim about a PROVIDER — "Cohere embed-multilingual-v3 …
retrieval is cross-lingual by model design", validated at "recall ≥0.85". Only
real vectors from that model can support or refute it. The deterministic
embedder this repo uses everywhere else hashes tokens, so a Hindi document and
an English query share nothing and recall would be ~0.0 — and, worse, a
different toy embedder could be tuned until the number read 0.90 while meaning
nothing at all.

So the gate runs on RECORDED vectors and skips, loudly, when they are absent.
The harness itself is fully tested below against a synthetic embedder with
known behaviour, so what is unproven is the provider's recall and nothing else.
That is the same discipline as the panchang fixtures (§35): the skipping test
is the honest marker.

To record (needs a Cohere key, never in CI):

    COHERE_API_KEY=... uv run python -m tests.memory.crosslingual.record
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sitara_api.memory.embeddings import cosine

PAIRS_PATH = Path(__file__).parent / "crosslingual" / "pairs.json"
VECTORS_PATH = Path(__file__).parent / "crosslingual" / "vectors.json"


def load_pairs() -> dict:
    return json.loads(PAIRS_PATH.read_text(encoding="utf-8"))


def recall_at_k(
    documents: dict[str, list[float]], queries: dict[str, list[float]], k: int
) -> float:
    """Fraction of queries whose own pair is in the top-k nearest documents.

    Deliberately plain: the gate's arithmetic must be obvious enough that a
    reviewer can see it is not flattering itself.
    """
    if not queries:
        return 0.0
    hits = 0
    for pair_id, query_vector in queries.items():
        ranked = sorted(
            documents.items(),
            key=lambda row: cosine(query_vector, row[1]),
            reverse=True,
        )
        if pair_id in [doc_id for doc_id, _ in ranked[:k]]:
            hits += 1
    return hits / len(queries)


# --------------------------------------------------------------------------
# The starter set itself
# --------------------------------------------------------------------------


class TestStarterSet:
    def test_fifty_pairs_across_all_eleven_types(self) -> None:
        data = load_pairs()
        pairs = data["pairs"]

        assert len(pairs) == 50
        assert len({p["id"] for p in pairs}) == 50
        # §32.4's taxonomy is the axis the set is stratified on — a recall
        # number averaged over only chatty types would hide the hard ones.
        assert len({p["type"] for p in pairs}) == 11

    def test_every_pair_is_genuinely_bilingual(self) -> None:
        """A pair whose "Hindi" side is Latin script would make the gate
        measure nothing — it would be English-to-English."""
        for pair in load_pairs()["pairs"]:
            assert any("ऀ" <= ch <= "ॿ" for ch in pair["hi"]), pair["id"]
            assert pair["en"].isascii(), pair["id"]
            assert pair["hi"] != pair["en"]

    def test_the_gate_is_the_one_325_states(self) -> None:
        gate = load_pairs()["gate"]

        assert gate["threshold"] == 0.85
        assert gate["spec_ref"] == "§32.5"


# --------------------------------------------------------------------------
# The harness, proven against known behaviour
# --------------------------------------------------------------------------


class TestHarness:
    """The recall computation is exercised in CI even though the provider
    cannot be. What is unproven is Cohere's recall — not this arithmetic."""

    def test_perfect_alignment_scores_one(self) -> None:
        docs = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        queries = {"a": [1.0, 0.0], "b": [0.0, 1.0]}

        assert recall_at_k(docs, queries, k=1) == 1.0

    def test_inverted_alignment_scores_zero_at_k1(self) -> None:
        docs = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        queries = {"a": [0.0, 1.0], "b": [1.0, 0.0]}

        assert recall_at_k(docs, queries, k=1) == 0.0
        # …and both are found once k covers the whole set, which is the sanity
        # check that the ranking is a ranking and not a coin flip.
        assert recall_at_k(docs, queries, k=2) == 1.0

    def test_partial_alignment_is_a_fraction(self) -> None:
        docs = {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [0.9, 0.1]}
        queries = {"a": [1.0, 0.0], "b": [0.1, 0.9], "c": [0.0, 1.0]}

        assert recall_at_k(docs, queries, k=1) == pytest.approx(2 / 3)

    def test_a_token_hashing_embedder_cannot_pass_this_gate(self) -> None:
        """Why the gate needs real vectors, demonstrated rather than asserted.

        The deterministic embedder shares no tokens between a Hindi document
        and its English query, so recall collapses. Anything that "passed" on
        it would be measuring the test, not the provider.
        """
        from sitara_api.memory.embeddings import DeterministicEmbedder

        embedder = DeterministicEmbedder()
        pairs = load_pairs()["pairs"]
        docs = {p["id"]: list(embedder.embed_one(p["hi"]).vector) for p in pairs}
        queries = {p["id"]: list(embedder.embed_one(p["en"]).vector) for p in pairs}

        assert recall_at_k(docs, queries, k=1) < 0.85


# --------------------------------------------------------------------------
# The gate (§32.5)
# --------------------------------------------------------------------------


class TestCrossLingualRecall:
    @pytest.mark.skipif(
        not VECTORS_PATH.exists(),
        reason=(
            "§32.5 recall gate needs recorded provider vectors — "
            "tests/memory/crosslingual/vectors.json is absent. Record with a "
            "Cohere key via tests.memory.crosslingual.record. UNPROVEN until then: "
            "no cross-lingual recall claim may be made from this suite."
        ),
    )
    def test_hindi_documents_are_found_by_english_queries(self) -> None:
        recorded = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        gate = load_pairs()["gate"]

        # A recording made with the wrong input_type would quietly depress
        # recall and look like a provider failure (§32.5's asymmetry).
        assert recorded["document_input_type"] == "search_document"
        assert recorded["query_input_type"] == "search_query"
        assert recorded["dimensions"] == 1024

        recall = recall_at_k(
            recorded["documents_hi"], recorded["queries_en"], k=gate["recall_at_k"]
        )
        assert recall >= gate["threshold"], (
            f"cross-lingual recall@{gate['recall_at_k']} = {recall:.3f}, "
            f"below §32.5's {gate['threshold']} on {recorded['model']}"
        )

    @pytest.mark.skipif(
        not VECTORS_PATH.exists(), reason="no recorded vectors — see the gate above"
    )
    def test_the_reverse_direction_holds_too(self) -> None:
        """§32.5 says cross-lingual, not Hindi-findable-from-English. A model
        strong in one direction only would still fail a real user."""
        recorded = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        gate = load_pairs()["gate"]

        recall = recall_at_k(
            recorded["documents_en"], recorded["queries_hi"], k=gate["recall_at_k"]
        )
        assert recall >= gate["threshold"]


def test_the_unproven_gate_is_reported_not_hidden() -> None:
    """A skipped gate that nobody sees is a green build lying.

    `release_gates` carries this one, so /shipcheck reports it beside lint and
    tests until the vectors exist.
    """
    from sitara_api.release_gates import gates

    gate = next(g for g in gates() if g.id == "memory.crosslingual_recall")
    assert gate.open is not VECTORS_PATH.exists()
