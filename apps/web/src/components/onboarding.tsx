"use client";

/** Shared onboarding scaffolding (§24.4): progress dots + envelope-key errors. */

import { useTranslations } from "next-intl";

export const ONBOARDING_STEPS = 13;

export function ProgressDots({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2" aria-hidden="true">
      {Array.from({ length: ONBOARDING_STEPS }, (_, i) => (
        <span
          key={i}
          className={`h-1 w-1 rounded-portrait ${
            i + 1 === current ? "bg-gold" : i + 1 < current ? "bg-brand-navy" : "bg-line"
          }`}
        />
      ))}
    </div>
  );
}

/** Renders a §34.4 message_key through the catalogs — never raw English. */
export function ErrorAlert({ messageKey }: { messageKey: string | null }) {
  const t = useTranslations();
  if (!messageKey) return null;
  return (
    <p role="alert" className="text-body text-danger">
      {t(messageKey)}
    </p>
  );
}
