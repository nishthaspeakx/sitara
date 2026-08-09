"""Diagram 8's nightly consolidation — dedupe and theme extraction (§32.4).

The decay third already had `test_retrieval_and_decay.py`. These are the two
that need the embedding space, and the rule they both bend around is the one
`decay.py` established: **consolidation never deletes**. §32.4 retains a memory
"until user deletes" and §30.5 makes deletion the user's act; a duplicate is a
weaker case for removal than a decayed memory, not a stronger one.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.memory.consolidation import (
    DUPLICATE_THRESHOLD,
    MIN_THEME_SIZE,
    Candidate,
    extract_themes,
    find_duplicates,
    run_consolidation,
    theme_id_for,
)
from sitara_api.memory.embeddings import DeterministicEmbedder
from sitara_api.memory.models import Memory, Visibility
from sitara_api.memory.taxonomy import MemoryType
from tests.memory.conftest import NOW, USER_ID, consent_for

pytestmark = pytest.mark.asyncio()

EMBEDDER = DeterministicEmbedder()


def candidate(
    content: str,
    *,
    memory_type: MemoryType = MemoryType.PREFERENCE,
    created_at: dt.datetime = NOW,
    updated_at: dt.datetime | None = None,
    model: str = EMBEDDER.model,
    memory_id: ObjectId | None = None,
    muted: bool = False,
) -> Candidate:
    memory = Memory(
        memory_id=memory_id or ObjectId(),
        user_id=USER_ID,
        type=memory_type,
        content=content,
        consent=consent_for(memory_type),
        visibility=Visibility(muted=muted),
        created_at=created_at,
        updated_at=updated_at or created_at,
    )
    return Candidate(
        memory=memory, vector=EMBEDDER.embed_one(content).vector, model=model
    )


# --- dedupe ----------------------------------------------------------------


def test_identical_memories_fold_together() -> None:
    a = candidate("she takes filter coffee at six", created_at=NOW)
    b = candidate("she takes filter coffee at six", created_at=NOW + dt.timedelta(days=1))
    (fold,) = find_duplicates([a, b])
    assert fold.similarity >= DUPLICATE_THRESHOLD
    assert {fold.duplicate_id, fold.canonical_id} == {a.memory_id, b.memory_id}


def test_unrelated_memories_never_fold() -> None:
    a = candidate("she takes filter coffee at six")
    b = candidate("the lease decision is due in March")
    assert find_duplicates([a, b]) == []


def test_the_more_recently_reinforced_wording_survives() -> None:
    """§32.4 attaches consent to WORDING. The memory the user last edited or
    re-confirmed is the one they stand behind."""
    old = candidate(
        "she takes filter coffee at six",
        created_at=NOW - dt.timedelta(days=30),
        updated_at=NOW - dt.timedelta(days=30),
    )
    edited = candidate(
        "she takes filter coffee at six",
        created_at=NOW - dt.timedelta(days=10),
        updated_at=NOW,  # reinforced today
    )
    (fold,) = find_duplicates([old, edited])
    assert fold.canonical_id == edited.memory_id
    assert fold.duplicate_id == old.memory_id


def test_memories_of_different_types_never_fold() -> None:
    """§32.4's eleven types carry different consent, gates and decay. Folding
    across them loses whichever set of rules the duplicate was carrying."""
    text = "she fasts on Tuesdays"
    a = candidate(text, memory_type=MemoryType.SPIRITUAL_PRACTICE)
    b = candidate(text, memory_type=MemoryType.PREFERENCE)
    assert find_duplicates([a, b]) == []


def test_vectors_from_two_models_never_fold() -> None:
    """§32.5: cosine across embedding spaces is noise."""
    text = "she takes filter coffee at six"
    a = candidate(text, model="cohere-v3")
    b = candidate(text, model="openai-3-large")
    assert find_duplicates([a, b]) == []


def test_fold_chains_cannot_form() -> None:
    """Every duplicate must point at a memory that is itself live — otherwise
    unmuting one restores a pointer to a pointer."""
    text = "she takes filter coffee at six"
    trio = [candidate(text, created_at=NOW + dt.timedelta(days=i)) for i in range(3)]
    folds = find_duplicates(trio)
    assert len(folds) == 2
    canonicals = {f.canonical_id for f in folds}
    duplicates = {f.duplicate_id for f in folds}
    assert not (canonicals & duplicates), "a canonical was itself folded"


# --- theme extraction ------------------------------------------------------


def test_a_theme_needs_more_than_a_pair() -> None:
    """A cluster of one or two is not a theme; it is a memory. Otherwise
    "themes" becomes a synonym for "memories"."""
    pair = [candidate("the lease renewal"), candidate("the lease renewal terms")]
    assert extract_themes(pair) == []


def test_related_memories_cluster_into_a_theme() -> None:
    related = [
        candidate("the lease renewal is due"),
        candidate("the lease renewal is due next month"),
        candidate("the lease renewal is due in March"),
        candidate("the lease renewal is due soon"),
    ]
    (theme,) = extract_themes(related)
    assert theme.size == len(related)
    assert theme.theme_id.startswith("theme:")


def test_theme_ids_are_stable_across_runs() -> None:
    """Derived from membership so retrieval can boost by theme without every
    nightly run invalidating what the last one learned."""
    ids = [ObjectId() for _ in range(4)]
    assert theme_id_for(ids) == theme_id_for(list(reversed(ids)))
    assert theme_id_for(ids) != theme_id_for(ids[:3])


def test_gated_types_are_themed_only_among_themselves() -> None:
    """§32.4 gates types 7–9 to matching context and type 8 out of casual turns.
    A theme mixing them with ordinary memories would route around those gates
    the moment retrieval boosted by theme."""
    text = "the money worry keeps coming back"
    mixed = [
        candidate(text, memory_type=MemoryType.WORK_FINANCE),
        candidate(text, memory_type=MemoryType.WORK_FINANCE),
        candidate(text, memory_type=MemoryType.WORK_FINANCE),
        candidate(text, memory_type=MemoryType.PREFERENCE),
        candidate(text, memory_type=MemoryType.PREFERENCE),
        candidate(text, memory_type=MemoryType.PREFERENCE),
    ]
    themes = extract_themes(mixed)
    assert len(themes) == 2, "gated and ungated memories must not share a theme"
    for theme in themes:
        member_types = {
            c.memory.type for c in mixed if c.memory_id in theme.member_ids
        }
        assert len(member_types) == 1


def test_themes_never_cross_embedding_spaces() -> None:
    text = "the lease renewal is due"
    mixed = [candidate(text, model="a") for _ in range(3)] + [
        candidate(text, model="b") for _ in range(3)
    ]
    themes = extract_themes(mixed)
    assert len(themes) == 2


# --- the job, end to end ---------------------------------------------------


async def _store(db, service, contents, memory_type=MemoryType.PREFERENCE):  # noqa: ANN001, ANN202
    from sitara_api.memory.models import MemoryCandidate

    out = []
    for content in contents:
        out.append(
            await service.accept_chip(
                user_id=USER_ID,
                candidate=MemoryCandidate(type=memory_type, content=content),
                wording_reconfirmed=True,
                now=NOW,
            )
        )
    return out


async def test_consolidation_folds_without_deleting(db, service) -> None:  # noqa: ANN001
    """The rule the whole module bends around. §32.4 retains "until user
    deletes"; a folded duplicate goes quiet and stays in the vault."""
    text = "she takes filter coffee at six"
    await _store(db, service, [text, text, "the lease decision is due in March"])
    await db.users.insert_one(
        {"_id": USER_ID, "locale": "en", "created_at": NOW, "updated_at": NOW,
         "schema_v": 1, "firebase_uid": "u1", "status": "active"}
    )

    report = await run_consolidation(db, now=NOW)

    assert report.folded == 1
    assert await db.memories.count_documents({}) == 3, "nothing was deleted"
    folded = await db.memories.find_one({"consolidation.duplicate_of": {"$ne": None}})
    assert folded is not None
    assert folded["visibility"]["muted"] is True, "quiet, not gone"
    assert folded["consolidation"]["duplicate_of"] is not None


