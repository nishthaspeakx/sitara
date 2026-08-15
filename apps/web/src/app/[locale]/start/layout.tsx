"use client";

/**
 * The onboarding stack shell (§24.4, §28.1's linear-stack rules).
 *
 * §28.1: "onboarding is a linear stack — back = previous step, exit-intent
 * shows a save-progress note, never a blank page." All three live here rather
 * than on thirteen screens, so a screen cannot forget one.
 *
 * §24.4 adds the per-screen contract this provides: progress dots, back always
 * works, and step analytics. What each screen keeps for itself is its question.
 */

import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Button, Header, ProgressDots, Sheet } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { track } from "@/lib/analytics";
import { STEP_ROUTES } from "@/lib/onboarding";
import { useCloseOnBack } from "@/lib/overlay";

/** Route → step, derived from the one route table so the two cannot drift. */
const STEP_BY_ROUTE = new Map(
  Object.entries(STEP_ROUTES).map(([step, route]) => [route, Number(step)]),
);

function stepFor(pathname: string): number | null {
  // The pathname carries the locale prefix; match on the suffix.
  for (const [route, step] of STEP_BY_ROUTE) {
    if (pathname.endsWith(route)) return step;
  }
  return null;
}

export default function StartLayout({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const step = stepFor(pathname);
  const [exitOpen, setExitOpen] = useState(false);
  const locale = pathname.split("/")[1] ?? "en";

  // §28.1: Back closes the note before it pops the route.
  useCloseOnBack(exitOpen, () => setExitOpen(false));

  useEffect(() => {
    if (step !== null) track("onboarding_step_viewed", { step, locale });
  }, [step, locale]);

  /**
   * §28.1: "back = previous step, never exits to blank". The previous step is
   * the previous ENTRY in the table, not `history.back()` — a user who arrived
   * by a resume redirect has no previous entry, and popping the history there
   * lands outside the app.
   */
  function back() {
    if (step === null) return;
    const steps = Object.keys(STEP_ROUTES).map(Number).sort((a, b) => a - b);
    const index = steps.indexOf(step);
    if (index <= 0) {
      // At the first step, back is an exit — and an exit shows the note.
      setExitOpen(true);
      return;
    }
    router.push(STEP_ROUTES[steps[index - 1]!]!);
  }

  return (
    <div className="min-h-app bg-bg-canvas" data-testid="onboarding-stack" data-step={step ?? ""}>
      <Header variant="bare" onBack={back} />
      {step !== null ? (
        <div className="flex justify-center px-6 pb-2">
          <ProgressDots current={step} />
        </div>
      ) : null}

      {children}

      {/* §28.1's exit-intent note. §29.2 forbids the dark pattern this could
          easily become: it states that progress is saved and offers leaving as
          plainly as staying — no countdown, no guilt, close always visible. */}
      <Sheet
        open={exitOpen}
        onClose={() => setExitOpen(false)}
        titleKey="start.exit.title"
      >
        <p className="text-body text-ink-primary" data-testid="exit-note">
          {t("start.exit.body")}
        </p>
        <div className="mt-4 flex gap-3">
          <Button onClick={() => setExitOpen(false)}>{t("start.exit.stay")}</Button>
          <Button
            variant="tertiary"
            onClick={() => {
              if (step !== null) track("onboarding_abandoned", { step, locale });
              setExitOpen(false);
              router.push("/");
            }}
          >
            {t("start.exit.leave")}
          </Button>
        </div>
      </Sheet>
    </div>
  );
}
