"""The astrology facade (§6.3's "astrology (facade over sitara-astro + …)").

§13 is the reason this class exists rather than each caller talking to the
engine: birth details are reachable "only via the astrology facade (no generic
query path)". Everything that wants a chart fact comes through here, and this is
the only place in the service that decrypts a `birth_details` row.

Three things it does that the adapter deliberately does not:

* **Reads the birth row and narrows it.** CSFLE-encrypted field by field, then
  reduced to the five values the engine needs (`BirthInput`) — so the blast
  radius of an engine-adapter bug is those five and not the rectification
  notes.
* **Caches the natal chart in `charts`.** §7.2 makes `natal_chart:{subject}:
  {engine_v}:{ayanamsa}` permanent until an engine bump and §6.4 says "keep
  last 3 versions"; that is a store's job, and the adapter has no store. A
  natal chart is the same forever, so recomputing one per morning would be
  the single most wasteful call in the system.
* **Knows what a missing birth time means.** §5.3 forbids guessing; §28.2 has
  a "missing birth time" variant that asks for it. So thin data raises
  `InsufficientBirthData`, which the caller renders as a question, while an
  outage raises `ChartEngineUnavailable`, which the caller degrades around.
  Collapsing the two would either nag a user about an outage or hide a real
  gap behind a retry.

Transits are NOT cached here. §7.2's transit key is global by latitude band and
that cache belongs to `transit_cache`; what this serves is the per-user
transit-to-natal HOUSE assignment, which is derived from both and is cheap
beside the natal computation it depends on.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from sitara_schemas.facts import DashaPeriodValue, FactSnapshot

from sitara_api.astrology.chart_adapter import (
    AstroChartAdapter,
    BirthInput,
    ChartEngineUnavailable,
    InsufficientBirthData,
)
from sitara_api.db.documents import stamp, utcnow

logger = logging.getLogger(__name__)

#: §6.4: "recompute on engine bump; keep last 3 versions".
CHART_VERSIONS_KEPT = 3

#: §6.4 bounds the `charts` row: "computed facts (embedded — bounded ~40KB)".
#: That bound is why the dasha tree is not stored whole. The engine returns the
#: FULL vimshottari tree — 9 maha × 9 antar × 9 pratyantar = 819 periods, which
#: measures 817 KB beside a 26 KB natal chart, twenty times the row the spec
#: describes. Three of those periods are in effect at any instant, so the row
#: holds those and the window is refreshed when it stops covering `now`.
#:
#: Nothing is lost by this. §34.2 requires the artefact to embed the snapshot it
#: CITED, and a brief cites the period it spoke about; the deeper tree is a
#: recomputation away and is not the system of record for anything.
CHART_SIZE_BUDGET_BYTES = 40 * 1024


#: §10-6's four honest answers, and the only four. They are stored rather than
#: derived because "I know it to the half hour" and "I only know it was the
#: morning" both produce a time and mean different things — §5.4 renders a
#: different confidence state for each, and a `time` column alone cannot tell
#: them apart.
TIME_ACCURACY = ("exact", "approximate", "part_of_day", "unknown")

#: Where a part-of-day answer lands when the engine needs an instant. These are
#: MIDPOINTS of the named window, and they exist so that a part-of-day chart is
#: computed at a declared, reviewable point rather than at whatever the caller
#: felt like. They never upgrade the confidence state: a chart built on one of
#: these is `approximate` and says so (§5.4).
PART_OF_DAY_MIDPOINT = {
    "morning": dt.time(9, 0),
    "afternoon": dt.time(15, 0),
    "evening": dt.time(19, 0),
    "night": dt.time(0, 30),
}


@dataclass(frozen=True)
class BirthDetailsInput:
    """What S06 + S07 capture. The write-side mirror of `BirthInput`.

    Deliberately NOT the `birth_details` document either: the row also carries
    rectification notes (§30.2's P2 tease) that onboarding never writes, and
    keeping the write surface to what a screen collects is what stops a future
    caller reaching past the facade to set one.
    """

    date: dt.date
    place_label: str
    lat: float
    lon: float
    tz: str
    time_accuracy: str
    time: dt.time | None = None
    part_of_day: str | None = None

    def __post_init__(self) -> None:
        if self.time_accuracy not in TIME_ACCURACY:
            raise ValueError(f"time_accuracy must be one of {TIME_ACCURACY}")
        # §5.3: we never guess at what we were not told. "exact" without a time
        # is a caller bug, and admitting it would produce a chart claiming a
        # precision nobody supplied.
        if self.time_accuracy in ("exact", "approximate") and self.time is None:
            raise ValueError(f"{self.time_accuracy} birth time requires a time")
        if self.time_accuracy == "part_of_day" and self.part_of_day not in PART_OF_DAY_MIDPOINT:
            raise ValueError("part_of_day must name one of the four windows")

    @property
    def effective_time(self) -> dt.time | None:
        """The instant the engine is given, or None for an unknown time.

        `unknown` returns None on purpose — §5.4's "no exact time" state reads
        the Moon chart, and substituting noon here would hand the engine a
        lagna it has no basis for while every downstream confidence chip went
        on saying `verified`.
        """
        if self.time_accuracy == "unknown":
            return None
        if self.time_accuracy == "part_of_day":
            return PART_OF_DAY_MIDPOINT[self.part_of_day or ""]
        return self.time


@dataclass(frozen=True)
class ChartBundle:
    """Everything the chart engine could say about one subject on one date."""

    natal: tuple[FactSnapshot, ...] = ()
    dasha: tuple[FactSnapshot, ...] = ()
    transits: tuple[FactSnapshot, ...] = ()
    #: True when the natal half came from `charts` rather than the engine.
    natal_cached: bool = False

    @property
    def all(self) -> tuple[FactSnapshot, ...]:
        return (*self.natal, *self.dasha, *self.transits)


def _subject_query(subject_id: str) -> dict[str, Any]:
    """Find the birth row for a SUBJECT — an account holder or a family member.

    Two bugs lived in the single-clause query this replaces, and the second is
    the serious one.

    **A family member's chart could never resolve.** `astrology/router.py` passes
    `subject_id` for §32.15's members, and their row is stored with
    `user_id` = the OWNER and `family_member_id` = the member. Looking up
    `{"user_id": member_id}` matches nothing, so S28 — the first product surface
    that draws CC-007's kundli — declined for every family member with
    ASTRO_INSUFFICIENT_BIRTH_DATA while the screen said "Birth details on file"
    one line above it.

    **And the account-holder's own lookup could return a FAMILY MEMBER's row.**
    `{"user_id": owner}` matches every row that user owns, their mother's
    included, and `find_one` with no sort returns natural order. An account with
    one family member could be shown their mother's chart as their own — with
    every confidence chip reading `verified`, because the row IS complete and IS
    theirs to hold. Nothing about it looks wrong. It had never fired only
    because nothing had ever written birth details for a family member.

    So the own-branch pins `family_member_id: None` — which is what the WRITE
    path has always scoped to; only the read was ambiguous. An id is either a
    user id or a member id and never both, which is what makes one query safe
    for both.
    """
    oid = ObjectId(subject_id)
    return {
        "$or": [
            {"user_id": oid, "family_member_id": None},
            {"family_member_id": oid},
        ]
    }


class AstrologyFacade:
    def __init__(
        self,
        *,
        db: Any,
        adapter: AstroChartAdapter,
        crypto: Any | None = None,
        engine_semver: str = "0.1.0",
        ayanamsa: str = "lahiri",
    ) -> None:
        self._db = db
        self._adapter = adapter
        self._crypto = crypto
        self._engine_semver = engine_semver
        self._ayanamsa = ayanamsa

    # -- birth details (§13's single door) ---------------------------------

    async def birth_input(self, user_id: str) -> BirthInput | None:
        """Decrypt one user's birth row and narrow it. None when there is none.

        None rather than raising: "this user has not entered their birth
        details" is an ordinary state on the way through onboarding (§10-6),
        not an error, and §28.2 has a screen for it.
        """
        from sitara_api.db.registry import BY_NAME

        doc = await self._db.birth_details.find_one(_subject_query(user_id))
        if doc is None:
            return None
        if self._crypto is not None:
            doc = await self._crypto.decrypt_document(BY_NAME["birth_details"], doc)

        place = doc.get("place") or {}
        if not doc.get("date") or not place.get("tz"):
            # A row without a date or a zone cannot produce a chart, and §5.2
            # forbids inferring a timezone from anywhere but the stored place.
            logger.warning("birth row incomplete", extra={"user_id": user_id})
            return None

        raw_time = doc.get("time")
        return BirthInput(
            date=_as_date(doc["date"]),
            time=_as_time(raw_time),
            place_name=place.get("name") or place.get("label") or "",
            lat=float(place["lat"]),
            lon=float(place["lon"]),
            tz=place["tz"],
            fold=doc.get("fold"),
        )

    async def time_accuracy(self, user_id: str) -> str:
        """The STORED accuracy of a subject's birth time (§30.2, §5.4).

        On the facade rather than read from `BirthInput`, because `BirthInput`
        is narrowed to the five fields the ENGINE needs and accuracy is not one
        of them — the engine computes the same chart from a time whether or not
        anyone is confident in it.

        Inferring accuracy from whether a time exists would be wrong in the one
        direction that matters: §30.2 stores a WINDOW for an approximate time,
        so an approximate row HAS a time, and a chart built from it would be
        labelled `verified` while resting on a guessed ascendant. §5.4 exists
        to prevent exactly that.

        `unknown` when there is no row, no stored accuracy, or a value nobody
        declared — the honest direction, since every unknown lands in
        Moon-chart mode rather than in a confident diamond.
        """
        from sitara_api.db.registry import BY_NAME

        doc = await self._db.birth_details.find_one(_subject_query(user_id))
        if doc is None:
            return "unknown"
        if self._crypto is not None:
            doc = await self._crypto.decrypt_document(BY_NAME["birth_details"], doc)
        accuracy = doc.get("time_accuracy")
        return accuracy if accuracy in TIME_ACCURACY else "unknown"

    async def set_birth_details(self, user_id: str, details: BirthDetailsInput) -> None:
        """Write one user's birth row. The ONLY write path there is.

        This belongs on the facade for the same reason `birth_input` does. §6.4
        says `birth_details` is "reachable only through the astrology facade, no
        generic query path", and a write helper on a repository would BE that
        generic path — the read door would be guarded while the write door
        stood open beside it, sharing a collection and a key class.

        Two things happen here that a plain upsert would not do, and both are
        §30.2's "correcting birth details" rule rather than convenience:

        * the row is encrypted through the same `birth_details` codec the read
          side decrypts with, so a field added to the registry is covered
          without this method changing;
        * every cached `charts` row for the subject is dropped. A chart is
          derived data with a permanent §7.2 key; leaving it in place after the
          birth time changed would serve a stale chart forever, and "forever" is
          exactly how long the key says it is valid for.

        Guidance already written is deliberately NOT touched — §30.2: "Your
        guidance history stays as written; new guidance uses the corrected chart
        from now." The §34.2 snapshot embedded in each artefact is what keeps
        that honest rather than merely tolerable.
        """
        from sitara_api.db.registry import BY_NAME

        subject = ObjectId(user_id)
        document = stamp(
            {
                "user_id": subject,
                "family_member_id": None,
                "date": details.date.isoformat(),
                "time": details.effective_time.isoformat() if details.effective_time else None,
                "time_accuracy": details.time_accuracy,
                "place": {
                    "name": details.place_label,
                    "label": details.place_label,
                    "lat": details.lat,
                    "lon": details.lon,
                    "tz": details.tz,
                },
                # §5.2: the zone is captured AT ENTRY, not looked up later. A
                # tzdb update that moves a historical offset must not silently
                # move someone's chart out from under the reading they were
                # given.
                "tz_snapshot": {
                    "tz": details.tz,
                    "resolved_at": utcnow().isoformat(),
                    "source": "gazetteer",
                },
                "rectification_notes": None,
            }
        )
        if self._crypto is not None:
            document = await self._crypto.encrypt_document(BY_NAME["birth_details"], document)
        created_at = document.pop("created_at")
        await self._db.birth_details.update_one(
            {"user_id": subject, "family_member_id": None},
            {"$set": document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )
        # Derived data outlives its source unless something removes it.
        await self._db.charts.delete_many({"subject_id": subject})
        logger.info(
            "birth details written",
            # §13: the accuracy is a category, not a birth detail. The date,
            # the time and the place are never logged, here or anywhere.
            extra={"user_id": user_id, "time_accuracy": details.time_accuracy},
        )

    # -- the chart ---------------------------------------------------------

    async def chart_for(
        self,
        user_id: str,
        *,
        local_date: str,
        timezone: str,
        chart_version: int = 1,
        include_transits: bool = True,
    ) -> ChartBundle:
        """Natal + dasha + today's transits for one user, cached where §7.2 says.

        `local_date` is the USER's calendar date and `timezone` their zone; the
        transit date is derived from both. Passing `date.today()` instead would
        compute a Kolkata brief against London's date for five and a half hours
        of every day.
        """
        birth = await self.birth_input(user_id)
        if birth is None:
            raise InsufficientBirthData("no birth details on file")

        now = _local_noon(local_date, timezone)
        natal, cached = await self._natal_with_cache(
            user_id, birth, chart_version=chart_version, now=now
        )

        transits: tuple[FactSnapshot, ...] = ()
        if include_transits:
            on = _transit_date(local_date, timezone)
            transits = tuple(
                await self._adapter.transits(
                    birth, on, subject=user_id, chart_version=chart_version
                )
            )

        return ChartBundle(
            natal=tuple(f for f in natal if not _is_dasha(f)),
            dasha=tuple(f for f in natal if _is_dasha(f)),
            transits=transits,
            natal_cached=cached,
        )

    async def _natal_with_cache(
        self, user_id: str, birth: BirthInput, *, chart_version: int, now: dt.datetime
    ) -> tuple[list[FactSnapshot], bool]:
        """The natal chart, cached permanently; the dasha window, refreshed.

        Two lifetimes in one row, which is why this is not a single cache hit:

        * The natal half is fixed at birth and dies only on an engine bump —
          §7.2's `natal_chart:{subject}:{engine_v}:{ayanamsa}` exactly.
        * The dasha half is a WINDOW on a tree, and the window moves. A cached
          row whose periods no longer contain `now` is not stale data to be
          served, it is a miss on that half alone.

        So a cached row with a live window is a full hit; a cached row with a
        dead window refetches the dasha and keeps the natal chart it already
        had, which is the expensive half.
        """
        cached = await self._read_chart(user_id)
        if cached is not None:
            natal = [f for f in cached if not _is_dasha(f)]
            if _live_dasha(cached, now):
                return cached, True
            logger.info("dasha window expired — refreshing", extra={"user_id": user_id})
            refreshed = natal + await self._dasha_window(
                birth, user_id, chart_version=chart_version, now=now
            )
            await self._write_chart(user_id, refreshed)
            return refreshed, False

        natal = await self._adapter.natal(
            birth, subject=user_id, chart_version=chart_version
        )
        facts = natal + await self._dasha_window(
            birth, user_id, chart_version=chart_version, now=now
        )
        await self._write_chart(user_id, facts)
        return facts, False

    async def _dasha_window(
        self, birth: BirthInput, user_id: str, *, chart_version: int, now: dt.datetime
    ) -> list[FactSnapshot]:
        """The maha/antar/pratyantar periods in effect, and nothing else.

        A chart without its dasha is still a chart: the modules that need one
        simply are not emitted (§5.3), which is the right shape for "we could
        not compute this" rather than a failed brief.
        """
        try:
            tree = await self._adapter.dasha(
                birth, subject=user_id, chart_version=chart_version
            )
        except ChartEngineUnavailable:
            logger.warning("dasha unavailable — serving natal alone")
            return []
        return _live_dasha(tree, now)

    async def _read_chart(self, user_id: str) -> list[FactSnapshot] | None:
        from sitara_api.db.registry import BY_NAME

        # §7.2's key is `natal_chart:{subject}:{engine_v}:{ayanamsa}` — all
        # four parts. Reading on engine_version alone would serve a Lahiri
        # chart to a deployment that had switched ayanamsa without bumping the
        # engine, and every house in it would be quietly wrong.
        doc = await self._db.charts.find_one(
            {
                "subject_id": ObjectId(user_id),
                "engine_version": self._engine_semver,
                "ayanamsa": self._ayanamsa,
            }
        )
        if doc is None:
            return None
        if self._crypto is not None:
            doc = await self._crypto.decrypt_document(BY_NAME["charts"], doc)
        facts = doc.get("facts") or []
        try:
            return [FactSnapshot.model_validate(f) for f in facts]
        except Exception:  # noqa: BLE001
            # A row we cannot parse is a row from a shape we no longer speak.
            # Recomputing is cheap and correct; serving a half-parsed chart is
            # neither. §34.2's snapshot rule protects ARTEFACTS, not this cache.
            logger.warning("unreadable chart cache — recomputing")
            return None

    async def _write_chart(self, user_id: str, facts: list[FactSnapshot]) -> None:
        from sitara_api.db.registry import BY_NAME

        payload = [f.model_dump(mode="json") for f in facts]
        size = len(json.dumps(payload).encode("utf-8"))
        if size > CHART_SIZE_BUDGET_BYTES:
            # §6.4 says "bounded ~40KB" and this is the only place that can
            # break the bound. Loud rather than silent: a row that grew past it
            # is a shape change (the engine started returning a whole tree
            # again), and the fix belongs here, not in a larger budget.
            logger.error(
                "chart row exceeds the §6.4 size bound — refusing to store",
                extra={"user_id": user_id, "bytes": size, "facts": len(facts)},
            )
            return

        subject = ObjectId(user_id)
        document = stamp(
            {
                "subject_id": subject,
                "engine_version": self._engine_semver,
                "ayanamsa": self._ayanamsa,
                "facts": payload,
                "fact_ids": [f.fact_id for f in facts],
                # §5.5's golden-set parity is a RELEASE gate over the engine,
                # not a per-user claim. An unadjudicated row says so.
                "parity_status": "unverified",
            }
        )
        if self._crypto is not None:
            document = await self._crypto.encrypt_document(BY_NAME["charts"], document)
        created_at = document.pop("created_at")
        await self._db.charts.update_one(
            {
                "subject_id": subject,
                "engine_version": self._engine_semver,
                "ayanamsa": self._ayanamsa,
            },
            {"$set": document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )
        await self._prune_chart_versions(subject)

    async def _prune_chart_versions(self, subject: ObjectId) -> None:
        """§6.4: "keep last 3 versions". Prose retention, so a job does it —
        a TTL index here would delete by age rather than by version count."""
        cursor = (
            self._db.charts.find({"subject_id": subject}, {"engine_version": 1})
            .sort("created_at", -1)
            .skip(CHART_VERSIONS_KEPT)
        )
        stale = [doc["_id"] async for doc in cursor]
        if stale:
            await self._db.charts.delete_many({"_id": {"$in": stale}})


# ---------------------------------------------------------------------------
# Coercion — the birth row stores strings, the engine wants dates
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _as_time(value: Any) -> dt.time | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.time()
    if isinstance(value, dt.time):
        return value
    return dt.time.fromisoformat(str(value))


def _transit_date(local_date: str, timezone: str) -> dt.date:
    """The UTC date the user's local date is anchored to.

    Noon local rather than midnight: midnight in a +14 zone is the previous UTC
    day, so anchoring there would compute a Kiritimati morning against
    yesterday's sky. Noon is inside the local day in every zone tzdb has.
    """
    date = dt.date.fromisoformat(local_date)
    noon_local = dt.datetime(
        date.year, date.month, date.day, 12, 0, tzinfo=ZoneInfo(timezone)
    )
    return noon_local.astimezone(dt.UTC).date()


def _is_dasha(fact: FactSnapshot) -> bool:
    return fact.kind.value.startswith("dasha.")


def _live_dasha(facts: Sequence[FactSnapshot], now: dt.datetime) -> list[FactSnapshot]:
    """The dasha periods containing `now` — maha, antar and pratyantar.

    Three of 819. The tree is complete and enormous; what any surface actually
    says is "you are in a Venus-Saturn period", which is this.
    """
    out: list[FactSnapshot] = []
    for fact in facts:
        if not _is_dasha(fact):
            continue
        value = fact.value
        if isinstance(value, DashaPeriodValue) and value.start_utc <= now < value.end_utc:
            out.append(fact)
    return out


def _local_noon(local_date: str, timezone: str) -> dt.datetime:
    """Midday on the user's local date, as an instant.

    The dasha window is asked "which period is this person in?", and the honest
    answer for a whole local date is the one that holds in the middle of it —
    not at the instant a worker happened to run, which for a 05:40 wave is the
    previous day in a westward zone.
    """
    date = dt.date.fromisoformat(local_date)
    return dt.datetime(
        date.year, date.month, date.day, 12, 0, tzinfo=ZoneInfo(timezone)
    ).astimezone(dt.UTC)