async def test_a_folded_duplicate_still_appears_in_the_vault(db, service, store) -> None:  # noqa: ANN001
    """§30.5: the vault is "the user's inventory of what Tara knows". A memory
    the system quietly hid from her would be exactly what §0.8 forbids."""
    text = "she takes filter coffee at six"
    await _store(db, service, [text, text])
    await run_consolidation(db, now=NOW)

    vault = await store.list_vault(USER_ID)
    assert len(vault) == 2


async def test_a_muted_memory_is_never_folded_into(db, service, store) -> None:  # noqa: ANN001
    """Unmuting must not restore a memory that quietly became a pointer."""
    text = "she takes filter coffee at six"
    memories = await _store(db, service, [text, text])
    await store.set_muted(user_id=USER_ID, memory_id=memories[0].memory_id, muted=True)

    report = await run_consolidation(db, now=NOW)
    assert report.folded == 0


async def test_consolidation_runs_decay_in_the_same_pass(db, service) -> None:  # noqa: ANN001
    """One nightly scan of `memories`, not three."""
    await _store(db, service, ["a preference that will age"])
    much_later = NOW + dt.timedelta(days=365)
    report = await run_consolidation(db, now=much_later)
    assert report.decay.scanned == 1
    assert report.decay.updated == 1


async def test_a_memory_with_no_vector_is_counted_not_crashed(db) -> None:  # noqa: ANN001
    """§32.5 makes the embedding derived data. A memory without one is still a
    memory; the re-embedding batch job is what fixes it, not this."""
    await db.memories.insert_one(
        {
            "user_id": USER_ID,
            "type": MemoryType.PREFERENCE.value,
            "content": "no vector here",
            "embedding": None,
            "embedding_model": None,
            "consent": consent_for(MemoryType.PREFERENCE).to_doc(),
            "visibility": Visibility().to_doc(),
            "decay_score": 1.0,
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    report = await run_consolidation(db, now=NOW)
    assert report.skipped_no_vector == 1
    assert report.folded == 0


async def test_a_dry_run_writes_nothing(db, service) -> None:  # noqa: ANN001
    text = "she takes filter coffee at six"
    await _store(db, service, [text, text])
    report = await run_consolidation(db, now=NOW, dry_run=True)

    assert report.folded == 1  # it still REPORTS what it would do
    assert await db.memories.count_documents({"visibility.muted": True}) == 0


#: Cosine ~0.857 under the deterministic embedder: above THEME_THRESHOLD,
#: below DUPLICATE_THRESHOLD. Chosen so these cluster WITHOUT folding — three
#: identical strings would be deduped down to one live memory and there would
#: be no theme left to find, which is correct behaviour and a useless fixture.
THEME_BAND = [
    "the lease renewal is due next month",
    "the lease renewal is due next week",
    "the lease renewal is due next year",
]


async def test_themes_are_written_to_their_members(db, service) -> None:  # noqa: ANN001
    contents = THEME_BAND
    await _store(db, service, contents)
    report = await run_consolidation(db, now=NOW)

    assert report.themes == 1
    assert report.themed_memories == MIN_THEME_SIZE
    themed = await db.memories.find({"consolidation.theme_id": {"$ne": None}}).to_list(None)
    assert len(themed) == MIN_THEME_SIZE
    assert len({doc["consolidation"]["theme_id"] for doc in themed}) == 1


async def test_a_theme_is_unlabelled_when_no_model_is_configured(db, service) -> None:  # noqa: ANN001
    """An unlabelled theme is a real theme; an invented label would be a
    summary of the user's life that nobody wrote."""
    await _store(db, service, THEME_BAND)
    report = await run_consolidation(db, now=NOW, labeller=None)

    assert report.themes == 1
    assert report.labelled == 0
    themed = await db.memories.find_one({"consolidation.theme_id": {"$ne": None}})
    assert themed.get("theme_label") is None


async def test_duplicates_are_folded_before_themes_are_extracted(db, service) -> None:  # noqa: ANN001
    """A folded duplicate is out of retrieval, so it must not shape a theme.

    Three copies of one memory are one thing the user told Tara, not a
    recurring theme in her life. Counting them as three would manufacture a
    theme out of a repetition — which is exactly the shape of insight that is
    not insight.
    """
    text = "she takes filter coffee at six"
    await _store(db, service, [text, text, text])
    report = await run_consolidation(db, now=NOW)

    assert report.folded == 2
    assert report.themes == 0


async def test_the_job_is_safe_to_run_twice(db, service) -> None:  # noqa: ANN001
    """§6.1 rejected a workflow engine on the strength of "idempotent tasks",
    and `task_acks_late` means a worker that dies hands the message back."""
    text = "she takes filter coffee at six"
    await _store(db, service, [text, text, "the lease decision is due in March"])

    first = await run_consolidation(db, now=NOW)
    second = await run_consolidation(db, now=NOW)

    assert second.folded <= first.folded
    assert await db.memories.count_documents({}) == 3
    assert await db.memories.count_documents({"visibility.muted": True}) == 1
