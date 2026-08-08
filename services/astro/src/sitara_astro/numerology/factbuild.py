"""Numerology FactSnapshot emission (§34.2 shape, §22.10 name contract).

Moolank and bhagyank need only the birth date, so the §10-9 reveal moment works
before the name step. Name numbers require a CONFIRMED Latin form — the engine
refuses to sum a name the user has not signed off.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sitara_schemas import ErrorCode
from sitara_schemas.facts import (
    BhagyankValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    MoolankValue,
    NameNumberValue,
    NameSource,
    build_fact_id,
)

from sitara_astro.errors import AstroError
from sitara_astro.numerology.core import (
    bhagyank,
    date_digits,
    letter_breakdown,
    moolank,
    name_number,
    normalise_name,
)
from sitara_astro.numerology.inputs import NumerologyOptions
from sitara_astro.numerology.translit import ISO15919_SCHEME, detect_script, propose_transliteration
from sitara_astro.version import engine_semver

# Numerology has no ephemeris and no timezone: its only inputs are the letter
# tables, which are versioned here so an artefact's provenance stays honest.
NUMEROLOGY_DATA_REVISION = "tables=chaldean.v1+pythagorean.v1"
PRECISION_EXACT = FactPrecision(tolerance=0.0, unit="exact")
SCOPE = "profile"  # §7.3: numerology:{subject}:{system}, permanent until profile edit


@dataclass(frozen=True)
class ConfirmedName:
    """A Latin name the user has confirmed (§22.10).

    Constructing one asserts the confirmation happened — the type IS the
    contract, so no caller can reach the engine with a guessed spelling.
    """

    latin: str
    source: NameSource
    original: str

    def __post_init__(self) -> None:
        # A non-Latin string here means confirmation produced no Latin form —
        # still the §22.10 flow state, not malformed input.
        if detect_script(self.latin) == "devanagari":
            raise AstroError(
                ErrorCode.ASTRO_NAME_UNCONFIRMED,
                message_key="errors.astro.name_unconfirmed",
            )
        # Anything else bad (digits, empty, symbols) is invalid input.
        normalise_name(self.latin)

    @classmethod
    def from_confirmation(
        cls, entered: str, *, confirmed: bool, edited_latin: str | None = None
    ) -> "ConfirmedName":
        """The onboarding S10 flow in one call.

        Latin entry needs no confirmation step. Non-Latin entry requires either
        an explicit yes to the proposal or an edited spelling; anything else
        raises ASTRO_NAME_UNCONFIRMED rather than guessing.
        """
        proposal = propose_transliteration(entered)
        if not proposal.needs_confirmation:
            return cls(
                latin=edited_latin or proposal.suggested_latin,
                source=NameSource.USER_EDITED if edited_latin else NameSource.LATIN_AS_ENTERED,
                original=proposal.original,
            )
        if edited_latin:
            return cls(
                latin=edited_latin, source=NameSource.USER_EDITED, original=proposal.original
            )
        if not confirmed:
            raise AstroError(
                ErrorCode.ASTRO_NAME_UNCONFIRMED,
                message_key="errors.astro.name_unconfirmed",
            )
        return cls(
            latin=proposal.suggested_latin,
            source=NameSource.CONFIRMED_TRANSLITERATION,
            original=proposal.original,
        )

    @property
    def was_transliterated(self) -> bool:
        return self.source is not NameSource.LATIN_AS_ENTERED and (
            detect_script(self.original) != "latin"
        )


def numerology_facts(
    dob: date,
    name: ConfirmedName | None,
    options: NumerologyOptions,
    *,
    subject: str,
    chart_version: int,
) -> list[FactSnapshot]:
    """Moolank + bhagyank (always) and one name-number fact per system."""
    valid_from = datetime.combine(dob, time.min, tzinfo=UTC)
    common = {
        "precision": PRECISION_EXACT,
        "valid_from": valid_from,
        "valid_to": None,  # permanent until the profile is edited (§7.3)
        "engine_semver": engine_semver(),
        "data_revision": NUMEROLOGY_DATA_REVISION,
    }
    date_method = FactMethod(master_numbers=options.master_numbers)

    moolank_value, moolank_steps = moolank(dob, options.master_numbers)
    bhagyank_value, bhagyank_steps = bhagyank(dob, options.master_numbers)

    facts: list[FactSnapshot] = [
        FactSnapshot(
            fact_id=build_fact_id("numerology.moolank", SCOPE, subject, chart_version),
            kind=FactKind.NUMEROLOGY_MOOLANK,
            value=MoolankValue(
                value=moolank_value, birth_day=dob.day, reduction_steps=moolank_steps
            ),
            method=date_method,
            **common,
        ),
        FactSnapshot(
            fact_id=build_fact_id("numerology.bhagyank", SCOPE, subject, chart_version),
            kind=FactKind.NUMEROLOGY_BHAGYANK,
            value=BhagyankValue(
                value=bhagyank_value,
                digits=date_digits(dob),
                reduction_steps=bhagyank_steps,
            ),
            method=date_method,
            **common,
        ),
    ]

    if name is None:
        return facts

    for system in options.systems:
        value, compound, steps = name_number(name.latin, system, options.master_numbers)
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"numerology.name_number.{system.value}", SCOPE, subject, chart_version
                ),
                kind=FactKind.NUMEROLOGY_NAME_NUMBER,
                value=NameNumberValue(
                    system=system,
                    value=value,
                    compound_value=compound,
                    latin_name=name.latin,
                    letter_values=letter_breakdown(name.latin, system),
                    reduction_steps=steps,
                ),
                method=FactMethod(
                    master_numbers=options.master_numbers,
                    numerology_system=system,
                    name_source=name.source,
                    transliteration_scheme=ISO15919_SCHEME if name.was_transliterated else None,
                ),
                **common,
            )
        )
    return facts
