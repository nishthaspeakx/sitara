"use client";

/**
 * FamilyCard — §24.3 Sitara-specific. A family member on S27/S28.
 *
 * §30.2: a member's timings use THEIR stored city, and birth details are
 * optional with an attestation. The card states which of those is true rather
 * than implying complete data — an incomplete member is normal, not an error,
 * so it carries a neutral chip and never a caution colour.
 */

import { CakeSlice, MapPin } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card } from "./Card";
import { ConfidenceChip } from "./ConfidenceChip";
import { ICON_STROKE, cn } from "./_util";

export interface FamilyCardProps {
  /** User data — a name, never a message key. */
  name: string;
  /** Relationship label, already localised. */
  relation: string;
  /** Their stored city; timings are computed for it (§30.2). */
  city?: string;
  /** The next date Sitara will remind about, already formatted in-locale. */
  upcoming?: string;
  /** False when birth details are absent — Moon-chart mode or none. */
  hasBirthDetails?: boolean;
  /** The member's own language tag, already localised. */
  languageLabel?: string;
  onOpen?: () => void;
  className?: string;
}

export function FamilyCard({
  name,
  relation,
  city,
  upcoming,
  hasBirthDetails = true,
  languageLabel,
  onOpen,
  className,
}: FamilyCardProps) {
  const t = useTranslations();
  return (
    <Card onClick={onOpen} className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="truncate font-serif text-h3 text-ink-primary">{name}</h3>
        <span className="shrink-0 text-caption text-ink-muted">{relation}</span>
      </div>

      <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-ink-muted">
        {city ? (
          <div className="flex items-center gap-1">
            <MapPin aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
            <dt className="sr-only">{t("ui.family.city")}</dt>
            <dd>{city}</dd>
          </div>
        ) : null}
        {upcoming ? (
          <div className="flex items-center gap-1">
            <CakeSlice aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
            <dt className="sr-only">{t("ui.family.upcoming")}</dt>
            <dd>{upcoming}</dd>
          </div>
        ) : null}
        {languageLabel ? (
          <div className="flex items-center gap-1">
            <dt className="sr-only">{t("ui.family.language")}</dt>
            <dd>{languageLabel}</dd>
          </div>
        ) : null}
      </dl>

      {!hasBirthDetails ? <ConfidenceChip state="tradition_general" withDescription /> : null}
    </Card>
  );
}
