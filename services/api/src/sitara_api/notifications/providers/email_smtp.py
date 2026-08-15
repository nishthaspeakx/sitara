"""§23.3's email rung, over ordinary SMTP.

    "Email: SES with per-class configuration sets, one-click unsubscribe
     headers (List-Unsubscribe) on Class M, never on Class T."

── Why SMTP and not an SES client ──────────────────────────────────────────

SES speaks SMTP. So does Mailpit, which is what this prototype runs against —
a real SMTP server in a container that accepts real messages and shows them in
a real inbox at http://localhost:8025. There is no account, no verified sender
and no sandbox to be let out of, and the adapter is unchanged when the host
becomes SES: `notifications_smtp_host`, a port, and credentials §13 keeps in
Secrets Manager.

That is a materially different situation from §30.3's payment rails, and the
difference is worth being explicit about because both are "swap the endpoint":
a payment rail's swap changes the legal posture of the transaction, so it is
DECLARED and gated. An SMTP host's swap changes who relays the bytes. The
protocol here is genuinely exercised end to end, so this cell is IMPLEMENTED
rather than declared, and the release gate names WhatsApp alone.

── The two headers that are not decoration ─────────────────────────────────

**`List-Unsubscribe` + `List-Unsubscribe-Post`** are §23.3's "one-click", and
they go on Class M only. `classes.policy(...).unsubscribe_header` decides,
never this file and never a caller — an unsubscribe header on an OTP mail
invites someone to unsubscribe from the thing that lets them sign in, and some
clients act on the header without asking the reader first.

**The per-class configuration set** is SES's mechanism for keeping one class's
reputation away from another's. It rides as a header here (`X-SES-CONFIGURATION-SET`),
which SES reads and Mailpit ignores, so the production shape is exercised
locally rather than added later by someone reading §23.3 for the first time.

── Why the send runs in a thread ───────────────────────────────────────────

`smtplib` is synchronous and there is no stdlib async SMTP. Running it in
`asyncio.to_thread` keeps the worker's event loop free without adding a
dependency for the one channel where an extra 40ms does not matter. §6.1 puts
this behind a Celery queue anyway; the loop it must not block belongs to the
API process that fires a Class-T mail inline.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage

from sitara_schemas.notifications import DeliveryFailure, NotificationChannel

from sitara_api.notifications.classes import policy
from sitara_api.notifications.providers.base import (
    ChannelProviderName,
    ChannelUnavailable,
    Delivery,
    DeliveryOutcome,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmtpConfig:
    """Where the mail goes. Every field is deployment, not product."""

    host: str
    port: int
    #: The envelope sender. `sitara.app` locally, a verified SES identity in
    #: production — the adapter does not care which and must not.
    from_address: str
    from_name: str = "Tara"
    username: str | None = None
    password: str | None = None
    starttls: bool = False
    timeout: float = 10.0


class SmtpChannel:
    """§23.3's email rung. IMPLEMENTED — a real SMTP conversation."""

    name = ChannelProviderName.SMTP
    channel = NotificationChannel.EMAIL

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    async def send(self, delivery: Delivery) -> DeliveryOutcome:
        address = delivery.recipient.email
        if not address:
            # Same reasoning as the push adapter's missing subscription: the
            # ladder asked `reachable_on` first, so arriving here means the
            # address was suppressed or removed in between. Not a message
            # failure — the ladder moves on.
            return DeliveryOutcome(
                accepted=False, provider=self.name, failure=DeliveryFailure.REJECTED
            )

        message = self._build(delivery, address)
        try:
            await asyncio.to_thread(self._send_blocking, message, address)
        except smtplib.SMTPRecipientsRefused:
            # §23.6's "hard bounces and complaints … suppress the address
            # globally". A refusal at RCPT TIME is the synchronous half of
            # that and is not retryable — the ladder should move on rather
            # than spend two more attempts being told the same thing.
            logger.info(
                "smtp recipient refused", extra={"message_id": delivery.message_id}
            )
            return DeliveryOutcome(
                accepted=False, provider=self.name, failure=DeliveryFailure.REJECTED
            )
        except (smtplib.SMTPException, OSError) as exc:
            # §13: the exception does not travel — an SMTP error string can
            # carry the recipient address, which is PII in a log.
            logger.warning(
                "smtp transport failure",
                extra={"message_id": delivery.message_id, "error": type(exc).__name__},
            )
            raise ChannelUnavailable("smtp host unreachable") from None

        # SMTP's accept is a queue accept, not a delivery. §23.7 keeps `sent`
        # and `delivered` as separate statuses for exactly this reason, and
        # this adapter can only ever report the first.
        return DeliveryOutcome(
            accepted=True,
            provider=self.name,
            provider_message_id=message["Message-ID"],
        )

    def _build(self, delivery: Delivery, address: str) -> EmailMessage:
        message = EmailMessage()
        # THE BODY GOES ON FIRST, and the order is not stylistic.
        # `set_content` calls `clear_content()`, which strips every header whose
        # name begins with `Content-` — including `Content-Language`. Setting
        # the headers first and the body second silently drops the locale, and
        # nothing about the message looks wrong afterwards: it arrives, it
        # renders, and only a screen reader in Hindi behaves differently.
        # `test_the_locale_rides_on_the_message` is what found it.
        message.set_content(delivery.body)

        message["Subject"] = delivery.title
        local, _, domain = self._config.from_address.partition("@")
        message["From"] = Address(self._config.from_name, local, domain)
        message["To"] = address
        # §23.4's idempotency identity, carried into the one header that means
        # the same thing in SMTP. A mail server that sees it twice can collapse
        # it, and a human debugging a duplicate has the join key in the message
        # itself rather than only in our database.
        message["Message-ID"] = f"<{delivery.message_id}@sitara.app>"
        if delivery.collapse_key:
            # RFC 5322 threading. The push service collapses by Topic; a mail
            # client threads by References, and §23.4's rule that a regenerated
            # brief replaces rather than duplicates should look the same in an
            # inbox as it does in a notification centre.
            message["References"] = f"<{delivery.collapse_key}@sitara.app>"
        # §23.8 reports per locale and §2.4 has no fallback: a mail client that
        # knows the language renders the right script and speaks it aloud
        # correctly to a screen reader.
        message["Content-Language"] = delivery.locale
        message["X-SES-CONFIGURATION-SET"] = f"sitara-{delivery.message_class.value}"

        if policy(delivery.message_class).unsubscribe_header and delivery.unsubscribe_url:
            message["List-Unsubscribe"] = f"<{delivery.unsubscribe_url}>"
            message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        return message

    def _send_blocking(self, message: EmailMessage, address: str) -> None:
        with smtplib.SMTP(
            self._config.host, self._config.port, timeout=self._config.timeout
        ) as smtp:
            if self._config.starttls:
                smtp.starttls()
            if self._config.username and self._config.password:
                smtp.login(self._config.username, self._config.password)
            smtp.send_message(message, to_addrs=[address])
