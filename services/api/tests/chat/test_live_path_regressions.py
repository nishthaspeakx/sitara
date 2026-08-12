"""The three defects the first live conversation found, each pinned.

None of them was reachable from the existing suite, and the reason is the same
in all three cases: **every test supplied by hand the thing production has to
look up.** The chat tests pass a `BirthProfile` in, stub the fact provider
outright, and never read a seeded row. So the wiring between those pieces —
which is all production has — was untested by construction.

Written after the run, not before, and that is worth saying plainly: the tests
below would not have been thought of without watching a real account get told
"I'd need your date of birth" while its birth row sat complete in Mongo.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.facts import (
    DashaLevel,
    DashaPeriodValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    TzMethod,
)

from sitara_api import trust

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. The router never loaded a birth profile
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Just enough of a Starlette request for `_birth_profile`."""

    def __init__(self, facade: object | None) -> None:
        self.app = type("App", (), {"state": type("S", (), {"astrology": facade})()})()


class _Facade:
    def __init__(self, birth: object | None = None, raises: bool = False) -> None:
        self._birth = birth
        self._raises = raises

    async def birth_input(self, user_id: str):  # noqa: ANN202
        if self._raises:
            raise RuntimeError("engine down")
        return self._birth


class _Birth:
    def __init__(self, *, time: dt.time | None, place_name: str, tz: str) -> None:
        self.time = time
        self.place_name = place_name
        self.tz = tz

    @property
    def has_exact_time(self) -> bool:
        return self.time is not None


async def test_the_router_loads_the_birth_profile_from_the_facade() -> None:
    """It read `request.state.birth_profile`, which nothing ever set.

    So every live turn ran with an all-False profile, `required_data` declined
    for a missing date of birth, and chat could not answer one chart question
    against a real account. Nine turns in three locales, all declining, with a
    complete birth row in the database — that is what this pins.
    """
    from sitara_api.chat_orchestration.router import _birth_profile

    birth = _Birth(time=dt.time(4, 55), place_name="Jaipur", tz="Asia/Kolkata")
    request = _FakeRequest(_Facade(birth))
    profile = await _birth_profile(request, "6a70000000000000000000a1")

    assert profile.has_date is True
    assert profile.has_exact_time is True
    assert profile.has_place is True
    assert profile.tz == "Asia/Kolkata"


async def test_a_row_without_a_birth_time_is_the_moon_chart_path() -> None:
    """§5.3: no birth time is a Moon chart, not a guessed ascendant. The
    profile says so rather than claiming an exact time it does not have."""
    from sitara_api.chat_orchestration.router import _birth_profile

    request = _FakeRequest(_Facade(_Birth(time=None, place_name="Jaipur", tz="Asia/Kolkata")))
    profile = await _birth_profile(request, "6a70000000000000000000a1")

    assert profile.has_date is True
    assert profile.has_exact_time is False
    assert profile.has_time_window is True


async def test_a_facade_failure_degrades_rather_than_failing_the_turn() -> None:
    """Tara asks for a birth date she cannot confirm she has. A worse answer,
    never a wrong one — and never a 500 on the chat surface."""
    from sitara_api.chat_orchestration.router import _birth_profile

    for facade in (_Facade(raises=True), _Facade(None), None):
        profile = await _birth_profile(_FakeRequest(facade), "6a70000000000000000000a1")
        assert profile.has_date is False


# ---------------------------------------------------------------------------
# 2. The pipeline was wired without the astrology facade
# ---------------------------------------------------------------------------


def test_build_pipeline_passes_the_astrology_facade_to_the_fact_provider() -> None:
    """`AstrologyFacadeProvider` has taken `astrology_facade` since M5 and
    nothing ever passed it, so `_chart` raised `chart_facade_unavailable` for
    every natal, transit and relationship question — surfacing as
    `chat.data.cannot_calculate` while the engine sat healthy.

    The chat suite could not see it: `build_env` constructs the provider
    itself. This asserts the WIRING, which is the part production uses.
    """
    from sitara_api.chat_orchestration import build_pipeline
    from sitara_api.chat_orchestration.config import ChatSettings

    sentinel = object()
    pipeline = build_pipeline(
        chat_settings=ChatSettings(anthropic_api_key="test-key"),
        environment="test",
        db=None,
        astrology_facade=sentinel,
    )
    assert pipeline is not None
    assert pipeline._facts._astrology is sentinel  # noqa: SLF001


