"""Localisation resolver (§6.3 module, §2.4 fallback rules).

The catalogs in `packages/i18n/messages` are the single source of user-facing
copy — "every user-facing string in ANY app/service lives here as a key". This
resolver is the server-side reader for them.

§2.4 rule 7 is the whole design: a missing string falls back within the SAME
language family first (Hinglish → Hindi) and logs a defect; English is not a
fallback. A key that resolves nowhere raises, because a silent English reply
to a Hindi user is the one outcome the spec forbids outright.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()

#: Where the catalogs can live. The monorepo path is the developer's; the
#: image path is the deployed one — the Dockerfile copies packages/i18n
#: alongside the service, because a container that cannot resolve
#: `chat.safety.crisis` would answer a person in crisis with a 500.
_CANDIDATE_DIRS: tuple[Path, ...] = (
    _HERE.parents[4] / "packages" / "i18n" / "messages",  # monorepo checkout
    _HERE.parents[3] / "packages" / "i18n" / "messages",  # image: /app/services/api/..
    Path("/app/packages/i18n/messages"),  # image: absolute
)


def _resolve_messages_dir() -> Path:
    override = os.environ.get("SITARA_I18N_DIR")
    if override:
        return Path(override)
    for candidate in _CANDIDATE_DIRS:
        if candidate.is_dir():
            return candidate
    return _CANDIDATE_DIRS[0]


MESSAGES_DIR = _resolve_messages_dir()

#: §2.4 rule 7: within the same language family, never across it.
_FAMILY_FALLBACK: dict[str, tuple[str, ...]] = {
    "hi-Latn": ("hi",),
    "hi": (),
    "en": (),
}


class MissingString(KeyError):
    """No catalog in the locale's family has this key. Never falls back to
    English silently (§2.4 rule 7) — the caller must handle it."""


@lru_cache(maxsize=8)
def _catalog(locale: str) -> dict[str, Any]:
    path = MESSAGES_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _lookup(catalog: dict[str, Any], key: str) -> str | None:
    node: Any = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def resolve(key: str, locale: str, **params: Any) -> str:
    """Resolve `key` in `locale`, interpolating simple ICU `{name}` slots.

    Full ICU (plurals, selects, dates) is the client's job via next-intl; the
    server renders only the flat strings it owns — safety lines, fallbacks,
    notices — and those are authored without plural forms for exactly this
    reason.
    """
    for candidate in (locale, *_FAMILY_FALLBACK.get(locale, ())):
        found = _lookup(_catalog(candidate), key)
        if found is not None:
            if candidate != locale:
                # A P1 localisation defect, per §2.4 rule 7.
                logger.warning(
                    "i18n fallback within family",
                    extra={"key": key, "from": locale, "to": candidate},
                )
            return _interpolate(found, params)
    raise MissingString(f"{key!r} missing for locale {locale!r} and its family")


#: §25.3's holding phrases, in the order they rotate.
#:
#: A SET rather than one line, because a call is a conversation and a person who
#: says the identical six words at every pause stops sounding like a person. The
#: rotation is by index rather than random so a test can assert which phrase a
#: given turn produced — §25.3 asks for the wait to feel designed, and a designed
#: thing is one you can predict.
#:
#: They are held here, beside the safety and decline lines, because they share
#: the property that matters: the SERVICE renders them, not the client, so a
#: missing translation is a boot failure rather than a silence mid-call.
HOLDING_PHRASE_KEYS: tuple[str, ...] = (
    "call.holding.thinking",
    "call.holding.moment",
    "call.holding.time",
)


def _notification_keys() -> tuple[str, ...]:
    """§23's copy keys, read from the template tables.

    Imported inside a function rather than at module scope: `localisation` is
    imported by nearly everything, and a top-level import of a product module
    from it is one refactor away from a cycle. The call happens once, while
    `SERVER_RENDERED_KEYS` is being built.
    """
    from sitara_api.notifications.templates import NOTIFICATION_KEYS

    return NOTIFICATION_KEYS


#: Keys the server itself renders. The client resolves everything else, but
#: these are spoken by Tara or shown in place of her reply, so the service must
#: be able to produce them in every launch locale — or it must not start.
SERVER_RENDERED_KEYS: tuple[str, ...] = (
    "chat.safety.crisis",
    "chat.fallback.safe_line",
    "chat.data.cannot_calculate",
    "chat.data.missing.birth_date",
    "chat.data.missing.birth_place",
    "chat.data.missing.current_location",
    # §25.3's holding phrases. Tara SPEAKS these, so a missing Hindi one is a
    # call that falls silent for 5.8 seconds in exactly the locale the phrase
    # exists to hold — and it would fail at 1.8 seconds into a live call rather
    # than at boot. Same reasoning as the crisis line above: loud at startup.
    *HOLDING_PHRASE_KEYS,
    # S12's preview line (§29.1, §0.11 item 11). Tara SPEAKS this one too, and
    # it is the FIRST thing she ever says — a missing Hindi line would make the
    # product's opening promise about language the moment it broke it. Boot is
    # the right place to find that out. The literal rather than an import,
    # because `voice.preview` imports this module.
    "start.voice.preview_line",
    # §23's notification copy (M12). The SERVER renders these: a push payload
    # reaches a service worker that has no catalog, and an email body is
    # composed before it touches anything that could resolve a key. §2.4 has no
    # English fallback, so a missing Hindi string here is not a degraded
    # notification — it is an English system notification on a Hindi user's
    # lock screen, outside the app, at 07:00, once per locale per morning.
    #
    # Imported rather than listed, so a template added to §23.5's categories or
    # §23.2's catalogue arrives in this guard on the same commit. Listing them
    # would make the guard something a new template has to remember to join.
    *_notification_keys(),
)


def verify_catalogs(locales: tuple[str, ...]) -> None:
    """Fail at boot if a server-rendered string is missing (§2.4).

    Called by the app factory. The alternative — discovering it lazily — means
    discovering it when someone in crisis triggers the L4 path, which is the
    single worst moment for a KeyError. Loud at startup, silent thereafter.
    """
    missing: list[str] = []
    for locale in locales:
        for key in SERVER_RENDERED_KEYS:
            try:
                resolve(key, locale)
            except MissingString:
                missing.append(f"{locale}:{key}")
    if missing:
        raise RuntimeError(
            f"i18n catalogs incomplete at {MESSAGES_DIR} — missing {', '.join(missing)}. "
            "The service renders these itself (§9 safety and decline paths); refusing to "
            "start rather than fail in front of a user."
        )


def _interpolate(template: str, params: dict[str, Any]) -> str:
    out = template
    for name, value in params.items():
        out = out.replace("{" + name + "}", str(value))
    return out
