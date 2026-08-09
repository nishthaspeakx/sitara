"use client";

/**
 * ErrorState — §24.3 feedback. In-locale, warm, ONE retry action, trace id shown
 * as a small copyable code for support (§24.6).
 *
 * It takes a §34.4 envelope, not a string: `message_key` renders through the
 * catalogs so there is never an English error in a Hindi session, and
 * `retryable` decides whether the retry control exists at all — an unretryable
 * failure must not offer a button that cannot work.
 *
 * §29.5: Tara is NEVER the face of failure. This screen uses the illustration
 * system's constellation motif and no portrait.
 */

import { Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "./Button";
import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

/** The §34.4 error envelope, as the UI receives it. */
export interface ErrorEnvelope {
  code: string;
  message_key: string;
  trace_id: string;
  retryable: boolean;
}

export interface ErrorStateProps {
  error: ErrorEnvelope;
  onRetry?: () => void;
  /** Fatal variant (S46) adds the status-page link. */
  fatal?: boolean;
  statusHref?: string;
  className?: string;
}

export function ErrorState({ error, onRetry, fatal = false, statusHref, className }: ErrorStateProps) {
  const t = useTranslations();
  const [copied, setCopied] = useState(false);

  async function copyTrace() {
    try {
      await navigator.clipboard.writeText(error.trace_id);
      setCopied(true);
    } catch {
      // clipboard can be denied; the code stays selectable on screen either way
      setCopied(false);
    }
  }

  return (
    <div
      role="alert"
      className={cn("flex max-w-reading flex-col items-center gap-3 px-4 py-8 text-center", className)}
    >
      <span aria-hidden="true">
        <svg viewBox="0 0 96 64" className="h-16 w-24" role="presentation">
          <g className="stroke-border-strong" strokeWidth="1.5" fill="none">
            <path d="M18 40 L38 18 L58 40" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M62 22 L82 42" strokeLinecap="round" />
          </g>
          <g className="fill-gold-soft">
            <circle cx="18" cy="40" r="2.5" />
            <circle cx="38" cy="18" r="3" />
            <circle cx="58" cy="40" r="2.5" />
            <circle cx="82" cy="42" r="2.5" />
          </g>
        </svg>
      </span>

      <h2 className="font-serif text-h2 text-ink-primary">
        {t(fatal ? "ui.error.fatal_title" : "ui.error.title")}
      </h2>
      <p className="text-body text-ink-muted">{t(error.message_key)}</p>

      {error.retryable && onRetry ? <Button onClick={onRetry}>{t("ui.retry")}</Button> : null}

      {fatal && statusHref ? (
        <a
          href={statusHref}
          className={cn(
            "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
            focusRing,
          )}
        >
          {t("ui.error.status_link")}
        </a>
      ) : null}

      <button
        type="button"
        onClick={copyTrace}
        className={cn(
          "inline-flex items-center gap-2 rounded-chip border border-border-subtle px-2 py-1 text-caption text-ink-muted",
          motionStandard,
          focusRing,
        )}
      >
        <Copy aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
        <code className="tabular-nums">{error.trace_id}</code>
        <span className="sr-only">{t(copied ? "ui.error.trace_copied" : "ui.error.copy_trace")}</span>
      </button>
    </div>
  );
}
