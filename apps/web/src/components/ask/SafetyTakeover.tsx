"use client";

/**
 * §22.9 / §29.1 — the L3+ takeover. Also what `/support/now` (S39) renders.
 *
 * §29.1's rule is structural, not a matter of care: the takeover "exits only to
 * Ask Tara or Help — structurally never to paywall, stories or marketing
 * surfaces". So this component renders exactly two destinations and has no prop
 * that could add a third. `tests/ask-safety.spec.ts` walks the rendered subtree
 * and fails on any link outside that pair — a screen cannot route to a paywall
 * from here because there is nothing here that routes.
 *
 * §29.5: **no portrait.** "Safety takeover screen uses no portrait
 * (institutional calm)", and "she is never the face of failure". There is no
 * `TaraPresence` in this file and there must not be one.
 *
 * §13/§9: no astrology framing at L2+, and the copy carries no fear-selling —
 * it names help and says plainly what Tara is not.
 */

import { useTranslations } from "next-intl";

import { Button, Card } from "@/components/ui";

export interface SafetyTakeoverProps {
  /** Back to the thread. The conversation is not deleted or hidden. */
  onBackToTara?: () => void;
  /** §29.1's only other exit. */
  onGetHelp?: () => void;
}

export function SafetyTakeover({ onBackToTara, onGetHelp }: SafetyTakeoverProps) {
  const t = useTranslations();

  return (
    <section
      data-testid="safety-takeover"
      role="region"
      aria-label={t("ui.safety.title")}
      className="flex min-h-screen flex-col justify-center gap-5 bg-bg-canvas p-5"
    >
      <h1 className="max-w-reading text-title text-ink-primary">{t("ui.safety.title")}</h1>
      <p className="max-w-reading text-body text-ink-primary">{t("ui.safety.body")}</p>

      <Card className="flex flex-col gap-2">
        <p className="text-body text-ink-primary">{t("ui.safety.helpline_in")}</p>
        <p className="text-caption text-ink-muted">{t("ui.safety.helpline_intl")}</p>
      </Card>

      {/* §13: honest about what she is. Said here rather than left implied,
          because this is the screen where the difference matters most. */}
      <p className="max-w-reading text-caption text-ink-muted">{t("ui.safety.disclosure")}</p>

      <div className="mt-auto flex flex-col gap-2">
        {/* Rendered only when there is somewhere to go — the convention
            `ChatHeader`, `PaywallPanel` and `ErrorState` already follow: where
            an action cannot happen, no control for it exists.

            It matters more here than anywhere else in the product. This
            handler pointed at `/you/help`, which does not exist, so the
            PRIMARY button on the L3+ crisis screen 404'd in all three
            locales. On `/support/now` the user is already at the help
            surface, so the prop is omitted and the button is absent rather
            than being a link to the page you are on.

            The helpline itself is in the Card above and is never behind this
            button — a crisis number that needed a tap would be the wrong
            design regardless of whether the tap worked. */}
        {onGetHelp ? (
          <Button variant="primary" fullWidth onClick={onGetHelp}>
            {t("ui.safety.get_help")}
          </Button>
        ) : null}
        <Button variant="tertiary" fullWidth onClick={onBackToTara}>
          {t("ui.safety.back_to_tara")}
        </Button>
      </div>
    </section>
  );
}
