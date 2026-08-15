"""§30.5's P0 search — keyword + filters over Journal + thread.

**What P0 is, precisely.** §30.5: "P0 keyword+filters (type: brief/reflection/
call/guidance/memory; date; family member) over Journal+thread via Atlas
Search; natural-language search P1 (embeddings already exist)." So this is a
keyword filter, not a relevance engine. That distinction is what makes the
Community-mongo fallback honest rather than a toy: the P0 contract is *every
artefact containing every term, newest first*, and two implementations can
satisfy that identically. A BM25 score is not something an exact scan can
reproduce, which is exactly why P0 does not promise one.

**Sensitive-search honesty is two answers over the same row.** §30.5:
"searching health-adjacent or safety-flagged content shows results to the user
(her data) but never resurfaces L4 content as casual suggestions." A query she
typed and a list the app offered her are different acts, so `SearchMode` is a
parameter rather than a setting — there is no way to run a suggestion without
saying it is one.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from bson import ObjectId

from sitara_api.journal.models import ArtefactType

logger = logging.getLogger(__name__)

#: How many rows per source the exact fallback will scan. The memory module's
#: rule applies: a cap that silently drops matches reads to the user as
#: "nothing more matched", so exceeding it is LOGGED.
DEFAULT_SCAN_LIMIT = 500

#: §9's L4. `messages.safety_labels` stores risk classes rather than ladder
#: levels, and `ACUTE_CRISIS` is the class §9 routes to L4 — the one §30.5
#: says never to resurface unbidden. Named as a set of one so that adding a
#: second L4 class is a data change here rather than a new condition.
L4_RISK_CLASSES: frozenset[str] = frozenset({"acute_crisis"})


class SearchMode(StrEnum):
    """Who asked.

    EXPLICIT — the user typed a query. She gets everything of hers.
    SUGGESTION — the app is offering something unprompted. §30.5's L4 rule
    applies here and only here.
    """

    EXPLICIT = "explicit"
    SUGGESTION = "suggestion"


@dataclass(frozen=True)
class SearchFilters:
    """§30.5's three P0 filters."""

    types: tuple[ArtefactType, ...] = ()
    since: str | None = None
    until: str | None = None
    #: §30.5: "family-member guidance appears in the account-holder's spaces
    #: only; per-member filter exists".
    family_member_id: ObjectId | None = None

    def allows(self, artefact_type: ArtefactType) -> bool:
        return not self.types or artefact_type in self.types


@dataclass(frozen=True)
class SearchHit:
    artefact_type: ArtefactType
    ref: str
    local_date: str
    preview: str
    occurred_at: dt.datetime | None = None
    message_id: str | None = None
    conversation_id: str | None = None


class JournalSearch(Protocol):
    async def run(
        self,
        *,
        user_id: ObjectId,
        query: str,
        filters: SearchFilters,
        mode: SearchMode = SearchMode.EXPLICIT,
        limit: int = 50,
    ) -> list[SearchHit]: ...


# ---------------------------------------------------------------------------
# matching


def terms_of(query: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"\s+", query.strip().lower()) if t)


def matches(text: str, terms: Sequence[str]) -> bool:
    """Every term must appear. Two words narrow a search; they do not widen it.

    Substring rather than word-boundary matching, deliberately: `\\b` is unsafe
    on Devanagari (CL-003 — vowel signs and the virama are combining marks
    Python excludes from `\\w`), and a journal search that silently matched
    nothing in Hindi would look like an empty journal.
    """
    haystack = text.lower()
    return all(term in haystack for term in terms)


