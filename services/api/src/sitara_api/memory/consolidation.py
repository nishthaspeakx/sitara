"""Nightly consolidation — diagram 8's last box, completed (§32.4, §32.5).

    "Nightly consolidation: dedupe · decay stale · theme extraction"

M5-P6b shipped the middle third: `decay.py`, arithmetic on a clock, needing
neither the embedding space nor a model. This module is the other two, which do
need the embedding space, and it runs all three together — one nightly scan of
`memories` rather than three.

**Dedupe does not delete.** This is the decision worth arguing with, because
"dedupe" sounds like removal. §32.4 retains memories "until user deletes" and
§30.5 makes deletion the user's act; `decay.py` already refuses to delete for
exactly this reason, and a duplicate is a weaker case for deletion than a
decayed memory, not a stronger one — the user consented to each of them
separately. So a duplicate is FOLDED: it stops being retrieved, it keeps its
row, the vault keeps showing it, and it points at the memory it was folded
into. The user can still see and delete it; Tara simply stops saying the same
thing twice.

Which of a pair survives is decided by reinforcement, not recency: the memory
the user has touched most recently (`updated_at`) is the wording they last
confirmed, and consent attaches to wording (§32.4's re-confirm rule for types
7–9 is the same principle).

**Theme extraction produces a cluster, and a label only if it can.** Clustering
is deterministic — single-link agglomeration on cosine over ONE embedding
space, which is the only comparison §32.5 permits. The label is a natural
language summary of memory content, so it is written to `theme_label`, which is
a top-level CSFLE field under the `memory` key class; the explicit codec reaches
top-level paths and not nested ones (§36.3), which is precisely why the label
does not live inside the `consolidation` object with the rest of the cluster
metadata. Where no model is configured the cluster still forms and the label
stays null — an unlabelled theme is a real theme, and an invented label would
be a summary of the user's life that nobody wrote.

**Vectors from two models never mix** (§32.5). Clustering partitions by
`embedding_model` before it does anything else. Cosine across spaces is noise,
and noise that clusters looks exactly like insight.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from bson import ObjectId

from sitara_api.memory.decay import DecayReport
from sitara_api.memory.decay import plan as plan_decay
from sitara_api.memory.embeddings import cosine
from sitara_api.memory.models import Memory
from sitara_api.memory.taxonomy import MemoryType

logger = logging.getLogger(__name__)

#: Cosine at or above this and two memories of the same type are saying the
#: same thing. Deliberately high: folding two memories that merely rhyme costs
#: the user something Tara promised to remember, and the failure is silent.
#: Tunable from the admin console like the decay half-lives; the ORDERING
#: constraints in §32.4 are spec, these constants are engineering.
DUPLICATE_THRESHOLD = 0.93

#: Cosine at or above this and two memories belong to one theme. Lower than the
#: duplicate bar by design — a theme is a neighbourhood, not a repetition.
THEME_THRESHOLD = 0.72

#: A cluster of one is not a theme; it is a memory. Below this the memory is
#: left unthemed rather than given a theme of its own, which would make
#: "themes" a synonym for "memories" in every vault with no repetition in it.
MIN_THEME_SIZE = 3

#: §32.4 gates types 7–9 to matching conversational context and type 8 out of
#: casual turns entirely. A theme that mixed a health-adjacent memory in with
#: ordinary ones would route around those gates the moment retrieval boosted by
#: theme, so the gated types are themed only among themselves.
_GATED = frozenset({MemoryType.MOOD_PATTERN, MemoryType.HEALTH_ADJACENT, MemoryType.WORK_FINANCE})


@dataclass(frozen=True)
class Candidate:
    """One memory with the vector and space it lives in."""

    memory: Memory
    vector: tuple[float, ...]
    model: str

    @property
    def memory_id(self) -> ObjectId:
        return self.memory.memory_id


@dataclass(frozen=True)
class Fold:
    """A duplicate and the memory it folds into."""

    duplicate_id: ObjectId
    canonical_id: ObjectId
    similarity: float


@dataclass(frozen=True)
class Theme:
    theme_id: str
    member_ids: tuple[ObjectId, ...]
    label: str | None = None

    @property
    def size(self) -> int:
        return len(self.member_ids)


@dataclass(frozen=True)
class ConsolidationReport:
    users: int = 0
    scanned: int = 0
    decay: DecayReport = field(default_factory=DecayReport)
    folded: int = 0
    themes: int = 0
    themed_memories: int = 0
    labelled: int = 0
    skipped_no_vector: int = 0

    def summary(self) -> str:
        return (
            f"users={self.users} scanned={self.scanned} "
            f"decay[{self.decay.summary()}] folded={self.folded} "
            f"themes={self.themes} themed={self.themed_memories} "
            f"labelled={self.labelled} no_vector={self.skipped_no_vector}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "users": self.users,
            "scanned": self.scanned,
            "decay_updated": self.decay.updated,
            "folded": self.folded,
            "themes": self.themes,
            "themed_memories": self.themed_memories,
            "labelled": self.labelled,
        }


# ---------------------------------------------------------------------------
# Dedupe (pure)
# ---------------------------------------------------------------------------


def find_duplicates(
    candidates: Sequence[Candidate], *, threshold: float = DUPLICATE_THRESHOLD
) -> list[Fold]:
    """Fold near-identical memories of the SAME TYPE within one vector space.

    Same type is a real constraint, not a shortcut. §32.4's eleven types carry
    different consent, gates and decay; a `person` memory and a `preference`
    memory that happen to embed close together are two different kinds of thing
    about one person, and folding them would lose whichever set of rules the
    duplicate was carrying.

    **The canonical is chosen per GROUP, not per pair.** Pairwise folding looks
    correct and is not: with three copies A, B, C, the pass that folds A into B
    will later fold B into C, and A is left pointing at a memory that is itself
    a pointer. Unmuting one duplicate then restores a memory that resolves to
    another duplicate — a chain nobody designed and nothing detects.

    So duplicates are clustered first (single-link, same rule as themes but at
    a much higher threshold), one canonical is elected for the whole cluster,
    and every other member folds directly into it. Every duplicate therefore
    points at a memory that is live, by construction rather than by care.
    """
    folds: list[Fold] = []

    groups: dict[tuple[str, MemoryType], list[Candidate]] = {}
    for candidate in candidates:
        groups.setdefault((candidate.model, candidate.memory.type), []).append(candidate)

    for group in groups.values():
        for cluster in _single_link(group, threshold):
            if len(cluster) < 2:
                continue
            canonical = _most_reinforced(cluster)
            for member in cluster:
                if member.memory_id == canonical.memory_id:
                    continue
                folds.append(
                    Fold(
                        duplicate_id=member.memory_id,
                        canonical_id=canonical.memory_id,
                        similarity=cosine(member.vector, canonical.vector),
                    )
                )

    return folds


def _most_reinforced(cluster: Sequence[Candidate]) -> Candidate:
    """The cluster's canonical: the wording the user last stood behind.

    `updated_at` is the reinforcement stamp the module already treats as
    authoritative (`models.recomputed_decay` reads it the same way) — an edited
    or re-confirmed memory is current again. The id tie-break keeps the choice
    deterministic, so two nightly runs over an unchanged vault agree.
    """
    return max(
        cluster,
        key=lambda c: (
            c.memory.updated_at or c.memory.created_at or dt.datetime.min,
            str(c.memory_id),
        ),
    )


# ---------------------------------------------------------------------------
# Theme extraction (pure)
# ---------------------------------------------------------------------------


def extract_themes(
    candidates: Sequence[Candidate],
    *,
    threshold: float = THEME_THRESHOLD,
    min_size: int = MIN_THEME_SIZE,
) -> list[Theme]:
    """Single-link agglomeration on cosine, within one embedding space.

    Single-link rather than centroid: a theme in someone's memory vault is a
    chain of related things ("the lease", "the landlord", "moving in March"),
    not a tight ball around an average, and centroid clustering would split
    exactly the chains worth surfacing.

    §32.4's gated types (7–9) cluster only among themselves — see `_GATED`.
    """
    themes: list[Theme] = []
    for group in _partitions(candidates):
        for cluster in _single_link(group, threshold):
            if len(cluster) < min_size:
                continue
            member_ids = tuple(sorted((c.memory_id for c in cluster), key=str))
            themes.append(Theme(theme_id=theme_id_for(member_ids), member_ids=member_ids))
    return themes


def _partitions(candidates: Sequence[Candidate]) -> list[list[Candidate]]:
    """Split by embedding space, and gated types away from ungated ones."""
    buckets: dict[tuple[str, bool], list[Candidate]] = {}
    for candidate in candidates:
        key = (candidate.model, candidate.memory.type in _GATED)
        buckets.setdefault(key, []).append(candidate)
    return list(buckets.values())


def _single_link(group: Sequence[Candidate], threshold: float) -> list[list[Candidate]]:
    """Union-find over pairs above threshold. O(n²) in one user's memories,
    which is a few hundred at the outside — the vault is not a message log."""
    parent = {candidate.memory_id: candidate.memory_id for candidate in group}

    def find(node: ObjectId) -> ObjectId:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: ObjectId, b: ObjectId) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for i, left in enumerate(group):
        for right in group[i + 1 :]:
            if cosine(left.vector, right.vector) >= threshold:
                union(left.memory_id, right.memory_id)

    clusters: dict[ObjectId, list[Candidate]] = {}
    for candidate in group:
        clusters.setdefault(find(candidate.memory_id), []).append(candidate)
    return list(clusters.values())


def theme_id_for(member_ids: Sequence[ObjectId]) -> str:
    """A stable id derived from membership.

    Derived rather than random so that a theme whose membership did not change
    keeps its id across nightly runs — retrieval can then boost by theme
    without every run invalidating what the last one learned. Change the
    membership and it is a different theme, which is the honest answer.
    """
    digest = hashlib.blake2b(
        ":".join(sorted(str(m) for m in member_ids)).encode("utf-8"), digest_size=8
    ).hexdigest()
    return f"theme:{digest}"


# ---------------------------------------------------------------------------
# Labelling (needs a model — optional by design)
# ---------------------------------------------------------------------------


class ThemeLabeller:
    """Names a cluster, or declines.

    Runs on §9's CLASSIFICATION tier — this is exactly the "classification/
    ranking polish" work §9 routes to Haiku-class, and it is not guidance, so
    no fact tool and no grounding validator is involved. What it must not do is
    invent: the prompt asks for a label DRAWN FROM the memories given, and a
    failure returns None rather than a guess.
    """

    def __init__(self, llm, *, settings=None) -> None:  # noqa: ANN001
        from sitara_api.chat_orchestration.config import ChatSettings

        self._llm = llm
        self._settings = settings or ChatSettings()

    async def label(self, contents: Sequence[str], locale: str) -> str | None:
        from sitara_api.chat_orchestration.llm import (
            LLMRequest,
            LLMTask,
            LLMUnavailable,
        )

        if not contents:
            return None
        request = LLMRequest(
            task=LLMTask.CLASSIFICATION,
            system=(
                "You name groups of personal notes. Reply with a short noun "
                "phrase of at most four words, in the user's own language, "
                "drawn only from what the notes say. Never add a detail the "
                "notes do not contain. Never judge, diagnose or advise.",
            ),
            messages=(
                {
                    "role": "user",
                    "content": "\n".join(f"- {c}" for c in contents[:12]),
                },
            ),
            temperature=self._settings.temperature_classification,
            max_tokens=32,
            schema={
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
                "additionalProperties": False,
            },
            label="memory.theme_label",
        )
        try:
            response = await self._llm.complete(request)
        except LLMUnavailable:
            logger.info("theme labelling unavailable — themes stay unlabelled")
            return None
        text = ((response.parsed or {}).get("label") or "").strip()
        return text or None


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


async def run_consolidation(
    db,  # noqa: ANN001
    *,
    now: dt.datetime | None = None,
    dry_run: bool = False,
    labeller: ThemeLabeller | None = None,
) -> ConsolidationReport:
    """All three thirds of diagram 8's nightly box, per user.

    Per user because every comparison in here is within one person's memories:
    §6.4 shards `memories` by `hashed(user_id)`, §32.5's vector index filters on
    it, and a cosine between two people's memories is not a number anyone should
    ever compute.
    """
    moment = now or dt.datetime.now(dt.UTC)
    user_ids = await db.memories.distinct("user_id")

    decay_updates: list[tuple[ObjectId, float]] = []
    folds: list[Fold] = []
    #: (theme, locale, member contents) — the contents travel WITH the theme
    #: because labelling happens after every user has been scanned, and a
    #: per-user lookup table would by then hold only the last user's memories.
    pending: list[tuple[Theme, str, list[str]]] = []
    decay = DecayReport()
    scanned = no_vector = 0

    for user_id in user_ids:
        user = await db.users.find_one({"_id": user_id}, {"locale": 1})
        # §2.4: a theme label is user-facing copy, so it is written in the
        # user's own language or not at all. No locale, no label.
        locale = (user or {}).get("locale") or ""

        memories: list[Memory] = []
        candidates: list[Candidate] = []
        contents: dict[ObjectId, str] = {}

        async for doc in db.memories.find({"user_id": user_id}):
            memory = Memory.from_doc(doc)
            memories.append(memory)
            contents[memory.memory_id] = memory.content
            vector = doc.get("embedding")
            model = doc.get("embedding_model")
            if not vector or not model:
                # §32.5 makes the embedding derived data — a memory without one
                # is still a memory, it simply cannot be compared. The
                # re-embedding batch job is what fixes this, not this job.
                no_vector += 1
                continue
            # A memory the user muted is out of retrieval by their choice; it
            # must not be folded into, or unmuting would restore a memory that
            # quietly became a pointer.
            if memory.visibility.muted:
                continue
            candidates.append(
                Candidate(memory=memory, vector=tuple(float(x) for x in vector), model=model)
            )

        scanned += len(memories)
        updates, decayed = plan_decay(memories, moment)
        decay_updates.extend(updates)
        decay = _add_decay(decay, decayed)

        user_folds = find_duplicates(candidates)
        folds.extend(user_folds)

        # A folded duplicate is out of retrieval, so it must not shape a theme.
        folded_ids = {fold.duplicate_id for fold in user_folds}
        live = [c for c in candidates if c.memory_id not in folded_ids]
        for theme in extract_themes(live):
            pending.append(
                (theme, locale, [contents.get(m, "") for m in theme.member_ids])
            )

    themes = [theme for theme, _, _ in pending]
    labelled = 0
    if labeller is not None and not dry_run:
        for index, (theme, locale, member_contents) in enumerate(pending):
            if not locale:
                continue
            label = await labeller.label(member_contents, locale)
            if label:
                themes[index] = Theme(theme.theme_id, theme.member_ids, label)
                labelled += 1

    if not dry_run:
        await _write(db, decay_updates, folds, themes, moment)

    return ConsolidationReport(
        users=len(user_ids),
        scanned=scanned,
        decay=decay,
        folded=len(folds),
        themes=len(themes),
        themed_memories=sum(theme.size for theme in themes),
        labelled=labelled,
        skipped_no_vector=no_vector,
    )


def _add_decay(total: DecayReport, one: DecayReport) -> DecayReport:
    return DecayReport(
        scanned=total.scanned + one.scanned,
        updated=total.updated + one.updated,
        below_floor=total.below_floor + one.below_floor,
        never_decays=total.never_decays + one.never_decays,
    )


async def _write(
    db,  # noqa: ANN001
    decay_updates: Sequence[tuple[ObjectId, float]],
    folds: Sequence[Fold],
    themes: Sequence[Theme],
    now: dt.datetime,
) -> None:
    from sitara_api.memory.store import MemoryStore

    await MemoryStore(db).set_decay_scores(decay_updates)

    for fold in folds:
        await db.memories.update_one(
            {"_id": fold.duplicate_id},
            {
                "$set": {
                    # The duplicate leaves retrieval the same way a muted
                    # memory does — one mechanism, so `retrieval.apply_gates`
                    # needs no new rule and the vault keeps showing the row.
                    "visibility.muted": True,
                    "consolidation.duplicate_of": fold.canonical_id,
                    "consolidation.duplicate_similarity": round(fold.similarity, 4),
                    "consolidation.last_run_at": now,
                    "updated_at": now,
                }
            },
        )

    for theme in themes:
        update: dict[str, Any] = {
            "consolidation.theme_id": theme.theme_id,
            "consolidation.theme_size": theme.size,
            "consolidation.last_run_at": now,
            "updated_at": now,
        }
        if theme.label is not None:
            update["theme_label"] = theme.label
        await db.memories.update_many(
            {"_id": {"$in": list(theme.member_ids)}}, {"$set": update}
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nightly memory consolidation — dedupe, decay, themes (§32.4, diagram 8)"
    )
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    from sitara_api.config import Settings
    from sitara_api.db import make_mongo

    client, db = make_mongo(Settings())
    try:
        report = asyncio.run(run_consolidation(db, dry_run=args.dry_run))
    finally:
        client.close()
    print(f"memory consolidation {'(dry run) ' if args.dry_run else ''}— {report.summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
