"use client";

/**
 * §25.3's screen 17, built to the reference layout.
 *
 * Reading the spec sentence as a layout:
 *
 *   "full-bleed Tara portrait/cinemagraph, dimmed 25% behind controls; top bar
 *    — minimise (pip), her name ("Tara" + "AI guide" microlabel), privacy
 *    shield icon → sheet; centre: call timer; bottom: three controls exactly as
 *    the reference — mute · end (red) · speaker, plus the plan chip"
 *
 * `src/components/call/` is NOT the component library — same rule as `today/`
 * and `ask/`. §24.3 is fixed at 49 and `tests/library.spec.ts` scans only
 * `src/components/ui`. Everything here composes library components:
 * `TaraPresence` for the portrait, `CallControls` for the three controls and
 * the chip, `Sheet` for the privacy explainer, `Chip` for the state.
 *
 * Two rules the shape of this file enforces rather than remembers:
 *
 * - **The dim is a sibling layer, not a filter on the portrait.** §29.4 forbids
 *   filtering her beyond the graded masters, so the 25% is a scrim ON TOP of
 *   the image rather than an `opacity`/`filter` applied to it.
 * - **The "Tara · AI guide" disclosure is not optional here** (§25.2, CC-008).
 *   It is passed to `TaraPresence` AND rendered in the top bar, because the
 *   portrait's own caption sits behind the controls at this size.
 */

import { ChevronDown, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CallControls } from "@/components/ui/CallControls";
import { Chip } from "@/components/ui/Chip";
import { IconButton } from "@/components/ui/IconButton";
import { Sheet } from "@/components/ui/Sheet";
import { TaraPresence } from "@/components/ui/TaraPresence";
import { ICON_STROKE, cn, focusRing } from "@/components/ui/_util";
import type { CallModel, CallState } from "@/lib/call-state";

/**
 * §25.3's states → §4.3's presence states, for the portrait.
 *
 * §29.5 assigns the call "states 1–4, 9 at night", so this map never reaches
 * outside that set. `degraded` and `ended` deliberately keep her warm-neutral
 * portrait rather than reaching for `concern_kind`: a network problem is not
 * something to look concerned about at somebody, and §29.5 keeps her off the
 * face of failure entirely.
 */
const PORTRAIT: Record<CallState, "welcome" | "listening" | "thoughtful" | "speaking_soft"> = {
  connecting: "welcome",
  listening: "listening",
  thinking: "thoughtful",
  speaking: "speaking_soft",
  degraded: "welcome",
  ended: "welcome",
};

const STATUS_KEY: Record<CallState, string> = {
  connecting: "ui.call.connecting",
  listening: "ui.call.listening",
  thinking: "ui.call.thinking",
  speaking: "ui.call.speaking",
  degraded: "ui.call.reconnecting",
  ended: "ui.call.ended",
};

export interface CallScreenProps {
  model: CallModel;
  onToggle: (control: "muted" | "speakerOn" | "captionsOn") => void;
  onEnd: () => void;
  onMinimise: () => void;
  onOpenThread: () => void;
  onDismissWarning: () => void;
  onResume: () => void;
  /** Injected so a screenshot baseline is not a function of when it ran. */
  now?: number;
}

