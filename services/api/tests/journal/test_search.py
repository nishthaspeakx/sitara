"""§30.5's P0 search: keyword + filters over Journal + thread.

Two properties are worth more than the query mechanics:

**There is one backend, and that is recorded rather than hidden.** §30.5 says
"via Atlas Search"; `ExactTextSearch` is what M10 ships, and
`test_search_provenance.py` is the marker saying so. The P0 contract is
deliberately keyword-and-recency rather than relevance-ranked — §30.5 puts
natural-language search in P1 — so an exact scan satisfies it exactly, and
what Atlas would add is an index, which is a scale property.

**Sensitive content is reachable but never suggested.** §30.5: "searching
health-adjacent or safety-flagged content shows results to the user (her data)
but never resurfaces L4 content as casual suggestions." Those are two different
code paths with two different answers over the same row, which is exactly the
kind of rule that rots into one path unless a test holds both.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.journal.models import ArtefactType
from sitara_api.journal.search import (
    ExactTextSearch,
    SearchFilters,
    SearchMode,
)
from sitara_api.journal.store import JournalStore
from tests.journal.conftest import NOW, OTHER_USER_ID, USER_ID

pytestmark = pytest.mark.asyncio


async def _message(
    db,
    *,
    content: str,
    role: str = "assistant",
    risk_class: str | None = None,
    when: dt.datetime = NOW,
    conversation_id: ObjectId | None = None,
) -> ObjectId:
    doc = {
        "_id": ObjectId(),
        "conversation_id": conversation_id or ObjectId(),
        "role": role,
        "type": "text",
        "content": content,
        "locale": "en",
        "fact_ids": [],
        "safety_labels": (
            [{"risk_class": risk_class, "score": 0.9, "source": "classifier"}]
            if risk_class
            else []
        ),
        "transcript_status": "none",
        "playback_policy": "none",
        "created_at": when,
        "updated_at": when,
        "schema_v": 1,
    }
    await db.messages.insert_one(doc)
    return doc["_id"]


async def _conversation(db, user_id: ObjectId = USER_ID) -> ObjectId:
    doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "mode": "text",
        "locale": "en",
        "started_at": NOW,
        "token_stats": {},
        "created_at": NOW,
        "updated_at": NOW,
        "schema_v": 1,
    }
    await db.conversations.insert_one(doc)
    return doc["_id"]


async def _reflection(db, *, date: str, entries: list[str]) -> None:
    await db.night_reflections.insert_one(
        {
            "_id": ObjectId(),
            "user_id": USER_ID,
            "date": date,
            "entries": entries,
            "memory_chips": [],
            "locale": "en",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )


@pytest.fixture()
def search(store: JournalStore, db) -> ExactTextSearch:  # noqa: ANN001
    return ExactTextSearch(db)


# --- keyword ---------------------------------------------------------------


async def test_a_keyword_finds_the_turn_it_appears_in(search: ExactTextSearch, db) -> None:
    conversation_id = await _conversation(db)
    await _message(
        db, content="the lease decision can wait until Thursday", conversation_id=conversation_id
    )
    await _message(
        db, content="your mother's birthday is on Sunday", conversation_id=conversation_id
    )

    hits = await search.run(user_id=USER_ID, query="lease", filters=SearchFilters())

    assert len(hits) == 1
    assert "lease" in hits[0].preview


async def test_search_is_case_insensitive(search: ExactTextSearch, db) -> None:
    conversation_id = await _conversation(db)
    await _message(db, content="Rahu kaal today runs late", conversation_id=conversation_id)

    assert await search.run(user_id=USER_ID, query="RAHU", filters=SearchFilters())


async def test_every_term_must_appear(search: ExactTextSearch, db) -> None:
    """Keyword search, not any-of. Two words narrow; they do not widen."""
    conversation_id = await _conversation(db)
    await _message(db, content="the lease decision can wait", conversation_id=conversation_id)
    await _message(db, content="a decision about the car", conversation_id=conversation_id)

    hits = await search.run(user_id=USER_ID, query="lease decision", filters=SearchFilters())

    assert len(hits) == 1


async def test_search_reaches_reflections_as_well_as_the_thread(
    search: ExactTextSearch, db
) -> None:
    """§30.5 searches "Journal+thread" — one query, both sides."""
    conversation_id = await _conversation(db)
    await _message(db, content="we talked about the move", conversation_id=conversation_id)
    await _reflection(db, date="2026-08-14", entries=["the move is starting to feel real"])

    hits = await search.run(user_id=USER_ID, query="move", filters=SearchFilters())

    assert {h.artefact_type for h in hits} == {ArtefactType.GUIDANCE, ArtefactType.REFLECTION}


async def test_one_users_search_never_reaches_anothers_thread(
    search: ExactTextSearch, db
) -> None:
    other_conversation = await _conversation(db, OTHER_USER_ID)
    await _message(db, content="a private thing", conversation_id=other_conversation)

    assert await search.run(user_id=USER_ID, query="private", filters=SearchFilters()) == []


# --- filters (§30.5: type, date, family member) ----------------------------


async def test_the_type_filter_narrows_to_one_kind(search: ExactTextSearch, db) -> None:
    conversation_id = await _conversation(db)
    await _message(db, content="the move", conversation_id=conversation_id)
    await _reflection(db, date="2026-08-14", entries=["the move"])

    hits = await search.run(
        user_id=USER_ID,
        query="move",
        filters=SearchFilters(types=(ArtefactType.REFLECTION,)),
    )

    assert [h.artefact_type for h in hits] == [ArtefactType.REFLECTION]


async def test_the_date_filter_bounds_the_range(search: ExactTextSearch, db) -> None:
    await _reflection(db, date="2026-08-10", entries=["the move"])
    await _reflection(db, date="2026-08-14", entries=["the move"])

    hits = await search.run(
        user_id=USER_ID,
        query="move",
        filters=SearchFilters(since="2026-08-12", until="2026-08-20"),
    )

    assert [h.local_date for h in hits] == ["2026-08-14"]


async def test_results_are_newest_first(search: ExactTextSearch, db) -> None:
    await _reflection(db, date="2026-08-10", entries=["the move"])
    await _reflection(db, date="2026-08-14", entries=["the move"])

    hits = await search.run(user_id=USER_ID, query="move", filters=SearchFilters())

    assert [h.local_date for h in hits] == ["2026-08-14", "2026-08-10"]


# --- §30.5's sensitive-search honesty --------------------------------------


async def test_an_explicit_search_shows_her_own_safety_flagged_content(
    search: ExactTextSearch, db
) -> None:
    """§30.5: "shows results to the user (her data)". It is hers. Hiding it
    when she went looking would be the app deciding what she may remember."""
    conversation_id = await _conversation(db)
    await _message(
        db,
        content="I could not stop crying about the diagnosis",
        risk_class="emotional_distress",
        conversation_id=conversation_id,
    )

    hits = await search.run(
        user_id=USER_ID, query="crying", filters=SearchFilters(), mode=SearchMode.EXPLICIT
    )

    assert len(hits) == 1


async def test_an_explicit_search_shows_even_l4_content(search: ExactTextSearch, db) -> None:
    conversation_id = await _conversation(db)
    await _message(
        db,
        content="the night everything felt unbearable",
        risk_class="acute_crisis",
        conversation_id=conversation_id,
    )

    hits = await search.run(
        user_id=USER_ID, query="unbearable", filters=SearchFilters(), mode=SearchMode.EXPLICIT
    )

    assert len(hits) == 1, "her own data, when she asked for it"


async def test_suggestions_never_resurface_l4_content(search: ExactTextSearch, db) -> None:
    """The other half of the same sentence: "never resurfaces L4 content as
    casual suggestions". Nobody asked for this one — it would arrive
    unbidden, on an ordinary evening, in a list of things to revisit."""
    conversation_id = await _conversation(db)
    await _message(
        db,
        content="the night everything felt unbearable",
        risk_class="acute_crisis",
        conversation_id=conversation_id,
    )
    await _message(
        db, content="the lease decision can wait", conversation_id=conversation_id
    )

    hits = await search.run(
        user_id=USER_ID, query="the", filters=SearchFilters(), mode=SearchMode.SUGGESTION
    )

    previews = " ".join(h.preview for h in hits)
    assert "unbearable" not in previews
    assert "lease" in previews, "the ordinary turn is still suggested"


async def test_suggestions_do_show_lesser_risk_classes(search: ExactTextSearch, db) -> None:
    """§30.5 names L4 specifically. A distressing evening is not a crisis, and
    treating every label as untouchable would quietly erase most of a life
    from her own journal."""
    conversation_id = await _conversation(db)
    await _message(
        db,
        content="a hard day at the hospital with amma",
        risk_class="emotional_distress",
        conversation_id=conversation_id,
    )

    hits = await search.run(
        user_id=USER_ID, query="amma", filters=SearchFilters(), mode=SearchMode.SUGGESTION
    )

    assert len(hits) == 1


# --- the two backends ------------------------------------------------------


async def test_the_fallback_logs_when_it_truncates(
    search: ExactTextSearch, db, caplog
) -> None:
    """The memory module's rule, applied here: a cap that silently drops
    results reads as "nothing more matched"."""
    conversation_id = await _conversation(db)
    for i in range(5):
        await _message(db, content=f"the move part {i}", conversation_id=conversation_id)

    small = ExactTextSearch(db, scan_limit=2)
    with caplog.at_level("INFO"):
        await small.run(user_id=USER_ID, query="move", filters=SearchFilters())

    assert any("truncat" in record.message.lower() for record in caplog.records)
