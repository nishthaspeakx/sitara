"use client";

/**
 * S41 notification preferences — §29.1 `/you/settings/notifications`, §23.5.
 *
 * §23.5's whole sentence, as a screen:
 *
 *   "Per-category toggles (morning / night / contextual / festival /
 *    marketing) × per-channel (push / WhatsApp / email) matrix with honest
 *    copy — no 'are you sure' guilt modals; quiet hours (default 22:30–07:00
 *    local, user-adjustable); brief time picker; one-tap 'pause everything for
 *    a week' (Class T exempt, stated plainly); travel behaviour toggle."
 *
 * ── What this screen does NOT do, and why each absence is deliberate ──────
 *
 * **It evaluates no §23 rule.** No cap is counted here, no quiet-hours window
 * is compared, no ladder is built. Every one of those is a SENDING decision the
 * server owns — the mirror of §32.1's Today `variant`, which is a display rule
 * the client owns and the server deliberately does not serve. A screen that
 * computed "would this send" would be a second implementation of §23,
 * disagreeing on exactly the morning it mattered.
 *
 * **There is no confirmation on anything.** §23.5 says "no 'are you sure'
 * guilt modals" and §29.2 says the close is always visible. Switching a
 * category off saves immediately; un-pausing is one tap with no minimum.
 *
 * **A row is never disabled and never removed.** WhatsApp's §23.3 cell is
 * DECLARED — the adapter is not built — so its column renders, stores a
 * choice, and says "not available yet" beside it. Hiding the column would
 * silently discard the preference of everyone who set it early, and they would
 * find it off on the day the channel arrived. `NotificationPrefRow` already
 * has the shape for this (`ChannelState = "unavailable"`), which is why M12
 * added no component: §24.3 stays at 49.
 *
 * ── §32.6's overlap notice is the one piece of copy worth reading twice ───
 *
 * When her brief time sits inside her quiet hours, §32.6 requires the screen to
 * flag it ONCE — "your brief arrives inside your quiet hours — that's fine,
 * just checking" — and to "never silently suppress". So the notice is a
 * courtesy and not a warning: it has an acknowledge button and no fix button,
 * because there is nothing broken. Dismissing it records the FINGERPRINT of
 * that overlap, so a later, different overlap flags again and this one never
 * does.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import {
  Button,
  Card,
  ErrorState,
  Input,
  NotificationPrefRow,
  SectionHeader,
  SegmentedControl,
  Skeleton,
} from "@/components/ui";
import type { ChannelState } from "@/components/ui/NotificationPrefRow";
import { YouShell } from "@/components/you/YouShell";
import {
  acknowledgeOverlap,
  cellEnabled,
  channelAvailable,
  loadPreferences,
  NOTIFICATION_CATEGORIES,
  NOTIFICATION_CHANNELS,
  pauseEverything,
  resumeEverything,
  savePreferences,
  subscribeToPush,
  type NotificationCategory,
  type NotificationChannel,
  type NotificationPreferences,
} from "@/lib/notifications";

type View =
  | { kind: "loading" }
  | { kind: "ready"; preferences: NotificationPreferences }
  | { kind: "error"; error: ErrorEnvelope };

export default function NotificationSettingsPage() {
  const t = useTranslations();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    const result = await loadPreferences();
    setView(
      result.ok
        ? { kind: "ready", preferences: result.data }
        : { kind: "error", error: result.error },
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const apply = useCallback(
    async (run: () => Promise<{ ok: true; data: NotificationPreferences } | { ok: false; error: ErrorEnvelope }>) => {
      setSaving(true);
      const result = await run();
      setSaving(false);
      if (result.ok) setView({ kind: "ready", preferences: result.data });
      else setView({ kind: "error", error: result.error });
    },
    [],
  );

  if (view.kind === "loading") {
    return (
      <YouShell testId="notifsettings" titleKey="notifsettings.title" withTabs={false}>
        <Skeleton variant="list" />
      </YouShell>
    );
  }
  if (view.kind === "error") {
    return (
      <YouShell testId="notifsettings" titleKey="notifsettings.title" withTabs={false}>
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      </YouShell>
    );
  }

  const preferences = view.preferences;
  const paused = preferences.paused_until !== null;

  const stateFor = (
    category: NotificationCategory,
    channel: NotificationChannel,
  ): ChannelState => {
    // Availability first: a channel with no adapter is `unavailable`
    // regardless of the stored choice, and the choice is still stored.
    if (!channelAvailable(preferences, channel)) return "unavailable";
    return cellEnabled(preferences, category, channel) ? "on" : "off";
  };

  const toggle = (category: NotificationCategory) =>
    (channel: NotificationChannel, next: boolean) => {
      void apply(async () => {
        // Turning push ON is the one toggle that needs the BROWSER's consent
        // too, and it must happen inside this click — a permission prompt away
        // from a gesture is denied by reflex, and a denial is sticky.
        if (channel === "push" && next) await subscribeToPush();
        return savePreferences({ matrix: [{ category, channel, enabled: next }] });
      });
    };

  return (
    <YouShell
      testId="notifsettings"
      titleKey="notifsettings.title"
      subtitleKey="notifsettings.subtitle"
      withTabs={false}
    >
      {/* §32.6 — flagged once, never a warning, never a suppression. There is
          deliberately no "fix this" control: nothing is broken. */}
      {preferences.overlap_to_flag ? (
        <Card measure>
          <p className="text-body text-ink-primary">{t("notifsettings.overlap_notice")}</p>
          <Button
            variant="secondary"
            onClick={() => void apply(acknowledgeOverlap)}
            disabled={saving}
          >
            {t("notifsettings.overlap_ack")}
          </Button>
        </Card>
      ) : null}

      {NOTIFICATION_CATEGORIES.map((category) => (
        <NotificationPrefRow
          key={category}
          classKey={`notifsettings.category.${category}`}
          descriptionKey={`notifsettings.category_detail.${category}`}
          channels={
            Object.fromEntries(
              NOTIFICATION_CHANNELS.map((channel) => [channel, stateFor(category, channel)]),
            ) as Record<NotificationChannel, ChannelState>
          }
          onToggle={toggle(category)}
        />
      ))}

      <SectionHeader
        titleKey="notifsettings.brief_time"
        subtitleKey="notifsettings.brief_time_detail"
      />
      <Input
        kind="time"
        labelKey="notifsettings.brief_time"
        value={preferences.brief_time}
        disabled={saving}
        onChange={(event) =>
          void apply(() => savePreferences({ brief_time: event.target.value }))
        }
      />

      <SectionHeader
        titleKey="notifsettings.quiet_hours"
        subtitleKey="notifsettings.quiet_hours_detail"
      />
      <div className="flex gap-3">
        <Input
          kind="time"
          labelKey="notifsettings.quiet_from"
          value={preferences.quiet_hours_start}
          disabled={saving}
          onChange={(event) =>
            void apply(() => savePreferences({ quiet_hours_start: event.target.value }))
          }
        />
        <Input
          kind="time"
          labelKey="notifsettings.quiet_to"
          value={preferences.quiet_hours_end}
          disabled={saving}
          onChange={(event) =>
            void apply(() => savePreferences({ quiet_hours_end: event.target.value }))
          }
        />
      </div>

      <SectionHeader titleKey="notifsettings.travel" />
      <SegmentedControl
        labelKey="notifsettings.travel"
        value={preferences.follow_timezone ? "follow" : "home"}
        segments={[
          { value: "follow", labelKey: "notifsettings.travel_follow" },
          { value: "home", labelKey: "notifsettings.travel_home" },
        ]}
        disabled={saving}
        onChange={(value) =>
          void apply(() => savePreferences({ follow_timezone: value === "follow" }))
        }
      />

      {/* §23.5: "Class T exempt, stated plainly". Stated whether or not she is
          paused — the sentence is what makes the promise honest, not a
          footnote that appears once the pause is already on. */}
      <SectionHeader
        titleKey="notifsettings.pause"
        subtitleKey="notifsettings.pause_detail"
      />
      {paused ? (
        <>
          <p className="text-body text-ink-primary">
            {t("notifsettings.paused_until", {
              date: new Date(preferences.paused_until!).toLocaleDateString(),
            })}
          </p>
          {/* §29.2: one tap, no confirmation, no minimum. */}
          <Button onClick={() => void apply(resumeEverything)} disabled={saving}>
            {t("notifsettings.resume")}
          </Button>
        </>
      ) : (
        <Button
          variant="secondary"
          onClick={() => void apply(pauseEverything)}
          disabled={saving}
        >
          {t("notifsettings.pause")}
        </Button>
      )}
    </YouShell>
  );
}
