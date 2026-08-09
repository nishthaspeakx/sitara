"use client";

/**
 * Button — §24.3 foundation.
 * Variants: primary (gold) · secondary (navy outline) · tertiary (text).
 * States:  default · pressed · loading · disabled.
 *
 * The gold fill is 2.26:1 against cream, so a primary button carries a
 * `border-strong` boundary to satisfy WCAG 1.4.11 — the fill identifies the
 * control, the boundary makes it findable. At night `bg-brand-navy` sits on a
 * navy canvas, so the secondary variant needs the same boundary for the
 * opposite reason.
 */

import { useTranslations } from "next-intl";
import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";

import { cn, controlHeight, focusRing, motionStandard, touchTarget } from "./_util";

export type ButtonVariant = "primary" | "secondary" | "tertiary";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-interactive-primary text-on-gold border border-border-strong " +
    "hover:bg-interactive-hover active:bg-interactive-pressed " +
    "disabled:bg-interactive-disabled disabled:text-ink-muted disabled:border-border-subtle",
  secondary:
    "bg-transparent text-ink-primary border border-border-strong " +
    "hover:bg-surface-sunken active:bg-surface-sunken " +
    "disabled:text-ink-muted disabled:border-border-subtle",
  tertiary:
    "bg-transparent text-ink-primary border border-transparent underline decoration-gold underline-offset-4 " +
    "hover:bg-surface-sunken active:bg-surface-sunken " +
    "disabled:text-ink-muted disabled:no-underline",
};

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: ButtonVariant;
  loading?: boolean;
  /** Rendered before the label; inherits currentColor. */
  icon?: ReactNode;
  children: ReactNode;
  fullWidth?: boolean;
  /** React 19 passes ref as an ordinary prop for function components. */
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = "primary",
  loading = false,
  icon,
  children,
  fullWidth = false,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  const t = useTranslations();
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-chip px-4 text-body font-ui",
        controlHeight,
        touchTarget,
        motionStandard,
        focusRing,
        VARIANT[variant],
        fullWidth && "w-full",
        "disabled:cursor-not-allowed",
        className,
      )}
    >
      {loading ? (
        <>
          {/* nothing loops except Tara's breathing and the star twinkle (§0.12);
              the busy affordance is a pulse that stops under reduced motion */}
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-portrait bg-current animate-pulse motion-reduce:animate-none motion-off:animate-none"
          />
          <span>{t("ui.button.loading")}</span>
        </>
      ) : (
        <>
          {icon ? <span aria-hidden="true">{icon}</span> : null}
          {children}
        </>
      )}
    </button>
  );
}
