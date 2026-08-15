"use client";

/**
 * Sheet — §24.3 structure. The app's default overlay: paywall, "Why this?",
 * permission explainers, pickers.
 *
 * §24.1 / §29.2: a sheet is never a dead end — the close control is always
 * visible, Escape always works, and focus is trapped while it is open.
 */

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useId, useRef, type ReactNode } from "react";

import { ICON_STROKE, cn, focusRing, touchTarget, type MessageKey } from "./_util";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  titleKey: MessageKey;
  /**
   * ICU values for `titleKey`.
   *
   * The same convention `Header` already carries: a title that names a PERSON
   * ("Remove Sudha?", §32.15) is a key plus user data, never a pre-rendered
   * string — pre-rendering it at the call site would put the sentence's grammar
   * in the screen instead of in the catalog, and Hindi and English do not agree
   * about where the name goes.
   */
  titleValues?: Record<string, string>;
  descriptionKey?: MessageKey;
  children: ReactNode;
  /** Sticky action row pinned below the content. */
  footer?: ReactNode;
  className?: string;
}

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Sheet({
  open,
  onClose,
  titleKey,
  titleValues,
  descriptionKey,
  children,
  footer,
  className,
}: SheetProps) {
  const t = useTranslations();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      previous?.focus?.();
    };
  }, [open, onKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      {/* scrim — tapping it closes, matching the visible close control */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-brand-navy-deep/60"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={descriptionKey ? `${id}-desc` : undefined}
        className={cn(
          "relative flex max-h-[90dvh] w-full flex-col rounded-t-sheet bg-surface shadow-sheet",
          "md:max-w-md md:rounded-sheet",
          "motion-safe:animate-[sheet-in_var(--motion-duration-enter)_var(--motion-easing-enter)]",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 p-4">
          <div className="flex flex-col gap-1">
            <h2 id={`${id}-title`} className="text-h2 font-serif text-ink-primary">
              {t(titleKey, titleValues)}
            </h2>
            {descriptionKey ? (
              <p id={`${id}-desc`} className="text-caption text-ink-muted">
                {t(descriptionKey)}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("ui.close")}
            className={cn(
              "inline-flex shrink-0 items-center justify-center rounded-portrait text-ink-primary",
              touchTarget,
              focusRing,
            )}
          >
            <X aria-hidden="true" strokeWidth={ICON_STROKE} />
          </button>
        </div>
        <div className="overflow-y-auto px-4 pb-4">{children}</div>
        {footer ? <div className="border-t border-border-subtle p-4">{footer}</div> : null}
      </div>
    </div>
  );
}
