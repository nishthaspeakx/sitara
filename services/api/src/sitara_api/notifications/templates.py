"""The message copy, per §23.5 category and §23.2 trigger (§2.4, §0.2).

Every notification body is rendered by the SERVER — the push payload goes to a
service worker that has no catalog, and the email is composed before it reaches
anything that could resolve a key. So these keys sit in
`localisation.SERVER_RENDERED_KEYS` alongside §9's crisis line and §25.3's
holding phrases, and for the same reason: §2.4 has no English fallback, so a
missing Hindi string is not a degraded notification, it is silence — or worse,
an English system notification on a Hindi user's lock screen, which is the
exact outcome §2.4 forbids outright.

`verify_catalogs` therefore refuses to boot without them. A brief that could
not be announced because a string was missing would be discovered at 07:00
local, once, per locale.

── The copy rules that are not style ───────────────────────────────────────

§0.2's voice register binds notifications explicitly ("UI copy, notifications,
error states, legal summaries"), and two of its rules are checkable rather than
aesthetic:

* **No manufactured urgency.** §0.2 names the forbidden words — warning,
  danger, doomed, guaranteed, unlock now, last chance — and §29.2 forbids
  countdowns and guilt copy outright. A notification is the surface where that
  pressure is strongest, because a lock screen is read by someone who did not
  choose to be reading.
* **Re-engagement is warm, not guilt-based.** §23.2(6) says so in the
  catalogue entry itself: "Tara has your Thursday brief ready when you want
  it" is the spec's own example, and the thing it carefully does not say is
  how many days it has been.

`tests/notifications/test_copy.py` runs every key in every locale through the
§9 fear-selling lint, which is the same corpus `chat_orchestration` uses. That
is a mechanical check on a §14 human review, not a substitute for it — the
per-locale copy is a draft until the named native reviewer signs it, and
`notifications.copy_review` is the gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sitara_schemas.notifications import ContextualTrigger, NotificationCategory

from sitara_api.notifications.catalogue import CATALOGUE

#: Bumped on any edit to the copy. §23.7 stores it on every row and §23.8
#: reports per template version, so a copy change that moves the open rate is
#: attributable rather than merely coincident with a deploy.
TEMPLATE_VERSION = "notif.v1"


@dataclass(frozen=True)
class MessageTemplate:
    """One notification's title and body keys, plus where tapping it goes."""

    template_id: str
    title_key: str
    body_key: str
    #: §24.1: "deep links (notifications → brief card, reminder → chat context)
    #: route through a typed route map … and every push carries its deep link".
    #: A ROUTE, never an origin — the client joins it to its own, so a push
    #: cannot navigate a browser off our domain.
    deep_link: str


#: §23.5's five categories. The morning brief's own row is the one §32.6 is
#: about, and the one the §7.1 wave announces.
BY_CATEGORY: Mapping[NotificationCategory, MessageTemplate] = {
    NotificationCategory.MORNING: MessageTemplate(
        template_id="notif.morning",
        title_key="notifications.morning.title",
        body_key="notifications.morning.body",
        deep_link="/today",
    ),
    NotificationCategory.NIGHT: MessageTemplate(
        template_id="notif.night",
        title_key="notifications.night.title",
        body_key="notifications.night.body",
        # §24.1: night reflection is Today's evening STATE, not a fifth tab.
        # A deep link to a route that does not exist is §24.6's dead end
        # arriving from outside the app, where there is no back button yet.
        deep_link="/today/reflection",
    ),
    NotificationCategory.CONTEXTUAL: MessageTemplate(
        template_id="notif.contextual",
        title_key="notifications.contextual.title",
        body_key="notifications.contextual.body",
        deep_link="/today",
    ),
    NotificationCategory.FESTIVAL: MessageTemplate(
        template_id="notif.festival",
        title_key="notifications.festival.title",
        body_key="notifications.festival.body",
        deep_link="/today/festival",
    ),
    NotificationCategory.MARKETING: MessageTemplate(
        template_id="notif.marketing",
        title_key="notifications.marketing.title",
        body_key="notifications.marketing.body",
        deep_link="/you/subscription",
    ),
}


#: §23.2's six triggers each get their own copy. They are NOT five variants of
#: one contextual template: a muhurat reminder, a festival greeting and a
#: re-engagement check-in are three different things to receive, and sharing a
#: body key would make §23.8's per-trigger open rate a measurement of one
#: sentence's performance across six situations.
BY_TRIGGER: Mapping[ContextualTrigger, MessageTemplate] = {
    ContextualTrigger.USER_REMINDER: MessageTemplate(
        template_id="notif.trigger.user_reminder",
        title_key="notifications.trigger.user_reminder.title",
        body_key="notifications.trigger.user_reminder.body",
        # §24.1's "reminder → chat context". She asked Tara for this in a
        # conversation, so it returns her to one.
        deep_link="/ask",
    ),
    ContextualTrigger.MUHURAT_WINDOW: MessageTemplate(
        template_id="notif.trigger.muhurat",
        title_key="notifications.trigger.muhurat.title",
        body_key="notifications.trigger.muhurat.body",
        deep_link="/today/timings",
    ),
    ContextualTrigger.FESTIVAL_OR_FAMILY: MessageTemplate(
        template_id="notif.trigger.festival_or_family",
        title_key="notifications.trigger.festival_or_family.title",
        body_key="notifications.trigger.festival_or_family.body",
        deep_link="/today/festival",
    ),
    ContextualTrigger.REFLECTION_FOLLOWUP: MessageTemplate(
        template_id="notif.trigger.reflection_followup",
        title_key="notifications.trigger.reflection_followup.title",
        body_key="notifications.trigger.reflection_followup.body",
        deep_link="/journal",
    ),
    ContextualTrigger.TRANSIT_CHANGE: MessageTemplate(
        template_id="notif.trigger.transit_change",
        title_key="notifications.trigger.transit_change.title",
        body_key="notifications.trigger.transit_change.body",
        deep_link="/today",
    ),
    ContextualTrigger.QUIET_REENGAGEMENT: MessageTemplate(
        template_id="notif.trigger.quiet_reengagement",
        title_key="notifications.trigger.quiet_reengagement.title",
        body_key="notifications.trigger.quiet_reengagement.body",
        deep_link="/today",
    ),
}


#: Every key the server must be able to render, for `verify_catalogs`.
NOTIFICATION_KEYS: tuple[str, ...] = tuple(
    sorted(
        {
            key
            for template in (*BY_CATEGORY.values(), *BY_TRIGGER.values())
            for key in (template.title_key, template.body_key)
        }
    )
)


def for_category(category: NotificationCategory) -> MessageTemplate:
    return BY_CATEGORY[category]


def for_trigger(trigger: ContextualTrigger) -> MessageTemplate:
    return BY_TRIGGER[trigger]


assert set(BY_CATEGORY) == set(NotificationCategory), (
    "every §23.5 category needs copy, or a toggle exists for a message that "
    "cannot be rendered"
)
assert set(BY_TRIGGER) == set(ContextualTrigger), (
    "every §23.2 trigger needs copy — the catalogue is closed, so a missing "
    "row here is a trigger that can be selected and never said"
)
assert len({t.body_key for t in BY_TRIGGER.values()}) == len(CATALOGUE), (
    "SPEC §23.8 reports open rate per trigger. Two triggers sharing a body key "
    "would make that a measurement of one sentence across two situations, and "
    "§23.2's auto-pause would then pause both or neither."
)
