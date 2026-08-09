"""Celery + Celery Beat (§6.1) — schedules and queues, nothing else.

The tasks in here are shells around `daily_guidance` and `memory`; the work is
testable without a broker, and this package is testable without a database.

    celery -A sitara_api.scheduling.celery_app:app beat
    celery -A sitara_api.scheduling.celery_app:app worker -Q brief.paying,brief.trial
    celery -A sitara_api.scheduling.celery_app:app worker -Q maintenance
"""

from sitara_api.scheduling.celery_app import app, beat_schedule, build_celery

__all__ = ["app", "beat_schedule", "build_celery"]
