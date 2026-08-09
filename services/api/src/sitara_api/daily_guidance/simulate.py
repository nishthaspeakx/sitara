"""Load-simulate the §7.1 morning wave and report its spread.

    "Load smoothing: waves spread across the 60-min lead window hashed by
    user_id; IST 07:00 is the global spike (≈60% of India users in one band)"

That sentence is a claim about a hash function, and a hash function's behaviour
on real inputs is not something to take on trust. This runs the REAL selector —
`windows.select_wave`, the same code the Beat tick calls — over a synthetic IST
population for a full day of 15-minute ticks, and prints what actually happened.

The population follows §7.1's own shape: ~60% at exactly 07:00 with the rest
spread over the morning, all in Asia/Kolkata. Every user id is a real ObjectId
hex string, because `lead_minutes` hashes the id and a simulation over
`user-0001`-style ids would be measuring a different input distribution than
production ever sees.

    uv run python -m sitara_api.daily_guidance.simulate
    uv run python -m sitara_api.daily_guidance.simulate --users 20000 --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass

from sitara_api.daily_guidance.types import BriefSubject, Density, Tier
from sitara_api.daily_guidance.windows import (
    LEAD_MAX_MINUTES,
    LEAD_MIN_MINUTES,
    TICK_MINUTES,
    select_wave,
    ticks_for_day,
)

IST = "Asia/Kolkata"

#: §7.1: "IST 07:00 is the global spike (≈60% of India users in one band)".
SPIKE_SHARE = 0.60
SPIKE_TIME = "07:00"

#: The other 40%, as brief times people actually pick from §23.5's picker.
#: Weighted towards the early morning, because that is what a morning-brief
#: product's preference distribution looks like — a flat spread would make the
#: smoothing look better than it is by never concentrating anywhere.
OTHER_TIMES: tuple[tuple[str, float], ...] = (
    ("05:30", 0.04),
    ("06:00", 0.08),
    ("06:30", 0.10),
    ("07:30", 0.06),
    ("08:00", 0.05),
    ("08:30", 0.03),
    ("09:00", 0.02),
    ("21:00", 0.02),
)


def synthetic_user_id(index: int) -> str:
    """A deterministic 24-hex ObjectId-shaped id.

    Deterministic so a run is reproducible, and ObjectId-shaped so the hash in
    `lead_minutes` sees the same character distribution it will see in
    production. Feeding it sequential integers would be measuring the hash's
    behaviour on a input space we never actually use.
    """
    return hashlib.blake2b(f"sim-user-{index}".encode(), digest_size=12).hexdigest()


def build_population(count: int) -> list[BriefSubject]:
    """`count` IST subjects shaped like §7.1's description."""
    subjects: list[BriefSubject] = []
    spike = int(count * SPIKE_SHARE)

    # The non-spike times are allocated by their relative weight so the tail
    # sums exactly to the remainder, whatever `count` is.
    tail = count - spike
    weights_total = sum(weight for _, weight in OTHER_TIMES)
    allocations: list[tuple[str, int]] = []
    assigned = 0
    for time, weight in OTHER_TIMES[:-1]:
        n = round(tail * weight / weights_total)
        allocations.append((time, n))
        assigned += n
    allocations.append((OTHER_TIMES[-1][0], max(0, tail - assigned)))

    index = 0
    for _ in range(spike):
        subjects.append(_subject(index, SPIKE_TIME))
        index += 1
    for time, n in allocations:
        for _ in range(n):
            subjects.append(_subject(index, time))
            index += 1
    return subjects


def _subject(index: int, brief_time: str) -> BriefSubject:
    # Tiers roughly as a beta cohort looks: mostly trial, some paying, a tail
    # of dormant. The dormant share matters to the result — §7.1 skips them, so
    # a simulation with none would overstate the wave's real size.
    modulo = index % 10
    if modulo < 2:
        tier = Tier.PAYING
    elif modulo < 8:
        tier = Tier.TRIAL
    else:
        tier = Tier.DORMANT
    return BriefSubject(
        user_id=synthetic_user_id(index),
        locale="hi" if index % 3 == 0 else "en",
        timezone=IST,
        brief_time=brief_time,
        density=Density.MED,
        tier=tier,
    )


@dataclass(frozen=True)
class SimulationResult:
    users: int
    generated: int
    dormant_skipped: int
    ticks: int
    per_tick: dict[str, int]
    spike_per_tick: dict[str, int]
    slot_histogram: dict[int, int]

    @property
    def busiest_tick(self) -> tuple[str, int]:
        return max(self.per_tick.items(), key=lambda kv: kv[1])

    @property
    def busiest_spike_tick(self) -> tuple[str, int]:
        return max(self.spike_per_tick.items(), key=lambda kv: kv[1])


