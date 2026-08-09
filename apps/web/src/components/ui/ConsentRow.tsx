"use client";

/**
 * ConsentRow — §24.3 feedback. One entry in the consent ledger (S36).
 *
 * A ledger row is a record, not a control: it states what was agreed, when, and
 * on which policy version, and offers withdrawal where withdrawal is possible.
 * Where consent is required for the service to exist at all, that is said in
 * words rather than shown as a disabled switch with no explanation.
 */

import { useTranslations } from "next-intl";

import { Toggle } from "./Toggle";
import { cn, focusRing, type MessageKey } from "./_util";

export interface ConsentRowProps {
  labelKey: MessageKey;
  descriptionKey?: MessageKey;
  granted: boolean;
  /** Formatted in-locale. */
  grantedOn?: string;
  /** Policy version this was agreed against. */
  policyVersion?: string;
  onChange?: (granted: boolean) => void;
  /** True when the service cannot run without it — explained, not disabled silently. */
  required?: boolean;
  onOpenPolicy?: () => void;
  className?: string;
}

export function ConsentRow({
  labelKey,
  descriptionKey,
  granted,
  grantedOn,
  policyVersion,
  onChange,
  required = false,
  onOpenPolicy,
  className,
}: ConsentRowProps) {
  const t = useTranslations();
  return (
    <div className={cn("flex flex-col gap-2 border-b border-border-subtle py-3", className)}>
      {required || !onChange ? (
        <div className="flex flex-col gap-1">
          <span className="text-body text-ink-primary">{t(labelKey)}</span>
          {descriptionKey ? (
            <span className="text-caption text-ink-muted">{t(descriptionKey)}</span>
          ) : null}
          <span className="text-caption text-ink-muted">{t("ui.consent.required")}</span>
        </div>
      ) : (
        <Toggle
          labelKey={labelKey}
          descriptionKey={descriptionKey}
          checked={granted}
          onChange={onChange}
        />
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-ink-muted">
        {grantedOn ? <span>{t("ui.consent.granted_on", { date: grantedOn })}</span> : null}
        {policyVersion ? (
          <span className="tabular-nums">{t("ui.consent.policy_version", { version: policyVersion })}</span>
        ) : null}
        {onOpenPolicy ? (
          <button
            type="button"
            onClick={onOpenPolicy}
            className={cn(
              "rounded-chip px-2 py-1 text-ink-primary underline decoration-gold underline-offset-4",
              focusRing,
            )}
          >
            {t("ui.consent.read_policy")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
