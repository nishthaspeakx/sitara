"use client";

/**
 * Onboarding scaffolding (§24.4).
 *
 * ProgressDots now lives in the §24.3 library and is re-exported here so the
 * onboarding screens keep their import path while there is exactly ONE
 * implementation — a second copy is the one-off component §24.3 forbids.
 */

import { useTranslations } from "next-intl";

export { ProgressDots, ONBOARDING_STEPS } from "./ui/ProgressDots";

/** Renders a §34.4 message_key through the catalogs — never raw English. */
export function ErrorAlert({ messageKey }: { messageKey: string | null }) {
  const t = useTranslations();
  if (!messageKey) return null;
  return (
    <p role="alert" className="text-body text-feedback-danger-text">
      {t(messageKey)}
    </p>
  );
}