function elapsed(startedAt: number | null, now: number): string {
  if (startedAt === null) return "0:00";
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function CallScreen({
  model,
  onToggle,
  onEnd,
  onMinimise,
  onOpenThread,
  onDismissWarning,
  onResume,
  now,
}: CallScreenProps) {
  const t = useTranslations();
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [tick, setTick] = useState(() => now ?? Date.now());

  useEffect(() => {
    if (now !== undefined) return; // pinned by a caller (a baseline, a story)
    const id = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [now]);

  const clock = now ?? tick;
  const degraded = model.state === "degraded";

  return (
    <main
      data-call-state={model.state}
      className="relative flex h-dvh w-full flex-col overflow-hidden bg-brand-navy-deep"
    >
      {/* The portrait, full bleed. `TaraPresence` is a `<figure>` with auto
          height, so its inner `h-full` resolves against nothing unless the
          figure is stretched — without this the portrait letterboxed at ~70%
          of the viewport and the rest of the screen was flat navy. Caught by
          the first baseline, which is what they are for. */}
      <div className="absolute inset-0">
        <TaraPresence
          size="full"
          state={PORTRAIT[model.state]}
          still
          className="h-full w-full"
        />
      </div>
      {/* ── The scrims, and an honest note about §25.3's "dimmed 25%" ─────
          §25.3 asks for the portrait "dimmed 25% behind controls". **The token
          layer cannot express a translucent overlay today**: every colour is a
          `var(--color-…)` holding a hex string, and Tailwind v3 emits NO RULE
          AT ALL for an opacity modifier on one — `bg-brand-navy-deep/25`
          compiles to nothing. The first baseline is what showed it: the dim was
          in the source, absent from the CSS, and the mandatory CC-008
          disclosure was unreadable over a lamp-lit frame.

          (The same defect is live in `Modal` and `Sheet`, whose
          `bg-brand-navy-deep/60` scrims have never rendered either. That is a
          token-layer fix — a scrim token, or channel-triplet colours with
          `<alpha-value>` — and it belongs in its own reviewed change, not here.)

          So the dim is expressed with what DOES compile: gradient bands from
          the solid token colour to transparent, at the top and bottom where
          the text is. It is a deviation from a flat 25% and it is stronger
          exactly where §25.3 says the dim is for ("behind controls"), while
          leaving her face untouched — §29.4 forbids filtering the portrait, so
          a scrim over it was always the only permitted mechanism. */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-brand-navy-deep to-transparent"
      />
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-80 bg-gradient-to-t from-brand-navy-deep to-transparent"
      />

      <div className="relative flex h-full flex-col justify-between p-4">
        {/* ── top bar ─────────────────────────────────────────────────── */}
        <header className="flex items-start justify-between gap-3">
          {/* `plain` is `text-ink-primary` — dark navy, correct on every other
              surface in the app and invisible on this one, so both top-bar
              controls rendered as smudges and one of them is the privacy
              shield §25.3 requires.

              **`text-on-brand`, NOT `text-inverse`.** This is the trap
              `today/sky.ts` documents and this screen walked straight into:
              `inverse` means "the opposite of THIS THEME's ink", so it is
              cream in light and NAVY in night — and every fixed dark surface
              here (the scrim, the caption block) then had navy text on navy in
              the night theme. The night baseline showed the timer, her name,
              the disclosure and every caption simply gone. `on-brand` is
              defined as reading on brand-navy and is light in BOTH themes,
              which is exactly what a fixed dark surface needs. */}
          <IconButton
            variant="plain"
            labelKey="ui.call.minimise"
            onClick={onMinimise}
            className="text-text-on-brand"
            icon={<ChevronDown strokeWidth={ICON_STROKE} />}
          />

          <div className="flex flex-col items-center">
            <p className="text-body-strong text-text-on-brand">{t("ui.call.tara")}</p>
            {/* CC-008 / §25.2 — permanent, and never conditional on anything.
                Full opacity: a disclosure that is mandatory and unreadable is
                not a disclosure, and the first baseline showed it at 80% over
                a lamp-lit frame where it disappeared entirely. */}
            <p className="text-caption text-text-on-brand">{t("ui.tara.ai_label")}</p>
          </div>

          <IconButton
            variant="plain"
            labelKey="ui.call.privacy_title"
            onClick={() => setPrivacyOpen(true)}
            className="text-text-on-brand"
            icon={<ShieldCheck strokeWidth={ICON_STROKE} />}
          />
        </header>

        {/* ── centre: the timer, the state, the captions ───────────────── */}
        <div className="flex flex-col items-center gap-3">
          <p
            aria-live="off"
            data-testid="call-timer"
            className="text-display text-text-on-brand tabular-nums"
          >
            {elapsed(model.startedAt, clock)}
          </p>
          {/* State is announced in words, never by the portrait alone (§29.4:
              state is never colour — or here, never imagery — alone). */}
          <Chip>{t(STATUS_KEY[model.state])}</Chip>

          {model.captionsOn ? (
            <div
              data-testid="call-captions"
              aria-live="polite"
              className="max-h-40 w-full max-w-prose overflow-y-auto rounded-sheet bg-brand-navy-deep p-3"
            >
              {model.captions.slice(-4).map((line) => (
                <p
                  key={`${line.role}-${line.id}-${line.partial ? "p" : "f"}`}
                  data-role={line.role}
                  data-partial={line.partial || undefined}
                  className={cn(
                    "text-caption text-text-on-brand",
                    // A partial is provisional and says so visually as well as
                    // in `data-partial` — the recogniser corrects itself, and a
                    // provisional line rendered as settled reads as Tara
                    // mishearing rather than as STT still thinking.
                    line.partial && "opacity-70",
                  )}
                >
                  <span className="font-medium">
                    {t(line.role === "tara" ? "ui.call.tara" : "ui.call.you")}:{" "}
                  </span>
                  {line.text}
                </p>
              ))}
            </div>
          ) : null}

          {model.warningKey ? (
            // §32.9's notice. Dismissible and never a countdown (§29.2).
            <button
              type="button"
              onClick={onDismissWarning}
              className={cn(
                "rounded-chip bg-surface px-3 py-1 text-caption text-ink-primary",
                focusRing,
              )}
            >
              {t(model.warningKey, { minutes: model.warningMinutes ?? 0 })}
            </button>
          ) : null}

          {model.resumeOffered ? (
            <button
              type="button"
              onClick={onResume}
              data-testid="call-resume"
              className={cn(
                "rounded-chip bg-surface px-3 py-2 text-caption text-ink-primary",
                focusRing,
              )}
            >
              {t("ui.call.resume_offer")}
            </button>
          ) : null}
        </div>

        {/* ── bottom: the three controls, the chip, the handoff ────────── */}
        {degraded ? (
          <section
            data-testid="call-handoff"
            className="rounded-sheet bg-surface p-4 text-center"
          >
            <p className="text-body-strong text-ink-primary">{t("ui.call.handoff_title")}</p>
            {/* The reassurance is the true one: the transcript is already in
                the thread, because the API commits each turn as it happens. */}
            <p className="mt-1 text-caption text-ink-muted">{t("ui.call.handoff_body")}</p>
            <button
              type="button"
              onClick={onOpenThread}
              className={cn(
                "mt-3 rounded-chip bg-interactive-primary px-4 py-2 text-body text-on-gold",
                focusRing,
              )}
            >
              {t("ui.call.handoff_open")}
            </button>
          </section>
        ) : (
          <CallControls
            muted={model.muted}
            onToggleMute={() => onToggle("muted")}
            speakerOn={model.speakerOn}
            onToggleSpeaker={() => onToggle("speakerOn")}
            captionsOn={model.captionsOn}
            onToggleCaptions={() => onToggle("captionsOn")}
            onEnd={onEnd}
            minutesLeft={model.plan?.minutesLeft ?? undefined}
            minutesTotal={model.plan?.minutesQuota ?? undefined}
            onOpenPlan={() => setPlanOpen(true)}
          />
        )}
      </div>

      <Sheet
        open={privacyOpen}
        onClose={() => setPrivacyOpen(false)}
        titleKey="ui.call.privacy_title"
      >
        {/* §13, and §25.3's own instruction: honest, and never claiming E2E. */}
        <p className="text-body text-ink-primary">{t("ui.call.privacy_body")}</p>
      </Sheet>

      <Sheet open={planOpen} onClose={() => setPlanOpen(false)} titleKey="ui.call.fair_use_title">
        <p className="text-body text-ink-primary">
          {model.plan?.unlimited
            ? t("ui.call.plan_unlimited")
            : t("ui.call.fair_use_body", { minutes: model.plan?.minutesQuota ?? 0 })}
        </p>
      </Sheet>
    </main>
  );
}
