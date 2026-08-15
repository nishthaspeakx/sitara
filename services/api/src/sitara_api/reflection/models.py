"""Night reflection types (§6.4 `night_reflections`, §10-17, §24.4 S19).

§10-17 fixes the shape: "3 prompts + day summary + tomorrow preview; ≤3 min;
**no streaks, no guilt**". The last four words are a design constraint with
teeth, and they are enforced by absence: there is no streak field, no
completion count, no "you missed yesterday" anywhere in this module. A
reflection is a thing she may do tonight, not a chain she can break.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from bson import ObjectId


class Prompt(StrEnum):
    """§10-17's three prompts, as ids rather than sentences.

    The wording lives in the i18n catalogs (§2.4) — three IDs here, three
    strings per locale there, so Tara asks a Hindi user in Hindi rather than
    in a translated-at-render English question.
    """

    GRATITUDE = "gratitude"
    WEIGHT = "weight"
    TOMORROW = "tomorrow"


#: The order they are asked in. A tuple rather than the enum's own order, so
#: reordering the ceremony is a one-line change with a test behind it.
PROMPT_ORDER: tuple[Prompt, ...] = (Prompt.GRATITUDE, Prompt.WEIGHT, Prompt.TOMORROW)


class Mood(StrEnum):
    """A coarse, optional self-report.

    Deliberately five plain states and no numeric scale: §0.8's emotional
    design asks for closure, and a 1–10 slider on a bad night is a test she
    can fail. Optional throughout — a reflection with no mood is complete.
    """

    HEAVY = "heavy"
    TIRED = "tired"
    STEADY = "steady"
    LIGHT = "light"
    JOYFUL = "joyful"


@dataclass(frozen=True)
class ReflectionEntry:
    prompt: Prompt
    text: str


@dataclass(frozen=True)
class Reflection:
    """One `night_reflections` row.

    Note what is not here: a streak, a completion percentage, a comparison
    with any other night. §10-17 forbids all three, and the way to keep a
    forbidden field out of a schema is to leave it out of the type that writes
    it.
    """

    reflection_id: ObjectId
    user_id: ObjectId
    #: The user's LOCAL calendar date, bound at creation (§27's night-reflection
    #: row). Never re-derived on read — a red-eye flight must not move a
    #: reflection to another day after the fact.
    date: str
    locale: str
    entries: tuple[ReflectionEntry, ...] = field(default_factory=tuple)
    mood: Mood | None = None
    #: §32.4's chips, offered from what she wrote. Ids only — the memory
    #: itself is created through the vault's own consent path, never here.
    memory_chips: tuple[str, ...] = field(default_factory=tuple)
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None

    @property
    def is_started(self) -> bool:
        return bool(self.entries) or self.mood is not None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Reflection:
        raw_entries = doc.get("entries")
        entries: list[ReflectionEntry] = []
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if not isinstance(item, dict):
                    # CSFLE returns Binary without the codec; a reflection that
                    # cannot be read renders as empty rather than as ciphertext.
                    continue
                try:
                    entries.append(
                        ReflectionEntry(
                            prompt=Prompt(item["prompt"]), text=str(item.get("text", ""))
                        )
                    )
                except (KeyError, ValueError):
                    continue

        raw_mood = doc.get("mood")
        mood: Mood | None = None
        if isinstance(raw_mood, str):
            try:
                mood = Mood(raw_mood)
            except ValueError:
                mood = None

        return cls(
            reflection_id=doc["_id"],
            user_id=doc["user_id"],
            date=doc["date"],
            locale=doc.get("locale", "en"),
            entries=tuple(entries),
            mood=mood,
            memory_chips=tuple(str(c) for c in doc.get("memory_chips") or []),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )


__all__ = ["PROMPT_ORDER", "Mood", "Prompt", "Reflection", "ReflectionEntry"]
