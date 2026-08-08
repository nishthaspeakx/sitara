"""Fact adjudication — SPEC §32.2, the §5.2 Layer D tolerances.

§32.2 REPLACED the naive "majority source" rule of §5.2 Layer D. The binding
rules, and the truth table below:

  * Chart facts (positions, lagna, dasha, nakshatra) — Layer A is
    authoritative, NEVER voted. External disagreement only flags review.
  * Panchang/muhurat/festival facts — DivineAPI is primary. On a
    DivineAPI↔Prokerala disagreement beyond tolerance the fact serves from
    DivineAPI, downgrades confidence, and queues Jyotish adjudication.
  * Two unverified vendors can never overrule validated deterministic astronomy.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sitara_schemas.facts import ConfidenceState, FactSource

from sitara_api.panchang.adjudicate import (
    BOUNDARY_TOLERANCE,
    DASHA_TOLERANCE,
    POSITION_TOLERANCE_DEG,
    FactClass,
    Reading,
    adjudicate,
)

T0 = datetime(2026, 8, 7, 6, 17, tzinfo=UTC)


def layer_a(offset_seconds: float = 0) -> Reading:
    return Reading(source=FactSource.LAYER_A, instant=T0 + timedelta(seconds=offset_seconds))


def divine(offset_seconds: float = 0) -> Reading:
    return Reading(source=FactSource.DIVINEAPI, instant=T0 + timedelta(seconds=offset_seconds))


def prokerala(offset_seconds: float = 0) -> Reading:
    return Reading(source=FactSource.PROKERALA, instant=T0 + timedelta(seconds=offset_seconds))


class TestChartFactsAreNeverVoted:
    """The heart of §32.2. These tests exist to make the majority rule
    impossible to reintroduce by accident."""

    def test_layer_a_is_served_when_both_vendors_disagree_with_it(self) -> None:
        """Two unverified vendors CANNOT overrule validated deterministic
        astronomy — even when they agree with each other and outnumber us."""
        result = adjudicate(
            FactClass.CHART,
            layer_a=layer_a(),
            divineapi=divine(600),
            prokerala=prokerala(600),
        )
        assert result.source is FactSource.LAYER_A
        assert result.served == T0

    def test_vendor_disagreement_flags_review_but_never_disputes(self) -> None:
        """§32.2: 'external disagreement only flags review'. A flag is an admin
        signal (§12 comparison dashboard); a dispute is a user-visible
        confidence downgrade. Chart facts get the former, never the latter."""
        result = adjudicate(
            FactClass.CHART, layer_a=layer_a(), divineapi=divine(600), prokerala=prokerala(600)
        )
        assert result.review_flagged is True
        assert result.disputed is False
        assert result.confidence is None  # nothing to downgrade

    def test_no_adjudication_is_queued_for_chart_facts(self) -> None:
        """A flagged chart fact is a provider-quality signal, not a question
        for the Jyotish lead — our own engine is the answer."""
        result = adjudicate(
            FactClass.CHART, layer_a=layer_a(), divineapi=divine(600), prokerala=prokerala(600)
        )
        assert result.adjudication is None

    def test_agreement_raises_no_flag(self) -> None:
        result = adjudicate(
            FactClass.CHART, layer_a=layer_a(), divineapi=divine(30), prokerala=prokerala(-30)
        )
        assert result.review_flagged is False
        assert result.source is FactSource.LAYER_A

    def test_layer_a_alone_is_sufficient(self) -> None:
        """Cross-check is an audit, not a dependency: with both vendors down
        the chart fact is still served, unflagged."""
        result = adjudicate(FactClass.CHART, layer_a=layer_a(), divineapi=None, prokerala=None)
        assert result.source is FactSource.LAYER_A
        assert result.review_flagged is False


class TestPanchangFactsPreferDivineApi:
    def test_divineapi_is_served_when_vendors_agree(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala(60)
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.disputed is False
        assert result.adjudication is None

    def test_disagreement_beyond_tolerance_still_serves_divineapi(self) -> None:
        """§32.2: the fact SERVES from DivineAPI. Prokerala cannot win a
        disagreement — it can only raise its hand."""
        result = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala(600)
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.served == T0

    def test_disagreement_downgrades_confidence_to_approximate(self) -> None:
        """§5.4's Approximate row is triggered by 'a disputed fact in play'."""
        result = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala(600)
        )
        assert result.disputed is True
        assert result.confidence is ConfidenceState.APPROXIMATE

    def test_disagreement_queues_jyotish_adjudication(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala(600)
        )
        record = result.adjudication
        assert record is not None
        assert record.served_source is FactSource.DIVINEAPI
        assert record.status == "pending"
        assert record.delta_seconds == pytest.approx(600)
        # Both opinions are preserved so the reviewer can adjudicate without
        # re-querying a vendor whose answer may have changed since.
        assert record.readings[FactSource.DIVINEAPI.value] == T0.isoformat()
        expected = (T0 + timedelta(seconds=600)).isoformat()
        assert record.readings[FactSource.PROKERALA.value] == expected

    @pytest.mark.parametrize("fact_class", [FactClass.MUHURAT, FactClass.FESTIVAL])
    def test_muhurat_and_festival_follow_the_same_rule(self, fact_class: FactClass) -> None:
        result = adjudicate(
            fact_class, layer_a=None, divineapi=divine(), prokerala=prokerala(600)
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.disputed is True


class TestLayerAIsNeverOutvotedOnPanchangEither:
    def test_layer_a_disagreement_flags_but_does_not_change_the_served_value(self) -> None:
        """Our engine's opinion on a CALENDAR fact is advisory — DivineAPI is
        primary there per §32.2 — but a large gap is still worth an admin's
        attention."""
        result = adjudicate(
            FactClass.PANCHANG,
            layer_a=layer_a(900),
            divineapi=divine(),
            prokerala=prokerala(),
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.review_flagged is True
        assert result.disputed is False  # vendors agree with each other


class TestDegradation:
    def test_prokerala_alone_serves_but_is_marked(self) -> None:
        """§8 ladder: DivineAPI down → Prokerala. Its ToS forbids it being the
        system of record, so anything it serves is explicitly degraded."""
        result = adjudicate(FactClass.PANCHANG, layer_a=None, divineapi=None, prokerala=prokerala())
        assert result.source is FactSource.PROKERALA
        assert result.confidence is ConfidenceState.APPROXIMATE
        assert result.cacheable is False

    def test_divineapi_result_is_cacheable(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala()
        )
        assert result.cacheable is True

    def test_layer_a_fallback_serves_tradition_based_general(self) -> None:
        """§5.4: a panchang-only answer with no chart in play is exactly the
        'Tradition-based general' row."""
        result = adjudicate(FactClass.PANCHANG, layer_a=layer_a(), divineapi=None, prokerala=None)
        assert result.source is FactSource.LAYER_A
        assert result.confidence is ConfidenceState.TRADITION_BASED_GENERAL

    def test_no_sources_cannot_calculate(self) -> None:
        """§5.3: missing data means an honest decline, never a guess."""
        result = adjudicate(FactClass.PANCHANG, layer_a=None, divineapi=None, prokerala=None)
        assert result.served is None
        assert result.confidence is ConfidenceState.CANNOT_CALCULATE


class TestTolerances:
    """§5.2 Layer D states them exactly: positions >1 arc-min, tithi/nakshatra
    boundary times >2 min, dasha dates >1 day."""

    def test_tolerance_constants_match_the_spec(self) -> None:
        assert BOUNDARY_TOLERANCE == timedelta(minutes=2)
        assert DASHA_TOLERANCE == timedelta(days=1)
        assert POSITION_TOLERANCE_DEG == pytest.approx(1 / 60)

    @pytest.mark.parametrize(
        ("delta_seconds", "expect_disputed"),
        [(0, False), (119, False), (120, False), (121, True), (600, True)],
    )
    def test_boundary_tolerance_is_inclusive(
        self, delta_seconds: int, expect_disputed: bool
    ) -> None:
        """'beyond tolerance' means strictly greater — exactly 2 minutes is
        still agreement."""
        result = adjudicate(
            FactClass.PANCHANG,
            layer_a=None,
            divineapi=divine(),
            prokerala=prokerala(delta_seconds),
        )
        assert result.disputed is expect_disputed

    def test_sign_of_the_disagreement_does_not_matter(self) -> None:
        early = adjudicate(
            FactClass.PANCHANG, layer_a=None, divineapi=divine(), prokerala=prokerala(-600)
        )
        assert early.disputed is True


class TestNoMajorityVoting:
    def test_no_executable_code_mentions_majority(self) -> None:
        """§5.2 Layer D's 'served from the majority source' was REPLACED by
        §32.2. Prose may explain that history — executable code may not
        implement it. Docstrings and comments are stripped via the AST so the
        check reads real statements only, not the paragraph above them."""
        import ast
        import inspect

        from sitara_api.panchang import adjudicate as module

        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(node, clean=False)
                if docstring and node.body:
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        assert "majority" not in ast.unparse(tree).lower()

    def test_the_served_value_is_always_one_source_verbatim(self) -> None:
        """A vote would blend or pick by count; §32.2 picks by AUTHORITY. The
        served instant must therefore always be exactly one input, never an
        average of them."""
        cases = [
            (FactClass.CHART, layer_a(), divine(600), prokerala(600)),
            (FactClass.PANCHANG, layer_a(900), divine(), prokerala(600)),
            (FactClass.PANCHANG, layer_a(), None, prokerala(600)),
        ]
        for fact_class, a, d, p in cases:
            result = adjudicate(fact_class, layer_a=a, divineapi=d, prokerala=p)
            inputs = {r.instant for r in (a, d, p) if r is not None}
            assert result.served in inputs


class TestPanchangAstronomyHybrid:
    """§32.2 + decision D1 for the tithi/nakshatra boundary instants.

    These are BOTH deterministic astronomy and panchang facts, so the rule
    depends on whether our engine could answer:

      * Layer A present → it is authoritative and is never voted (D1).
      * Layer A absent  → §32.2's plain rule takes over, because the vendors
        are then genuinely all we have and the §8 ladder is serving from one
        of them.
    """

    def test_layer_a_present_means_layer_a_wins(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG_ASTRONOMY,
            layer_a=layer_a(),
            divineapi=divine(600),
            prokerala=prokerala(600),
        )
        assert result.source is FactSource.LAYER_A
        assert result.review_flagged is True
        assert result.disputed is False
        assert result.adjudication is None

    def test_layer_a_absent_falls_back_to_divineapi_primary(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG_ASTRONOMY,
            layer_a=None,
            divineapi=divine(),
            prokerala=prokerala(600),
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.disputed is True
        assert result.confidence is ConfidenceState.APPROXIMATE
        assert result.adjudication is not None

    def test_layer_a_absent_and_vendors_agree_is_clean(self) -> None:
        result = adjudicate(
            FactClass.PANCHANG_ASTRONOMY,
            layer_a=None,
            divineapi=divine(),
            prokerala=prokerala(30),
        )
        assert result.source is FactSource.DIVINEAPI
        assert result.disputed is False

    def test_strict_chart_facts_still_have_no_vendor_substitute(self) -> None:
        """The hybrid is scoped to boundary instants ONLY. A missing position
        or dasha date is never backfilled from a vendor — §32.2 forbids
        unverified vendors standing in for deterministic astronomy."""
        result = adjudicate(
            FactClass.CHART, layer_a=None, divineapi=divine(), prokerala=prokerala()
        )
        assert result.source is None
        assert result.served is None
        assert result.confidence is ConfidenceState.CANNOT_CALCULATE
