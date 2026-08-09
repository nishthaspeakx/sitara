"use client";

/**
 * Toast — §24.3 feedback. Bottom, auto-dismiss, **never stacked more than one**.
 *
 * The single-toast rule is enforced here rather than left to callers: the
 * component owns a module-level slot, so a second toast replaces the first
 * instead of piling up. §24.3 states the rule; this is where it is true.
 *
 * Auto-dismiss pauses on hover and focus, and never applies to a toast carrying
 * an action — an action the user cannot reach is a dark pattern.
 */

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { ICON_STROKE, cn, focusRing, touchTarget, type MessageKey } from "./_util";

/**
 * The single-toast slot. Whoever opens first holds it; a second Toast that
 * opens while it is held renders nothing, so "never stacked >1" cannot be
 * broken by a caller that forgets.
 */
let toastSlot: string | null = null;

export type ToastTone = "neutral" | "success";

export interface ToastProps {
  open: boolean;
  messageKey: MessageKey;
  /** ICU values for the message. */
  values?: Record<string, string | number>;
  tone?: ToastTone;
  actionKey?: MessageKey;
  onAction?: () => void;
  onDismiss: () => void;
  /** Milliseconds; ignored when an action is present. */
  autoDismissMs?: number;
  className?: string;
}

export function Toast({
  open,
  messageKey,
  values,
  tone = "neutral",
  actionKey,
  onAction,
  onDismiss,
  autoDismissMs = 4000,
  className,
}: ToastProps) {
  const t = useTranslations();
  const id = useId();
  const [paused, setPaused] = useState(false);
  const [holdsSlot, setHoldsSlot] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    if (toastSlot === null) toastSlot = id;
    setHoldsSlot(toastSlot === id);
    return () => {
      if (toastSlot === id) toastSlot = null;
    };
  }, [open, id]);

  useEffect(() => {
    if (!open || !holdsSlot || actionKey || paused) return;
    timer.current = setTimeout(onDismiss, autoDismissMs);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [open, holdsSlot, actionKey, paused, autoDismissMs, onDismiss]);

  if (!open || !holdsSlot) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className={cn(
        "fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md items-center gap-3 rounded-card border p-3 shadow-sheet",
        tone === "success"
          ? "border-feedback-success bg-surface"
          : "border-border-subtle bg-surface",
        className,
      )}
    >
      <p className="min-w-0 flex-1 text-body text-ink-primary">{t(messageKey, values)}</p>
      {actionKey ? (
        <button
          type="button"
          onClick={onAction}
          className={cn(
            "shrink-0 rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
            focusRing,
          )}
        >
          {t(actionKey)}
        </button>
      ) : null}
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t("ui.toast.dismiss")}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-portrait text-ink-muted",
          touchTarget,
          focusRing,
        )}
      >
        <X aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
      </button>
    </div>
  );
}