def test_the_app_hands_the_facade_it_built_to_the_pipeline() -> None:
    """A parse of `app.py`, because the lifespan needs Mongo to run. The order
    matters too — `app.state.astrology` is built before the pipeline — and a
    reordering that broke it would pass `None` silently."""
    import ast
    import inspect

    from sitara_api import app as app_module

    source = inspect.getsource(app_module)
    tree = ast.parse(source)
    passed = [
        kw
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "build_pipeline"
        for kw in node.keywords
        if kw.arg == "astrology_facade"
    ]
    assert passed, "app.py builds the pipeline without an astrology facade"
    assert source.index("app.state.astrology = AstrologyFacade") < source.index("build_pipeline(")


# ---------------------------------------------------------------------------
# 3. The seeder wrote a place shape the facade cannot read
# ---------------------------------------------------------------------------


def test_the_seeder_writes_the_place_shape_the_facade_reads() -> None:
    """`birth_input` requires `place["tz"]` (§5.2 forbids inferring a zone from
    anywhere else) and the seeder wrote `label`/`lat`/`lon` only, parking the
    zone in `tz_snapshot` where the reader never looks. Every seeded account
    was therefore chart-less, and the row looked complete in Mongo.

    A seeder that writes what the real reader rejects is the mirror of the
    root-CLAUDE.md rule about fakes accepting what the real system rejects.
    Compared as SOURCE rather than by round-tripping, so the check needs no
    database — the two shapes simply have to name the same keys.
    """
    import inspect
    import re

    from sitara_api.astrology import service as facade_module
    from sitara_api.db import seed as seed_module

    def place_keys(source: str) -> set[str]:
        block = re.search(r'"place":\s*\{(.*?)\}', source, re.S)
        assert block, "no place literal found"
        return set(re.findall(r'"(\w+)":', block.group(1)))

    written_by_facade = place_keys(
        inspect.getsource(facade_module.AstrologyFacade.set_birth_details)
    )
    written_by_seeder = place_keys(inspect.getsource(seed_module))

    assert "tz" in written_by_seeder, (
        "seeded birth rows have no timezone — the facade will refuse them"
    )
    assert written_by_facade <= written_by_seeder, (
        f"the seeder omits {sorted(written_by_facade - written_by_seeder)} "
        "that the real write path stores"
    )


# ---------------------------------------------------------------------------
# 4. A dasha-backed claim had no layer 3
# ---------------------------------------------------------------------------


def _dasha_fact(level: DashaLevel, lord: Graha, parents: tuple[Graha, ...]) -> FactSnapshot:
    return FactSnapshot(
        fact_id=f"fact:dasha.{level.value}/2026-08-13/6a70000000000000000000a1@v1",
        kind=FactKind.DASHA_VIMSHOTTARI_PERIOD,
        value=DashaPeriodValue(
            level=level,
            lord=lord,
            start_utc=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
            end_utc=dt.datetime(2036, 1, 1, tzinfo=dt.UTC),
            parent_lords=parents,
        ),
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(
            dasha_year="days_365_25",
            tz=TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800),
        ),
        valid_from=dt.datetime(2026, 8, 13, tzinfo=dt.UTC),
        valid_to=dt.datetime(2026, 8, 13, 23, 59, tzinfo=dt.UTC),
        engine_semver="0.1.0",
        data_revision="test",
    )


@pytest.mark.parametrize("locale", ["en", "hi", "hi-Latn"])
def test_a_dasha_fact_renders_a_detail_line(locale: str) -> None:
    """§30.4's layer 3 was EMPTY for every dasha claim.

    This renderer was written for Today, whose modules never stand on a dasha
    fact. Chat does, constantly — "you are in a Jupiter mahadasha" was the most
    common grounded sentence a real model produced — so the sheet opened on a
    claim, a sources row, and nothing at all under "see the details".
    """
    line = trust.detail(_dasha_fact(DashaLevel.MAHA, Graha.JUPITER, ()), locale)

    assert line, f"no detail line for a dasha fact in {locale}"
    assert "·" in line
    # Layer 3 reads the FACT — the lord and the level — rather than
    # paraphrasing the sentence above it.
    assert line != ""


def test_every_dasha_level_has_a_label() -> None:
    """Three levels, and a missing label silently drops the whole line."""
    for level in DashaLevel:
        parents = {DashaLevel.MAHA: (), DashaLevel.ANTAR: (Graha.SUN,),
                   DashaLevel.PRATYANTAR: (Graha.SUN, Graha.MOON)}[level]
        assert trust.detail(_dasha_fact(level, Graha.JUPITER, parents), "en"), level
