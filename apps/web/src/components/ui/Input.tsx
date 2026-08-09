"use client";

/**
 * Input — §24.3 foundation. Types: text · date · time · phone-otp.
 *
 * §29.4: 48px height, **label above** (floating labels fail Indic scripts),
 * inline validation on blur, error text carries an icon as well as colour.
 * Errors arrive as §34.4 message KEYS so the copy is always in-locale.
 */

import { useTranslations } from "next-intl";
import { useId, type InputHTMLAttributes } from "react";

import { cn, controlHeight, focusRing, motionStandard, type MessageKey } from "./_util";

export type InputKind = "text" | "date" | "time" | "phone" | "otp";

const HTML_TYPE: Record<InputKind, string> = {
  text: "text",
  date: "date",
  time: "time",
  phone: "tel",
  otp: "text",
};

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  kind?: InputKind;
  labelKey: MessageKey;
  helperKey?: MessageKey;
  /** §34.4 message_key — never a raw string. */
  errorKey?: MessageKey | null;
}

export function Input({
  kind = "text",
  labelKey,
  helperKey,
  errorKey,
  className,
  id,
  ...rest
}: InputProps) {
  const t = useTranslations();
  const auto = useId();
  const inputId = id ?? auto;
  const helperId = `${inputId}-helper`;
  const errorId = `${inputId}-error`;
  const invalid = Boolean(errorKey);

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-caption text-ink-muted">
        {t(labelKey)}
      </label>
      <input
        {...rest}
        id={inputId}
        type={HTML_TYPE[kind]}
        inputMode={kind === "otp" ? "numeric" : kind === "phone" ? "tel" : undefined}
        autoComplete={kind === "otp" ? "one-time-code" : rest.autoComplete}
        aria-invalid={invalid || undefined}
        aria-describedby={cn(helperKey && helperId, invalid && errorId) || undefined}
        className={cn(
          "w-full rounded-chip border bg-surface px-3 text-body text-ink-primary",
          "placeholder:text-ink-muted",
          kind === "otp" && "tracking-widest text-center",
          controlHeight,
          motionStandard,
          focusRing,
          invalid ? "border-feedback-danger" : "border-border-strong",
          "disabled:bg-surface-sunken disabled:text-ink-muted disabled:cursor-not-allowed",
          className,
        )}
      />
      {helperKey && !invalid ? (
        <p id={helperId} className="text-caption text-ink-muted">
          {t(helperKey)}
        </p>
      ) : null}
      {invalid ? (
        <p id={errorId} role="alert" className="flex items-center gap-2 text-caption text-feedback-danger-text">
          {/* icon as well as colour — §29.4 never encodes state by colour alone */}
          <span aria-hidden="true">⚠</span>
          {t(errorKey as MessageKey)}
        </p>
      ) : null}
    </div>
  );
}
