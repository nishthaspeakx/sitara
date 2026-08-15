"use client";

/**
 * S02 — language (§29.1 `/start/language`, §10-3).
 *
 * "FIRST interactive screen, before anything else; 8 language cards each
 * labeled in its own script + a one-line Tara greeting that plays in that
 * language's voice on tap."
 *
 * The eight names are NOT translated between catalogs — a card reading
 * "Gujarati" to an English speaker and "ગુજરાતી" to a Gujarati one defeats the
 * screen, whose whole job is that someone who reads only Gujarati can find
 * their language without reading anything else. `start.language.name.*` holds
 * the same eight values in all three catalogs, deliberately.
 *
 * Wave-2/3 locales render as cards but are not selectable: §2.4 admits a
 * language only with its signed 100% checklist (§12's gate), and a card that
 * silently did nothing would be worse than one that says "not yet".
 */

import { useLocale, useTranslations } from "next-intl";

import { Card, ListRow, SectionHeader, TaraPresence } from "@/components/ui";
import { STEPS } from "@/lib/onboarding";

import { useLocalStepCommit } from "../_step";

/** §2.2's eight, in wave order. `released` is §2.4's gate, not a preference. */
const LANGUAGES = [
  { code: "hi", released: true },
  { code: "hi-Latn", released: true },
  { code: "en", released: true },
  { code: "gu", released: false },
  { code: "pa", released: false },
  { code: "mr", released: false },
  { code: "ta", released: false },
  { code: "te", released: false },
] as const;

export default function LanguagePage() {
  const t = useTranslations();
  const active = useLocale();
  const { commit, busy } = useLocalStepCommit(STEPS.LANGUAGE);

  function choose(code: string) {
    // **S02 does not write to the server, and cannot.**
    //
    // §29.1 puts language FIRST and auth at S03, so at this moment there is no
    // session — and `PATCH /v1/onboarding` is behind `CurrentSession` (§33.2's
    // product identity comes from the §34.5 cookie). This screen used to call
    // it anyway: every tap returned 401, `commit` correctly refused to advance
    // a step it could not persist, and onboarding was sealed shut at its first
    // screen for anyone without a stale cookie. Same language or different made
    // no difference — there was nothing to authorise the write.
    //
    // The choice is not lost. next-intl pins the locale in the URL and cookie
    // on this navigation, and it reaches the server at the FIRST authenticated
    // moment: `POST /auth/session` already takes `locale` and stores it on the
    // user (S03). §24.4's "state persisted per step" holds — the step is
    // recorded locally now and durably the instant an identity exists.
    commit({ locale: code });
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <div className="flex justify-center">
        <TaraPresence size="md" state="profile_portrait" still showAiLabel />
      </div>

      <SectionHeader titleKey="start.language.title" subtitleKey="start.language.subtitle" />

      <Card as="section" className="p-0">
        <ul>
          {LANGUAGES.map(({ code, released }) => (
            <li key={code}>
              <ListRow
                // User-visible language names are DATA here, not copy: each is
                // written in its own script and must not be translated.
                label={t(`start.language.name.${code}`)}
                // NOT `start.skip`, which is the ACTION label "Skip for now"
                // and read as an invitation under a language you cannot pick —
                // the first live walkthrough showed five rows offering to skip
                // something that was never on offer. §2.4 admits a locale
                // through the §12 gate, so the honest word is "not yet".
                detailKey={released ? undefined : "start.language.not_released"}
                disabled={!released || busy}
                onClick={released ? () => choose(code) : undefined}
                trailing={code === active ? <span aria-hidden="true">✓</span> : undefined}
              />
            </li>
          ))}
        </ul>
      </Card>

      <p className="text-caption text-ink-muted">{t("start.language.greeting_hint")}</p>
    </main>
  );
}