def simulate(count: int = 5000, *, day: dt.date | None = None) -> SimulationResult:
    """Run a full day of ticks over a synthetic IST population."""
    subjects = build_population(count)
    spike_ids = {s.user_id for s in subjects if s.brief_time == SPIKE_TIME}

    # Start at IST midnight so the printed ticks read as an Indian day.
    from zoneinfo import ZoneInfo

    on = day or dt.date(2026, 8, 12)
    start = dt.datetime(on.year, on.month, on.day, 0, 0, tzinfo=ZoneInfo(IST)).astimezone(
        dt.UTC
    )

    per_tick: Counter[str] = Counter()
    spike_per_tick: Counter[str] = Counter()
    slots: Counter[int] = Counter()
    generated = 0
    dormant = 0
    seen: set[tuple[str, str]] = set()

    for tick in ticks_for_day(start):
        members, report = select_wave(subjects, tick)
        label = tick.astimezone(ZoneInfo(IST)).strftime("%H:%M")
        per_tick[label] = len(members)
        dormant = report.skipped_dormant  # identical every tick; the last is fine
        for member in members:
            generated += 1
            slots[member.slot_minutes] += 1
            if member.subject.user_id in spike_ids:
                spike_per_tick[label] += 1
            key = (member.subject.user_id, member.local_date)
            if key in seen:
                raise AssertionError(
                    f"§32.13 violated in simulation: {key} selected twice in one day"
                )
            seen.add(key)

    return SimulationResult(
        users=count,
        generated=generated,
        dormant_skipped=dormant,
        ticks=len(per_tick),
        per_tick=dict(per_tick),
        spike_per_tick=dict(spike_per_tick),
        slot_histogram=dict(sorted(slots.items())),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _bar(value: int, peak: int, width: int = 44) -> str:
    if peak <= 0:
        return ""
    return "█" * max(1 if value else 0, round(width * value / peak))


def render(result: SimulationResult) -> str:
    lines: list[str] = []
    lines.append(
        f"§7.1 wave simulation — {result.users} IST users, "
        f"{TICK_MINUTES}-minute ticks, {result.ticks} ticks/day"
    )
    lines.append(
        f"  generated {result.generated} briefs; "
        f"{result.dormant_skipped} dormant skipped per tick (§7.1 on-open only)"
    )
    expected = result.users - result.dormant_skipped
    lines.append(
        f"  every eligible user generated exactly once: "
        f"{result.generated} == {expected} → {result.generated == expected}"
    )

    busy = [(k, v) for k, v in result.per_tick.items() if v]
    peak = max(v for _, v in busy) if busy else 0
    lines.append("")
    lines.append(f"Wave spread — briefs generated per tick (IST local, peak {peak}):")
    for label, value in sorted(busy):
        lines.append(f"  {label}  {str(value).rjust(5)}  {_bar(value, peak)}")

    spike = [(k, v) for k, v in result.spike_per_tick.items() if v]
    spike_peak = max(v for _, v in spike) if spike else 0
    spike_total = sum(v for _, v in spike)
    lines.append("")
    lines.append(
        f"The 07:00 band alone ({spike_total} users) — this is what §7.1's hash smooths:"
    )
    for label, value in sorted(spike):
        share = 100 * value / spike_total if spike_total else 0
        lines.append(
            f"  {label}  {str(value).rjust(5)}  {share:5.1f}%  {_bar(value, spike_peak)}"
        )
    lines.append(
        f"  without the hash all {spike_total} would land on one tick; "
        f"the busiest tick carries {spike_peak} "
        f"({100 * spike_peak / spike_total:.1f}%)"
    )

    lines.append("")
    lines.append(
        f"Lead-slot histogram — minutes ahead of brief_time "
        f"(§7.1 window {LEAD_MIN_MINUTES}–{LEAD_MAX_MINUTES}):"
    )
    slot_peak = max(result.slot_histogram.values()) if result.slot_histogram else 0
    buckets: Counter[str] = Counter()
    for slot, value in result.slot_histogram.items():
        buckets[f"{(slot // 10) * 10:>2}-{(slot // 10) * 10 + 9:>2} min"] += value
    for label, value in sorted(buckets.items()):
        lines.append(f"  {label}  {str(value).rjust(5)}  {_bar(value, max(buckets.values()))}")
    lines.append(
        f"  slots occupied: {len(result.slot_histogram)}/{LEAD_MAX_MINUTES - LEAD_MIN_MINUTES}"
        f"  ·  min/max per slot: "
        f"{min(result.slot_histogram.values(), default=0)}/{slot_peak}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="§7.1 morning-wave load simulation")
    parser.add_argument("--users", type=int, default=5000)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    result = simulate(args.users)
    if args.json:
        print(
            json.dumps(
                {
                    "users": result.users,
                    "generated": result.generated,
                    "dormant_skipped": result.dormant_skipped,
                    "per_tick": result.per_tick,
                    "spike_per_tick": result.spike_per_tick,
                    "slot_histogram": result.slot_histogram,
                },
                indent=2,
            )
        )
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
