"""Build the channel adapters from configuration (§23.3, §6.3).

`payments/providers/registry.py` and `voice/providers/registry.py` for
delivery, and it keeps the rule both of them keep: **an unconfigured provider
is None, not an exception.**

§8's degradation ladder is why. A deployment with no VAPID key has no push
channel — and §23.3's ladder is built for exactly that, so it delivers the same
messages by email and says so once in a log. Refusing to boot would turn a
missing optional key into an outage of the entire API, including the surfaces
that have nothing to do with notifications.

The one thing this file will NOT do is substitute. There is no fake push
adapter, no "log it instead" channel, no in-memory collector standing in for
SMTP. A channel that is not configured is absent from the adapter map, so
`ladder.build` never offers it as a rung and §23.8 reports what actually
happened. A stand-in would make an unconfigured deployment look like a working
one right up until somebody checked their phone.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from sitara_schemas.notifications import NotificationChannel

from sitara_api.config import Settings
from sitara_api.notifications.providers.base import NotificationChannelAdapter
from sitara_api.notifications.providers.email_smtp import SmtpChannel, SmtpConfig
from sitara_api.notifications.providers.routing import Support, resolve
from sitara_api.notifications.providers.webpush import VapidKeypair, WebPushChannel

logger = logging.getLogger(__name__)


def build_adapters(
    settings: Settings,
) -> Mapping[NotificationChannel, NotificationChannelAdapter]:
    """Every channel this deployment can actually carry.

    Consults `routing.resolve` FIRST for each channel, so the capability matrix
    is what decides — not the presence of a config value. That ordering is what
    makes WhatsApp's DECLARED cell mean something: if someone later adds
    WhatsApp credentials to the environment, this still builds nothing, because
    the matrix says there is no adapter. Configuration cannot promote a channel
    the code has not implemented.
    """
    adapters: dict[NotificationChannel, NotificationChannelAdapter] = {}

    if resolve(NotificationChannel.PUSH).support is Support.IMPLEMENTED:
        keypair = _load_vapid(settings)
        if keypair is not None:
            adapters[NotificationChannel.PUSH] = WebPushChannel(keypair)
        else:
            logger.warning(
                "web push is UNCONFIGURED — no VAPID keypair at %s. §23.3's ladder "
                "will carry daily-loop messages on email instead. Generate one with "
                "`uv run python -m sitara_api.notifications.vapid --generate`.",
                settings.vapid_key_path or "(vapid_key_path unset)",
            )

    if resolve(NotificationChannel.EMAIL).support is Support.IMPLEMENTED:
        adapters[NotificationChannel.EMAIL] = SmtpChannel(
            SmtpConfig(
                host=settings.notifications_smtp_host,
                port=settings.notifications_smtp_port,
                from_address=settings.notifications_smtp_from,
                from_name=settings.notifications_smtp_from_name,
                username=settings.notifications_smtp_username,
                password=settings.notifications_smtp_password,
                starttls=settings.notifications_smtp_starttls,
                timeout=settings.notifications_smtp_timeout_seconds,
            )
        )

    # WhatsApp is deliberately absent and there is no branch for it here.
    # `resolve` returns DECLARED, the `if` above it does not exist, and
    # `whatsapp.py`'s constructor raises — three guards, and the one that
    # matters is that no code path in this file can produce one.

    return adapters


def _load_vapid(settings: Settings) -> VapidKeypair | None:
    path = vapid_path(settings)
    if path is None or not path.exists():
        return None
    try:
        return VapidKeypair.load(path)
    except (ValueError, KeyError, OSError) as exc:
        # A malformed key file is a configuration error and it fails the same
        # way an absent one does: push is unavailable, the ladder falls back,
        # and the log says which. Raising here would take the API down over a
        # channel §23.3 already knows how to live without.
        logger.error(
            "VAPID keypair at %s is unreadable (%s) — push is unavailable",
            path,
            type(exc).__name__,
        )
        return None


def vapid_path(settings: Settings) -> Path | None:
    """Where the keypair lives.

    Defaults to `.secrets/vapid.json` beside the Firebase service account —
    the directory the compose stack already mounts read-only and `.gitignore`
    already covers. A default rather than a required setting because a
    developer who runs the generator should get a working push channel without
    also editing `.env`; an explicit path still wins.
    """
    if settings.vapid_key_path:
        return Path(settings.vapid_key_path)
    return Path(__file__).resolve().parents[4] / ".secrets" / "vapid.json"
