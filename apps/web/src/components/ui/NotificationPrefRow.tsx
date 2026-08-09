"use client";

/**
 * NotificationPrefRow — §24.3 feedback / §23.5. One cell row of the preference
 * matrix: a notification class × the channels it may use.
 *
 * §23: transactional messages cannot be switched off, and the row says why in
 * words rather than rendering a dead switch. A channel the user has not granted
 * (push denied, WhatsApp not opted in) shows its state honestly and offers the
 * §30.1 recovery path instead of silently failing to deliver.
 */

import { useTranslations } from "next-intl";

import { cn, focusRing, motionStandard, touchTarget, type MessageKey } from "./_util";

export const NOTIFICATION_CHANNELS = ["push", "whatsapp", "email"] as const;
export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];

export type ChannelState = "on" | "off" | "unavailable";

export interface NotificationPrefRowProps {
  /** The §23.4 class: ui.notif.class.transactional | daily | conversational | marketing */
  classKey: MessageKey;
  descriptionKey?: MessageKey;
  channels: Record<NotificationChannel, ChannelState>;
  onToggle?: (channel: NotificationChannel, next: boolean) => void;
  /** Transactional (T) class — cannot be switched off (§23). */
  locked?: boolean;
  /** Opens the §30.1 re-enable instructions for an unavailable channel. */
  onFixChannel?: (channel: NotificationChannel) => void;
  className?: string;
}

export function NotificationPrefRow({
  classKey,
  descriptionKey,
  channels,
  onToggle,
  locked = false,
  onFixChannel,
  className,
}: NotificationPrefRowProps) {
  const t = useTranslations();
  return (
    <div className={cn("flex flex-col gap-2 border-b border-border-subtle py-3", className)}>
      <div className="flex flex-col gap-1">
        <span className="text-body text-ink-primary">{t(classKey)}</span>
        {descriptionKey ? (
          <span className="text-caption text-ink-muted">{t(descriptionKey)}</span>
        ) : null}
        {locked ? (
          <span className="text-caption text-ink-muted">{t("ui.notif.always_on")}</span>
        ) : null}
      </div>

      <ul className="flex flex-wrap gap-2">
        {NOTIFICATION_CHANNELS.map((channel) => {
          const state = channels[channel];
          const unavailable = state === "unavailable";
          const on = state === "on";
          return (
            <li key={channel}>
              <button
                type="button"
                role={unavailable ? undefined : "switch"}
                aria-checked={unavailable ? undefined : on}
                disabled={locked && on}
                onClick={() =>
                  unavailable ? onFixChannel?.(channel) : onToggle?.(channel, !on)
                }
                className={cn(
                  "inline-flex items-center gap-2 rounded-chip border px-3 py-2 text-caption",
                  touchTarget,
                  motionStandard,
                  focusRing,
                  on
                    ? "border-border-strong bg-gold-soft text-on-gold"
                    : "border-border-subtle bg-surface text-ink-primary",
                  unavailable && "border-dashed text-ink-muted",
                  locked && on && "cursor-not-allowed",
                )}
              >
                {/* glyph carries the state alongside the fill (§29.4) */}
                <span aria-hidden="true">{unavailable ? "ⓘ" : on ? "✓" : "○"}</span>
                <span>{t(`ui.notif.channel.${channel}`)}</span>
                {unavailable ? (
                  <span className="text-ink-muted">{t("ui.notif.unavailable")}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
