"use client";

/**
 * §32.1's stack, rendered. The DECIDING is already done.
 *
 * `chrome.banners` arrives from `resolveChrome` already truncated to two, in
 * §32.1's declared priority, with the night-takeover and safety rules applied.
 * This component's only job is to turn each name into the right library
 * component — which is why there is no `if (festival && banners.length < 2)`
 * anywhere below. A second copy of the precedence rule, in the file that
 * renders it, is how the two would drift on the crowded morning the rule exists
 * for.
 *
 * The trial pill and the birth-time chip render here too: §32.1 counts them in
 * the same stack ("max 2 banners + 1 pill"), so they belong beside the banners
 * rather than scattered down the screen where the ceiling could not be seen.
 */

import { useFormatter, useTranslations } from "next-intl";

import type { TodayPayload } from "@sitara/schemas";

import { Chip, FestivalBanner, OfflineBanner } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import type { TodayChrome } from "@/lib/today-variant";

export interface BannerStackProps {
  payload: TodayPayload;
  chrome: TodayChrome;
  onSortPayment?: () => void;
  onAddBirthTime?: () => void;
  onOpenFestival?: () => void;
  /** When the cached payload was taken — §28.2's "as of [time]". */
  cachedAt?: string;
}

export function BannerStack({
  payload,
  chrome,
  onSortPayment,
  onAddBirthTime,
  onOpenFestival,
  cachedAt,
}: BannerStackProps) {
  const router = useRouter();
  const t = useTranslations();
  const format = useFormatter();
  const { state } = payload;

  if (
    chrome.banners.length === 0 &&
    chrome.trialPill === null &&
    !chrome.birthTimeChip
  ) {
    return null;
  }

  return (
    <div data-testid="banner-stack" className="flex flex-col">
      {chrome.banners.map((banner) => {
        switch (banner) {
          case "payment_grace":
            return (
              <Notice
                key={banner}
                testId="banner-grace"
                tone="grace"
                text={t("today.banner.grace")}
                actionLabel={t("today.banner.grace_action")}
                onAction={onSortPayment}
              />
            );
          case "travel":
            return (
              <Notice
                key={banner}
                testId="banner-travel"
                tone="info"
                text={t("today.banner.travel", { city: state.travel.city ?? "" })}
              />
            );
          case "offline":
            return <OfflineBanner key={banner} cachedAt={cachedAt} />;
          case "festival":
            return state.festival ? (
              <div key={banner} data-testid="banner-festival" className="px-5 pb-2">
                <FestivalBanner
                  name={state.festival.name}
                  traditionLabel={state.festival.tradition_label}
                  // The payload carries an ISO date; a banner that printed
                  // "2026-08-12" would be the one string on a whole-app-native
                  // screen that belongs to no language (§2.4 reaches numerals
                  // and dates, not only words).
                  dateLabel={format.dateTime(new Date(state.festival.date_label), {
                    day: "numeric",
                    month: "long",
                  })}
                  onOpen={onOpenFestival ?? (() => router.push("/today/festival"))}
                />
              </div>
            ) : null;
          case "safety":
            // §22.9's L3+ takeover is its own surface (`/support/now`), not a
            // banner Today draws. The slot exists so §32.1's "never co-renders"
            // rule is expressible here rather than being a comment elsewhere.
            return null;
          default:
            return null;
        }
      })}

      <div className="flex flex-wrap items-center gap-2 px-5">
        {chrome.trialPill !== null ? (
          // §28.2: "subtle, never red", and from day 4 — the day count is a
          // POSITION, not a countdown (§29.2). `resolveChrome` decides whether
          // it shows at all.
          <span
            data-testid="trial-pill"
            className="rounded-chip bg-surface-sunken px-3 py-1 text-caption text-ink-muted"
          >
            {t("today.trial_pill", { day: chrome.trialPill })}
          </span>
        ) : null}

        {chrome.birthTimeChip ? (
          <Chip variant="choice" onClick={onAddBirthTime}>
            <span data-testid="birth-time-chip">{t("today.birth_time_chip")}</span>
          </Chip>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A one-line banner.
 *
 * `grace` uses the caution token deliberately and it is the ONE place on this
 * screen that may: §28.2 calls it "amber banner", and unlike a degraded reading
 * it is a state with a consequence the user can act on. Everything else on
 * Today — a limited confidence, a missing chart, a short brief — is an honest
 * limit, and §34.7 is explicit those never reach for caution or danger colour.
 */
function Notice({
  testId,
  tone,
  text,
  actionLabel,
  onAction,
}: {
  testId: string;
  tone: "grace" | "info";
  text: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div
      data-testid={testId}
      role="status"
      aria-live="polite"
      className={
        tone === "grace"
          ? "flex flex-wrap items-center gap-2 border-b border-border-subtle bg-feedback-caution/10 px-5 py-2"
          : "flex flex-wrap items-center gap-2 border-b border-border-subtle bg-surface-sunken px-5 py-2"
      }
    >
      <p className="min-w-0 flex-1 text-caption text-ink-primary">{text}</p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
