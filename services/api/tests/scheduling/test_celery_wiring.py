"""Celery + Beat wiring (§6.1, §7.1, §23.7).

These tests read configuration, not behaviour — the work is tested in
`daily_guidance` and `memory`, without a broker. What is worth asserting here
is that the schedule says what §7.1 says, because a Beat entry with the wrong
period is a defect nothing else in the suite can see: every task still passes,
and the morning simply arrives at the wrong time or not at all.
"""

from __future__ import annotations

from datetime import timedelta

from sitara_api.daily_guidance.panchang_prejob import PREJOB_TICK_MINUTES
from sitara_api.daily_guidance.windows import TICK_MINUTES
from sitara_api.scheduling.celery_app import (
    QUEUE_BRIEF_PAYING,
    QUEUE_BRIEF_TRIAL,
    QUEUE_CONTEXTUAL,
    QUEUE_DAILY,
    QUEUE_MAINTENANCE,
    QUEUE_MARKETING,
    QUEUE_TRANSACTIONAL,
    TASK_QUEUES,
    beat_schedule,
    build_celery,
)


def test_the_wave_ticks_every_fifteen_minutes() -> None:
    """§7.1: "Celery Beat ticks every 15 min"."""
    entry = beat_schedule()["morning-wave-tick"]
    assert entry["schedule"] == timedelta(minutes=15)
    assert TICK_MINUTES == 15
    assert entry["task"] == "sitara.daily_guidance.wave_tick"


def test_a_wave_tick_expires_before_the_next_one() -> None:
    """A tick that ran late would select a window the next tick already owns,
    and the two would fight over the same users."""
    entry = beat_schedule()["morning-wave-tick"]
    assert entry["options"]["expires"] == TICK_MINUTES * 60


def test_the_panchang_prejob_runs_often_enough_to_catch_every_zone() -> None:
    """§7.1's pre-job is at 00:30 LOCAL-REGION time, so the entry has to fire
    often enough that no zone's midnight slips between two runs. Half-hourly
    matches the half-hour offsets that exist (+05:30, +05:45)."""
    entry = beat_schedule()["panchang-prejob"]
    assert entry["schedule"] == timedelta(minutes=PREJOB_TICK_MINUTES)
    assert PREJOB_TICK_MINUTES <= 30


def test_memory_consolidation_is_nightly() -> None:
    """Diagram 8: "Nightly consolidation: dedupe · decay stale · theme
    extraction"."""
    entry = beat_schedule()["memory-consolidation"]
    assert entry["schedule"] == timedelta(days=1)
    assert entry["task"] == "sitara.memory.consolidate"
    # Maintenance, never a brief queue: consolidation must not compete with
    # the IST spike §7.1 spends its whole design smoothing.
    assert entry["options"]["queue"] == QUEUE_MAINTENANCE


def test_every_scheduled_task_names_a_queue() -> None:
    declared = {queue.name for queue in TASK_QUEUES}
    for name, entry in beat_schedule().items():
        queue = entry["options"]["queue"]
        assert queue in declared, f"{name} routes to an undeclared queue {queue!r}"


def _priorities() -> dict[str, int]:
    """Kombu types `queue_arguments` loosely; read it the way the broker does."""
    return {
        queue.name: getattr(queue, "queue_arguments", {})["x-max-priority"]
        for queue in TASK_QUEUES
    }


def test_the_queue_priorities_are_23_7s_ordering() -> None:
    """§23.7: "Dedicated Celery queues per class (T > D > C > M priority)"."""
    priority = _priorities()
    assert priority[QUEUE_TRANSACTIONAL] > priority[QUEUE_DAILY]
    assert priority[QUEUE_DAILY] > priority[QUEUE_CONTEXTUAL]
    assert priority[QUEUE_CONTEXTUAL] > priority[QUEUE_MARKETING]


def test_paying_briefs_outrank_trial_briefs() -> None:
    """§7.1: "Priority queues: paying users > trial > dormant". Dormant has no
    queue at all — it is not a lower priority, it is not enqueued."""
    priority = _priorities()
    assert priority[QUEUE_BRIEF_PAYING] > priority[QUEUE_BRIEF_TRIAL]
    assert not any("dormant" in queue.name for queue in TASK_QUEUES)


def test_tasks_ack_late_so_a_dead_worker_loses_nobodys_morning() -> None:
    """§6.1 rejected a workflow engine on the strength of "Celery Beat +
    idempotent tasks". Late ack is the other half of that bargain: redelivery
    is safe because §32.13's unique index makes it a no-op."""
    app = build_celery()
    assert app.conf.task_acks_late is True
    assert app.conf.worker_prefetch_multiplier == 1


def test_retries_are_three_times_exponential() -> None:
    """§7.1: "Retries: 3× exponential"."""
    app = build_celery()
    annotations = app.conf.task_annotations["*"]
    assert annotations["max_retries"] == 3
    assert annotations["retry_backoff"] is True


def test_a_task_cannot_outlive_the_morning_it_is_for() -> None:
    """A brief still composing at 08:30 has missed the appointment it was for;
    dying is better than arriving after the user has read the on-open one."""
    app = build_celery()
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit
    assert app.conf.task_time_limit <= 15 * 60


def test_the_app_runs_in_utc() -> None:
    """Every local-time decision in this system is made explicitly, from a
    user's own zone. A broker with a local timezone would add a second,
    invisible one."""
    app = build_celery()
    assert app.conf.enable_utc is True
    assert app.conf.timezone == "UTC"


def test_the_tasks_module_registers_what_beat_schedules() -> None:
    """A Beat entry naming a task nobody registered fails silently at 05:40."""
    from sitara_api.scheduling import tasks  # noqa: F401
    from sitara_api.scheduling.celery_app import app

    for name, entry in beat_schedule().items():
        assert entry["task"] in app.tasks, f"{name} schedules an unregistered task"
