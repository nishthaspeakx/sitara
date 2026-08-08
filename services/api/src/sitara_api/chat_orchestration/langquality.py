"""Stage 10 — the language-quality validator (§9, §2.3, §2.4).

§9 names four checks: "locale match, script match, register/honorific lint,
glossary compliance". All four are here, and all four are mechanical. The
judgement calls this validator cannot make — mixing ratio, grammar, code-switch
naturalness — belong to §14's named native reviewer and the MOS panel, not to a
regex pretending to have taste.

A failure costs one corrective regeneration and then the safe in-locale
fallback line (§2.4 rule 8). It is never an English reply to a Hindi user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sitara_api import text as textutil
from sitara_api.chat_orchestration import config, language
from sitara_api.chat_orchestration.types import LAUNCH_LOCALES


@dataclass(frozen=True)
class LanguageQualityVerdict:
    ok: bool
    failures: tuple[str, ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.failures


#: §2.3: "Tara uses respectful-warm second person by default — aap
#: (HI/Hinglish) — and never switches to intimate forms uninvited."
_INTIMATE_FORMS: dict[str, tuple[str, ...]] = {
    "hi": ("तू", "तेरा", "तेरी", "तेरे", "तुझे", "तुझको", "तुम्हारा", "तुम्हें"),
    "hi-Latn": ("tu", "tera", "teri", "tere", "tujhe", "tujhko", "tumhara", "tumhein", "tum"),
}

#: The one glossary rule strong enough to lint: Tara is a photographic
#: presence and is NEVER called an avatar — in any locale, ever (§4.1, §24.3).
_FORBIDDEN = re.compile(r"\bavatars?\b|अवतार", re.IGNORECASE)



class LanguageQualityValidator:
    def __init__(self, glossary: tuple[tuple[str, tuple[str, ...]], ...] | None = None) -> None:
        self._glossary = glossary if glossary is not None else config.glossary_terms()

    def check(self, text: str, locale: str) -> LanguageQualityVerdict:  # noqa: C901
        failures: list[str] = []

        if locale not in LAUNCH_LOCALES:
            failures.append(f"locale {locale!r} is not a launch locale (§2.4)")

        if language.contains_wrong_script(text, locale):
            expected = language.script_of_locale(locale)
            failures.append(f"script mismatch: {locale} must render in {expected.value} (§2.3)")

        detected = language.detect(text, locale)
        # Only a confident detection can accuse a reply of drifting; a
        # three-word answer carries too little signal to convict on.
        if (
            detected.detected_locale != locale
            and detected.confidence >= 0.8
            and len(text.split()) >= 8
        ):
            failures.append(
                f"locale drift: reply reads as {detected.detected_locale}, "
                f"account locale is {locale} (§2.4 rule 3)"
            )

        for form in _INTIMATE_FORMS.get(locale, ()):
            if re.search(textutil.bounded(form), text, re.IGNORECASE):
                failures.append(f"intimate address {form!r} used uninvited (§2.3 honorifics)")
                break

        if _FORBIDDEN.search(text):
            failures.append("Tara is a photographic presence, never an 'avatar' (glossary)")

        for term, forbidden in self._glossary:
            # §2.4's rule is that these terms are KEPT NATIVE — about
            # TRANSLATION, not capitalisation. Comparing case only ever caught
            # a sentence-initial "Nakshatra", which is not a violation; what is
            # one is an English rendering standing in for the term.
            for rendering in forbidden:
                if re.search(textutil.bounded(rendering), text, re.IGNORECASE):
                    failures.append(
                        f"glossary term {term!r} rendered as {rendering!r} — "
                        f"kept native in all locales (§2.4)"
                    )
            # Case still matters for the proper nouns, and only those.
            if term[:1].isupper():
                pattern = textutil.bounded(term)
                if re.search(pattern, text, re.IGNORECASE) and not re.search(pattern, text):
                    failures.append(f"glossary term {term!r} altered (§2.4)")

        return LanguageQualityVerdict(ok=not failures, failures=tuple(failures))