def _preview(text: str, terms: Sequence[str], *, width: int = 160) -> str:
    """A window around the first hit, so a result shows why it matched."""
    lowered = text.lower()
    at = min((lowered.find(t) for t in terms if lowered.find(t) >= 0), default=0)
    start = max(0, at - width // 3)
    snippet = text[start : start + width]
    return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")


def _is_l4(doc: dict[str, Any]) -> bool:
    return any(
        (label or {}).get("risk_class") in L4_RISK_CLASSES
        for label in doc.get("safety_labels") or []
    )


def _local_date_of(moment: dt.datetime | None) -> str:
    return moment.astimezone(dt.UTC).date().isoformat() if moment else ""


def _in_range(local_date: str, filters: SearchFilters) -> bool:
    if filters.since and local_date < filters.since:
        return False
    return not (filters.until and local_date > filters.until)


# ---------------------------------------------------------------------------


class ExactTextSearch:
    """The Community-mongo implementation (§6 gives development `mongo:7`).

    It scans the user's own rows and applies the same predicate the Atlas
    backend expresses as a `$search` stage. Same corpus, same filter, same
    order — the difference is the index, which is a scale property rather than
    a correctness one, exactly as `ExactVectorSearch` is to `AtlasVectorSearch`.
    """

    def __init__(self, db: Any, *, scan_limit: int = DEFAULT_SCAN_LIMIT) -> None:
        self._db = db
        self._scan_limit = scan_limit

    async def run(
        self,
        *,
        user_id: ObjectId,
        query: str,
        filters: SearchFilters,
        mode: SearchMode = SearchMode.EXPLICIT,
        limit: int = 50,
    ) -> list[SearchHit]:
        terms = terms_of(query)
        if not terms:
            return []

        hits: list[SearchHit] = []
        for source in (self._thread, self._reflections, self._briefs, self._calls):
            hits.extend(await source(user_id, terms, filters, mode))

        hits.sort(key=lambda h: (h.local_date, h.occurred_at or dt.datetime.min), reverse=True)
        return hits[:limit]

    # -- sources ------------------------------------------------------------

    async def _conversation_ids(self, user_id: ObjectId) -> list[ObjectId]:
        """§6.4 scopes `messages` by conversation, and conversations by user.

        The hop matters: a search that queried `messages` directly would have
        no user predicate at all, and the first bug would be one account's
        thread appearing in another's journal.
        """
        cursor = self._db.conversations.find({"user_id": user_id}, {"_id": 1})
        return [doc["_id"] async for doc in cursor]

    async def _thread(
        self,
        user_id: ObjectId,
        terms: Sequence[str],
        filters: SearchFilters,
        mode: SearchMode,
    ) -> list[SearchHit]:
        if not filters.allows(ArtefactType.GUIDANCE):
            return []
        conversation_ids = await self._conversation_ids(user_id)
        if not conversation_ids:
            return []

        cursor = self._db.messages.find(
            {"conversation_id": {"$in": conversation_ids}}
        ).limit(self._scan_limit + 1)
        docs = [doc async for doc in cursor]
        docs = self._note_truncation(docs, "messages")

        hits: list[SearchHit] = []
        for doc in docs:
            if mode is SearchMode.SUGGESTION and _is_l4(doc):
                # §30.5: never as a casual suggestion. Reachable by an
                # explicit query, which is the branch above.
                continue
            content = doc.get("content")
            if not isinstance(content, str) or not matches(content, terms):
                continue
            local_date = _local_date_of(doc.get("created_at"))
            if not _in_range(local_date, filters):
                continue
            hits.append(
                SearchHit(
                    artefact_type=ArtefactType.GUIDANCE,
                    ref=str(doc["_id"]),
                    local_date=local_date,
                    preview=_preview(content, terms),
                    occurred_at=doc.get("created_at"),
                    message_id=str(doc["_id"]),
                    conversation_id=str(doc["conversation_id"]),
                )
            )
        return hits

    async def _reflections(
        self,
        user_id: ObjectId,
        terms: Sequence[str],
        filters: SearchFilters,
        mode: SearchMode,
    ) -> list[SearchHit]:
        if not filters.allows(ArtefactType.REFLECTION):
            return []
        cursor = self._db.night_reflections.find({"user_id": user_id}).limit(self._scan_limit + 1)
        docs = self._note_truncation([doc async for doc in cursor], "night_reflections")

        hits: list[SearchHit] = []
        for doc in docs:
            local_date = doc.get("date", "")
            if not _in_range(local_date, filters):
                continue
            text = " ".join(_strings(doc.get("entries")))
            if not text or not matches(text, terms):
                continue
            hits.append(
                SearchHit(
                    artefact_type=ArtefactType.REFLECTION,
                    ref=local_date,
                    local_date=local_date,
                    preview=_preview(text, terms),
                    occurred_at=doc.get("created_at"),
                )
            )
        return hits

    async def _briefs(
        self,
        user_id: ObjectId,
        terms: Sequence[str],
        filters: SearchFilters,
        mode: SearchMode,
    ) -> list[SearchHit]:
        if not filters.allows(ArtefactType.BRIEF):
            return []
        cursor = self._db.daily_briefings.find({"user_id": user_id}).limit(self._scan_limit + 1)
        docs = self._note_truncation([doc async for doc in cursor], "daily_briefings")

        hits: list[SearchHit] = []
        for doc in docs:
            local_date = doc.get("date", "")
            if not _in_range(local_date, filters):
                continue
            text = " ".join(
                str(m.get("polished_text") or m.get("text") or "")
                for m in doc.get("modules") or []
            )
            if not text.strip() or not matches(text, terms):
                continue
            hits.append(
                SearchHit(
                    artefact_type=ArtefactType.BRIEF,
                    ref=local_date,
                    local_date=local_date,
                    preview=_preview(text, terms),
                    occurred_at=doc.get("generated_at") or doc.get("created_at"),
                )
            )
        return hits

    async def _calls(
        self,
        user_id: ObjectId,
        terms: Sequence[str],
        filters: SearchFilters,
        mode: SearchMode,
    ) -> list[SearchHit]:
        if not filters.allows(ArtefactType.CALL):
            return []
        cursor = self._db.call_sessions.find(
            {"user_id": user_id, "summary": {"$ne": None}}
        ).limit(self._scan_limit + 1)
        docs = self._note_truncation([doc async for doc in cursor], "call_sessions")

        hits: list[SearchHit] = []
        for doc in docs:
            summary = doc.get("summary")
            text = summary if isinstance(summary, str) else " ".join(_strings(summary))
            if not text or not matches(text, terms):
                continue
            local_date = _local_date_of(doc.get("ended_at") or doc.get("started_at"))
            if not _in_range(local_date, filters):
                continue
            hits.append(
                SearchHit(
                    artefact_type=ArtefactType.CALL,
                    ref=str(doc["_id"]),
                    local_date=local_date,
                    preview=_preview(text, terms),
                    occurred_at=doc.get("ended_at"),
                    conversation_id=(
                        str(doc["conversation_id"]) if doc.get("conversation_id") else None
                    ),
                )
            )
        return hits

    def _note_truncation(self, docs: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
        if len(docs) > self._scan_limit:
            logger.info(
                "journal search truncated %s at %d rows — results are incomplete",
                source,
                self._scan_limit,
            )
            return docs[: self._scan_limit]
        return docs


def _strings(value: Any) -> Iterable[str]:
    """Reflection entries and call summaries are shaped by their own modules.

    Both are declared loosely in §6.4 (`entries: array`, `summary: string|object`)
    and both may come back as ciphertext when CSFLE is on and this codec is
    not the encrypting one. A non-string is skipped rather than stringified —
    searching the repr of a Binary would match nothing and look like a bug in
    the query.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, str)]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_strings(item))
        return out
    return []


__all__ = [
    "DEFAULT_SCAN_LIMIT",
    "L4_RISK_CLASSES",
    "ExactTextSearch",
    "JournalSearch",
    "SearchFilters",
    "SearchHit",
    "SearchMode",
    "matches",
    "terms_of",
]
