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

import { Card, ErrorState, ListRow, SectionHeader, TaraPresence } from "@/components/ui";
import { usePathname, useRouter } from "@/i18n/navigation";
import { patchState, STEPS } from "@/lib/onboarding";

import { useStepCommit } from "../_step";

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
  const router = useRouter();
  const pathname = usePathname();
  const active = useLocale();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.LANGUAGE);

  async function choose(code: string) {
    if (code !== active) {
      // Switching locale re-renders the whole app in the new script (§10-3:
      // "full re-render, no residue"). The commit follows on the new route.
      router.replace(pathname, { locale: code });
    }
    await commit(() => patchState({ locale: code, completed_step: STEPS.LANGUAGE }));
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <div className="flex justify-center">
        <TaraPresence size="md" state="warm_neutral" still showAiLabel />
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
                detailKey={released ? undefined : "start.skip"}
                disabled={!released || busy}
                onClick={released ? () => void choose(code) : undefined}
                trailing={code === active ? <span aria-hidden="true">✓</span> : undefined}
              />
            </li>
          ))}
        </ul>
      </Card>

      <p className="text-caption text-ink-muted">{t("start.language.greeting_hint")}</p>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}
    </main>
  );
}
