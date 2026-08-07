"""Vimshottari arithmetic — hand-computable expectations, no ephemeris needed."""

from datetime import UTC, datetime, timedelta

from sitara_schemas.facts import DashaLevel, DashaYearBasis, Graha

from sitara_astro.engine.constants import DASHA_LORD_SEQUENCE, DASHA_YEARS
from sitara_astro.engine.dasha import compute_vimshottari

BIRTH = datetime(1990, 5, 15, 9, 0, tzinfo=UTC)
ARC = 360.0 / 27.0
YEAR = timedelta(days=365.25)


def mahas(periods):  # noqa: ANN001, ANN201 - test helper
    return sorted((p for p in periods if p.level is DashaLevel.MAHA), key=lambda p: p.start)


def test_moon_at_ashwini_start_gives_full_ketu_maha() -> None:
    periods = compute_vimshottari(0.0, BIRTH, DashaYearBasis.DAYS_365_25, levels=1)
    first = mahas(periods)[0]
    assert first.lord is Graha.KETU
    assert first.start == BIRTH  # zero elapsed: maha starts exactly at birth
    assert first.end == BIRTH + 7 * YEAR


def test_moon_halfway_through_nakshatra_halves_the_balance() -> None:
    periods = compute_vimshottari(ARC / 2, BIRTH, DashaYearBasis.DAYS_365_25, levels=1)
    first = mahas(periods)[0]
    assert first.lord is Graha.KETU
    assert first.start == BIRTH - 3.5 * YEAR  # half of Ketu's 7y already elapsed
    assert first.end == BIRTH + 3.5 * YEAR


def test_sequence_and_total_span() -> None:
    periods = compute_vimshottari(ARC * 1.25, BIRTH, DashaYearBasis.DAYS_365_25, levels=1)
    seq = mahas(periods)
    assert len(seq) == 9
    # Moon in Bharani → Venus maha first, 25% elapsed
    assert [p.lord for p in seq] == [
        Graha.VENUS, Graha.SUN, Graha.MOON, Graha.MARS, Graha.RAHU,
        Graha.JUPITER, Graha.SATURN, Graha.MERCURY, Graha.KETU,
    ]
    assert seq[0].start == BIRTH - 5 * YEAR  # 25% of 20y
    assert seq[-1].end - seq[0].start == 120 * YEAR
    for prev, nxt in zip(seq, seq[1:], strict=False):
        assert prev.end == nxt.start


def test_antar_subdivision_proportions() -> None:
    periods = compute_vimshottari(0.0, BIRTH, DashaYearBasis.DAYS_365_25, levels=2)
    ketu_antars = sorted(
        (p for p in periods if p.level is DashaLevel.ANTAR and p.parents == (Graha.KETU,)),
        key=lambda p: p.start,
    )
    assert len(ketu_antars) == 9
    assert ketu_antars[0].lord is Graha.KETU  # first antar lord = maha lord
    assert ketu_antars[1].lord is Graha.VENUS
    # Ketu-Ketu antar = 7 * 7/120 years
    expected = timedelta(days=365.25 * 7 * 7 / 120)
    assert abs((ketu_antars[0].end - ketu_antars[0].start) - expected) < timedelta(seconds=1)


def test_pratyantar_depth_and_count() -> None:
    periods = compute_vimshottari(0.0, BIRTH, DashaYearBasis.DAYS_365_25, levels=3)
    pratyantars = [p for p in periods if p.level is DashaLevel.PRATYANTAR]
    assert len(pratyantars) == 729
    sample = pratyantars[0]
    assert len(sample.parents) == 2


def test_year_basis_changes_boundaries() -> None:
    a = mahas(compute_vimshottari(0.0, BIRTH, DashaYearBasis.DAYS_365_25, levels=1))
    b = mahas(compute_vimshottari(0.0, BIRTH, DashaYearBasis.SAVANA_360, levels=1))
    assert a[0].end != b[0].end
    assert b[0].end == BIRTH + timedelta(days=360 * 7)


def test_nakshatra_lord_mapping_is_cyclic() -> None:
    assert DASHA_LORD_SEQUENCE[0] is Graha.KETU
    assert sum(DASHA_YEARS[lord] for lord in DASHA_LORD_SEQUENCE) == 120
    with_moon_in = lambda idx: mahas(  # noqa: E731
        compute_vimshottari(idx * ARC, BIRTH, DashaYearBasis.DAYS_365_25, levels=1)
    )[0].lord
    assert with_moon_in(9) is Graha.KETU  # Magha restarts the cycle
    assert with_moon_in(18) is Graha.KETU  # Mula restarts again
    assert with_moon_in(4) is Graha.MARS  # Mrigashira
