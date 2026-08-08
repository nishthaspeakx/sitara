"""Retrieval ranking, §32.4's visibility gates, and the decay job."""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.memory import decay as decay_job
from sitara_api.memory.models import ConsentRecord, Memory, Visibility, recomputed_decay
from sitara_api.memory.retrieval import (
    RETRIEVAL_FLOOR,
    RetrievalContext,
    SearchHit,
    apply_gates,
    rank,
)
from sitara_api.memory.taxonomy import (
    HALF_LIFE_DAYS,
    NEVER_DECAYS,
    MemoryType,
    decay_score,
)
from tests.memory.conftest import NOW, USER_ID, consent_for


def make_memory(
    memory_type: MemoryType = MemoryType.PERSON,
    *,
    age_days: float = 0.0,
    muted: bool = False,
    content: str = "x",
) -> Memory:
    stamped = NOW - dt.timedelta(days=age_days)
    return Memory(
        memory_id=ObjectId(),
        user_id=USER_ID,
        type=memory_type,
        content=content,
        consent=consent_for(memory_type),
        visibility=Visibility(muted=muted),
        created_at=stamped,
        updated_at=stamped,
    )


class TestDecayPolicy:
    def test_the_spec_fixes_the_ordering_not_the_constants(self) -> None:
        """§32.4: "4,7 decay fastest; 1,3,11 never auto-decay". The half-life
        numbers are engineering defaults; THIS is the spec property."""
        fastest = {MemoryType.PREFERENCE, MemoryType.MOOD_PATTERN}
        decaying = {
            t: half
            for t, half in HALF_LIFE_DAYS.items()
            if half is not None and t not in fastest
        }
        slowest_of_the_fast = max(HALF_LIFE_DAYS[t] or 0 for t in fastest)

        assert all(half > slowest_of_the_fast for half in decaying.values())

    def test_types_1_3_and_11_never_decay(self) -> None:
        assert NEVER_DECAYS == {
            MemoryType.PERSON,
            MemoryType.DATE_ANNIVERSARY,
            MemoryType.PRONUNCIATION_IDENTITY,
        }
        for memory_type in NEVER_DECAYS:
            assert decay_score(memory_type, age_days=10_000) == 1.0

    def test_a_half_life_halves(self) -> None:
        half = HALF_LIFE_DAYS[MemoryType.MOOD_PATTERN]
        assert half is not None
        assert decay_score(MemoryType.MOOD_PATTERN, age_days=half) == pytest.approx(0.5)

    def test_an_edit_makes_a_memory_young_again(self) -> None:
        """Reinforcement: `updated_at` is the stamp decay measures from."""
        stale = make_memory(MemoryType.PREFERENCE, age_days=180)
        refreshed = Memory(**{**stale.__dict__, "updated_at": NOW})

        assert recomputed_decay(stale, NOW) < 0.2
        assert recomputed_decay(refreshed, NOW) == 1.0


class TestRanking:
    def test_similarity_dominates(self) -> None:
        weak = SearchHit(memory=make_memory(content="weak"), similarity=0.10)
        strong = SearchHit(memory=make_memory(content="strong"), similarity=0.90)

        ranked = rank([weak, strong], NOW)

        assert [r.memory.content for r in ranked] == ["strong", "weak"]

    def test_recency_breaks_a_similarity_tie(self) -> None:
        old = SearchHit(
            memory=make_memory(MemoryType.PREFERENCE, age_days=80, content="old"),
            similarity=0.8,
        )
        fresh = SearchHit(
            memory=make_memory(MemoryType.PREFERENCE, age_days=0, content="fresh"),
            similarity=0.8,
        )

        ranked = rank([old, fresh], NOW)

        assert [r.memory.content for r in ranked] == ["fresh", "old"]

    def test_a_decayed_memory_drops_out_of_retrieval(self) -> None:
        """Quiet, not deleted — §32.4 retains until the user deletes."""
        faded = SearchHit(
            memory=make_memory(MemoryType.MOOD_PATTERN, age_days=400), similarity=0.99
        )

        assert rank([faded], NOW) == []
        assert recomputed_decay(faded.memory, NOW) < RETRIEVAL_FLOOR

    def test_a_never_decaying_type_survives_any_age(self) -> None:
        ancient = SearchHit(memory=make_memory(MemoryType.PERSON, age_days=5000), similarity=0.5)

        assert len(rank([ancient], NOW)) == 1


