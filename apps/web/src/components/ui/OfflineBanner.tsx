"use client";

/**
 * OfflineBanner — §24.3 feedback, §24.6 / §6.2.
 *
 * Offline is never a blank screen: the banner sits above CACHED content and the
 * composer stays usable with messages queued. It is informational, not an
 * alarm — hence the neutral surface, not the danger colour.
 */

import { CloudOff, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

export interface OfflineBannerProps {
  /** Number of composer messages waiting to send (§6.2). */
  queued?: number;
  onRetry?: () => void;
  /** When the shown content was cached, formatted in-locale. */
  cachedAt?: string;
  className?: string;
}

export function OfflineBanner({ queued = 0, onRetry, cachedAt, className }: OfflineBannerProps) {
  const t = useTranslations();
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border-subtle bg-surface-sunken px-4 py-2",
        className,
      )}
    >
      <CloudOff aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4 shrink-0 text-ink-muted" />
      <p className="min-w-0 flex-1 text-caption text-ink-primary">
        {t("ui.offline.title")}
        {cachedAt ? <span className="text-ink-muted"> {t("ui.offline.cached_at", { time: cachedAt })}</span> : null}
      </p>
      {queued > 0 ? (
        <span className="rounded-chip bg-surface px-2 py-1 text-caption text-ink-muted">
          {t("ui.offline.queued", { count: queued })}
        </span>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            "inline-flex items-center gap-1 rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
            motionStandard,
            focusRing,
          )}
        >
          <RefreshCw aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
          {t("ui.retry")}
        </button>
      ) : null}
    </div>
  );
}
