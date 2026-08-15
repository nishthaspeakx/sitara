"""One place that assembles §23's service (§6.3).

`daily_guidance/wiring.py` for notifications, and it exists for the same
reason: the app factory, the Celery worker and the acceptance harness all need
an identically-wired service, and three call sites each constructing one is
three places for a store to be swapped for a fake or a channel to be quietly
left out.

The one thing worth knowing: this returns a service even when NO channel is
configured. A deployment with no VAPID key and no reachable SMTP host still
runs every §23 gate — quiet hours, the caps, the catalogue, the ledger — and
then records a `failed` row saying it could not reach anybody. That is the
honest behaviour and it is also the testable one: §23's rules are the product,
and the channels are how the result leaves the building.
"""

from __future__ import annotations

from sitara_api.config import Settings
from sitara_api.notifications.emergency_stop import EmergencyStop
from sitara_api.notifications.ladder import Dedupe
from sitara_api.notifications.providers.registry import build_adapters
from sitara_api.notifications.service import NotificationService, RecipientResolver
from sitara_api.notifications.store import (
    NotificationStore,
    PreferenceStore,
    PushSubscriptionStore,
)


def build_service(db, redis, settings: Settings | None = None) -> NotificationService:  # noqa: ANN001
    """§23's send path, fully wired."""
    settings = settings or Settings()
    subscriptions = PushSubscriptionStore(db)
    return NotificationService(
        store=NotificationStore(db),
        preferences=PreferenceStore(db, redis),
        subscriptions=subscriptions,
        adapters=build_adapters(settings),
        dedupe=Dedupe(redis),
        emergency_stop=EmergencyStop(redis),
        recipients=RecipientResolver(db, subscriptions),
    )