class TestVisibilityGates:
    """§32.4's three rules, each as its own case."""

    def test_types_7_to_9_are_withheld_out_of_context(self) -> None:
        items = rank([SearchHit(memory=make_memory(MemoryType.WORK_FINANCE), similarity=0.9)], NOW)

        allowed, withheld = apply_gates(items, RetrievalContext(topics=frozenset({"festival"})))

        assert allowed == []
        assert withheld == ["work_finance:context_mismatch"]

    def test_types_7_to_9_surface_in_matching_context(self) -> None:
        items = rank([SearchHit(memory=make_memory(MemoryType.WORK_FINANCE), similarity=0.9)], NOW)

        allowed, _ = apply_gates(
            items, RetrievalContext(topics=frozenset({"daily_guidance"}))
        )

        assert len(allowed) == 1

    def test_type_8_never_surfaces_in_a_casual_turn(self) -> None:
        """§32.4: "8 never in celebratory/casual turns" — even when the topic
        would otherwise match."""
        items = rank(
            [SearchHit(memory=make_memory(MemoryType.HEALTH_ADJACENT), similarity=0.99)], NOW
        )

        allowed, withheld = apply_gates(
            items,
            RetrievalContext(topics=frozenset({"emotional_support"}), casual=True),
        )

        assert allowed == []
        assert withheld == ["health_adjacent:casual_turn"]

    def test_type_11_is_always_available(self) -> None:
        """Knowing how to say someone's name is not a disclosure — it holds
        even in a casual turn, an unmatched context and at L2+."""
        items = rank(
            [SearchHit(memory=make_memory(MemoryType.PRONUNCIATION_IDENTITY), similarity=0.4)],
            NOW,
        )

        allowed, _ = apply_gates(
            items, RetrievalContext(casual=True, constrained=True, topics=frozenset())
        )

        assert len(allowed) == 1

    def test_a_constrained_turn_withholds_everything_else(self) -> None:
        """§9: astrology framing is removed at L2+, and a constrained turn is
        not a memory-recall moment either."""
        items = rank([SearchHit(memory=make_memory(MemoryType.PERSON), similarity=0.9)], NOW)

        allowed, withheld = apply_gates(items, RetrievalContext(constrained=True))

        assert allowed == []
        assert withheld == ["person:constrained_turn"]

    def test_a_muted_memory_is_withheld(self) -> None:
        items = rank([SearchHit(memory=make_memory(muted=True), similarity=0.9)], NOW)

        allowed, withheld = apply_gates(items, RetrievalContext())

        assert allowed == []
        assert withheld == ["person:muted_by_user"]

    def test_withholding_is_recorded_not_silent(self) -> None:
        """Diagram 8 has an explicit "withheld this turn" branch; a gate that
        dropped things without saying so could not be audited."""
        items = rank(
            [
                SearchHit(memory=make_memory(MemoryType.PERSON), similarity=0.9),
                SearchHit(memory=make_memory(MemoryType.MOOD_PATTERN), similarity=0.9),
            ],
            NOW,
        )

        allowed, withheld = apply_gates(items, RetrievalContext(topics=frozenset()))

        assert len(allowed) == 1
        assert withheld == ["mood_pattern:context_mismatch"]


class TestDecayJob:
    def test_it_plans_writes_only_where_the_score_moved(self) -> None:
        fresh = make_memory(MemoryType.PREFERENCE, age_days=0)
        aged = make_memory(MemoryType.PREFERENCE, age_days=120)

        updates, report = decay_job.plan([fresh, aged], NOW)

        assert report.scanned == 2
        assert [memory_id for memory_id, _ in updates] == [aged.memory_id]

    def test_it_never_decays_types_1_3_and_11(self) -> None:
        person = make_memory(MemoryType.PERSON, age_days=3000)

        updates, report = decay_job.plan([person], NOW)

        assert updates == []
        assert report.never_decays == 1

    def test_it_heals_a_never_decay_score_that_drifted(self) -> None:
        person = make_memory(MemoryType.PERSON, age_days=10)
        drifted = Memory(**{**person.__dict__, "decay_score": 0.4})

        updates, _ = decay_job.plan([drifted], NOW)

        assert updates == [(drifted.memory_id, 1.0)]

    def test_it_counts_what_fell_below_the_floor_without_deleting(self) -> None:
        """§32.4 retains "until user deletes"; §30.5 makes deletion the user's
        act. A cleanup job that quietly removed memories would be the opposite
        of §0.8's control promise."""
        faded = make_memory(MemoryType.MOOD_PATTERN, age_days=400)

        updates, report = decay_job.plan([faded], NOW)

        assert report.below_floor == 1
        assert updates  # its score is written down…
        # …and nothing in the plan is a deletion: the plan is (id, score) only.
        assert all(isinstance(score, float) for _, score in updates)

    @pytest.mark.asyncio
    async def test_the_job_writes_through_to_mongo(self, db, store) -> None:  # noqa: ANN001
        memory = await store.create(
            user_id=USER_ID,
            memory_type=MemoryType.PREFERENCE,
            content="tea without sugar",
            consent=consent_for(MemoryType.PREFERENCE),
            embedding=None,
            now=NOW - dt.timedelta(days=120),
        )

        report = await decay_job.run(db, now=NOW)

        assert report.updated == 1
        reloaded = await store.get(USER_ID, memory.memory_id)
        assert reloaded is not None and reloaded.decay_score < 0.4

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self, db, store) -> None:  # noqa: ANN001
        memory = await store.create(
            user_id=USER_ID,
            memory_type=MemoryType.PREFERENCE,
            content="x",
            consent=ConsentRecord(granted=True, granted_at=NOW),
            embedding=None,
            now=NOW - dt.timedelta(days=120),
        )

        report = await decay_job.run(db, now=NOW, dry_run=True)

        assert report.updated == 1  # it would have written
        reloaded = await store.get(USER_ID, memory.memory_id)
        assert reloaded is not None and reloaded.decay_score == 1.0  # but did not
