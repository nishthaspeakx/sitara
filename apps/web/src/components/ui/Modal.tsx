"use client";

/**
 * Modal — §24.3 structure, marked "rare" in the spec. Reserved for a decision
 * that cannot be deferred and cannot be undone: hard-delete a memory, delete an
 * account. Everything else is a Sheet.
 *
 * The destructive action is never the pre-selected one.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useId, useRef, type ReactNode } from "react";

import { Button } from "./Button";
import { cn, type MessageKey } from "./_util";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  titleKey: MessageKey;
  bodyKey?: MessageKey;
  children?: ReactNode;
  confirmKey: MessageKey;
  cancelKey?: MessageKey;
  onConfirm: () => void;
  /** Confirm becomes a plain control, not the gold one, when destructive. */
  destructive?: boolean;
  busy?: boolean;
}

export function Modal({
  open,
  onClose,
  titleKey,
  bodyKey,
  children,
  confirmKey,
  cancelKey = "ui.cancel",
  onConfirm,
  destructive = false,
  busy = false,
}: ModalProps) {
  const t = useTranslations();
  const id = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    // focus lands on cancel, never on the irreversible action
    cancelRef.current?.focus();
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [open, onKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div aria-hidden="true" className="absolute inset-0 bg-brand-navy-deep/60" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={bodyKey ? `${id}-body` : undefined}
        className={cn(
          "relative flex w-full max-w-md flex-col gap-4 rounded-card bg-surface p-6 shadow-modal",
        )}
      >
        <h2 id={`${id}-title`} className="text-h2 font-serif text-ink-primary">
          {t(titleKey)}
        </h2>
        {bodyKey ? (
          <p id={`${id}-body`} className="text-body text-ink-muted">
            {t(bodyKey)}
          </p>
        ) : null}
        {children}
        <div className="flex flex-col-reverse gap-2 md:flex-row md:justify-end">
          <Button ref={cancelRef} variant="tertiary" onClick={onClose} className="md:w-auto">
            {t(cancelKey)}
          </Button>
          <Button
            variant={destructive ? "secondary" : "primary"}
            loading={busy}
            onClick={onConfirm}
            className="md:w-auto"
          >
            {t(confirmKey)}
          </Button>
        </div>
      </div>
    </div>
  );
}
