"""Celery + Celery Beat on Redis (§6.1, §7.1, §23.7).

§6.1 chose Celery deliberately and wrote down what it chose it over: "NOT
chosen: … Temporal (Celery Beat + idempotent tasks cover morning fan-out;
re-evaluate if workflows grow stateful)". That sentence is a constraint on this
file — every task here must be safe to run twice, because "idempotent tasks" is
half of the reason there is no workflow engine underneath them.

Queues are per §23.7: "Dedicated Celery queues per class (T > D > C > M
priority)". The morning wave is Class D — it is the daily loop — and the
generation work is split from the delivery work so a WhatsApp BSP slowdown
cannot back up brief composition behind it.

The Beat schedule is §7.1's three clocks:

* every 15 minutes — the generation wave;
* every 30 minutes — the panchang pre-job, catching whichever zones have just
  passed 00:30 local;
* nightly — memory consolidation (diagram 8).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import Celery
from kombu import Queue

from sitara_api.config import Settings
from sitara_api.daily_guidance.panchang_prejob import PREJOB_TICK_MINUTES
from sitara_api.daily_guidance.windows import TICK_MINUTES

logger = logging.getLogger(__name__)

# --- queues (§23.7) --------------------------------------------------------
# Celery/Redis priorities are per-queue via `queue_order_strategy`; the numeric
# priorities below are the intent, and the worker's `-Q` ordering is what
# enforces it operationally. Both are stated so neither can drift alone.

QUEUE_TRANSACTIONAL = "notify.t"
QUEUE_DAILY = "notify.d"
QUEUE_CONTEXTUAL = "notify.c"
QUEUE_MARKETING = "notify.m"
#: §7.1's generation queues, split from delivery. Paying before trial, so a
#: queue-depth breach spends the §7.1 cost lever on the least-committed briefs.
QUEUE_BRIEF_PAYING = "brief.paying"
QUEUE_BRIEF_TRIAL = "brief.trial"
#: Everything that is neither a user's morning nor a user's notification.
QUEUE_MAINTENANCE = "maintenance"

TASK_QUEUES = (
    Queue(QUEUE_TRANSACTIONAL, queue_arguments={"x-max-priority": 10}),
    Queue(QUEUE_BRIEF_PAYING, queue_arguments={"x-max-priority": 8}),
    Queue(QUEUE_BRIEF_TRIAL, queue_arguments={"x-max-priority": 6}),
    Queue(QUEUE_DAILY, queue_arguments={"x-max-priority": 6}),
    Queue(QUEUE_CONTEXTUAL, queue_arguments={"x-max-priority": 4}),
    Queue(QUEUE_MARKETING, queue_arguments={"x-max-priority": 2}),
    Queue(QUEUE_MAINTENANCE, queue_arguments={"x-max-priority": 1}),
)


def build_celery(settings: Settings | None = None) -> Celery:
    """The app. Built by a function so tests get a fresh one with `task_always_eager`."""
    settings = settings or Settings()
    app = Celery("sitara", broker=settings.redis_url, backend=None)

    app.conf.update(
        task_queues=TASK_QUEUES,
        task_default_queue=QUEUE_MAINTENANCE,
        task_serializer="json",
        accept_content=["json"],
        result_backend=None,
        timezone="UTC",
        enable_utc=True,
        # §7.1's morning is a wall-clock deadline, so a task that outlives its
        # own relevance is worse than a task that dies: a brief still composing
        # at 08:30 has missed the appointment it was for.
        task_soft_time_limit=240,
        task_time_limit=300,
        # §6.1's "idempotent tasks" — late ack means a worker that dies
        # mid-brief hands the work back rather than losing someone's morning,
        # and §32.13's unique index makes the redelivery harmless.
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # §7.1: "Retries: 3× exponential".
        task_annotations={
            "*": {"max_retries": 3, "retry_backoff": True, "retry_jitter": True}
        },
        beat_schedule=beat_schedule(),
    )
    return app


def beat_schedule() -> dict[str, dict]:
    """§7.1's clocks. Every entry names the section that sets its period."""
    return {
        # §7.1: "Celery Beat ticks every 15 min".
        "morning-wave-tick": {
            "task": "sitara.daily_guidance.wave_tick",
            "schedule": timedelta(minutes=TICK_MINUTES),
            "options": {"queue": QUEUE_MAINTENANCE, "expires": TICK_MINUTES * 60},
        },
        # §7.1: "a global pre-job at 00:30 local-region time". Fired every half
        # hour; the task itself works out which zones have just turned over.
        "panchang-prejob": {
            "task": "sitara.daily_guidance.panchang_prejob",
            "schedule": timedelta(minutes=PREJOB_TICK_MINUTES),
            "options": {"queue": QUEUE_MAINTENANCE, "expires": PREJOB_TICK_MINUTES * 60},
        },
        # Diagram 8: "Nightly consolidation: dedupe · decay stale · theme
        # extraction". 02:30 UTC is 08:00 IST — deliberately AFTER the Indian
        # morning wave rather than before it, so consolidation never competes
        # with the spike §7.1 spends its whole design smoothing.
        "memory-consolidation": {
            "task": "sitara.memory.consolidate",
            "schedule": timedelta(days=1),
            "options": {"queue": QUEUE_MAINTENANCE, "expires": 6 * 3600},
        },
    }


#: The module-level app Celery's CLI imports:
#:     celery -A sitara_api.scheduling.celery_app:app worker -Q brief.paying,brief.trial,notify.d
#:     celery -A sitara_api.scheduling.celery_app:app beat
app = build_celery()
