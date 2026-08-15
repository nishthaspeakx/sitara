"use client";

/**
 * S27 Family — §29.1 `/you/family`, §30.5's family-privacy rule.
 *
 * §30.5: "family-member guidance appears in the account-holder's spaces only;
 * per-member filter exists; no member-facing views in Phase 1." So this list
 * lives inside `/you` and nowhere else, and every member reachable from it is
 * one the session owns — the API is scoped to her, and a member id that is not
 * hers resolves to nothing rather than to somebody else's record.
 *
 * ── §45's memorial state is rendered here, not only on the detail screen ───
 *
 * A member who is `in_memory` stays in this list — §45.2 is explicit: "the
 * member remains in the family list, in her chart history and in every past
 * artefact". What changes is that she is MARKED, so the list tells the truth
 * about a person who has died without removing her from it. Rendering the state
 * only on S28 would make the gentle option look, from here, exactly like
 * nothing had happened.
 *
 * The mark is a label, never a colour or an opacity: §29.4 forbids state
 * carried by colour alone, and a dimmed row would be the visual language of
 * "disabled" applied to a person.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { Chip, EmptyState, ErrorState, FamilyCard, Skeleton } from "@/components/ui";
import { MEMORIAL_COPY } from "@/lib/deletion-scope";
import { useRouter } from "@/i18n/navigation";
import { loadMembers, type FamilyMember } from "@/lib/family";

type View =
  | { kind: "loading" }
  | { kind: "ready"; members: FamilyMember[] }
  | { kind: "error"; error: ErrorEnvelope };

export default function FamilyPage() {
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });

  const refresh = useCallback(async () => {
    const result = await loadMembers();
    setView(
      result.ok ? { kind: "ready", members: result.data } : { kind: "error", error: result.error },
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <YouShell testId="family" titleKey="family.title" subtitleKey="family.subtitle">
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" && view.members.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <EmptyState id="family" />
        </div>
      ) : null}

      {view.kind === "ready" && view.members.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {view.members.map((member) => {
            // BARE identifiers, for i18n-lint's literal template match.
            const relation = member.relation;
            return (
              <li
                key={member.member_id}
                data-testid="family-member"
                data-member-id={member.member_id}
                data-memorial={member.memorial_state}
              >
                <FamilyCard
                  name={member.name}
                  relation={t(`family.relation.${relation}`)}
                  hasBirthDetails={member.has_birth_details}
                  onOpen={() => router.push(`/you/family/${member.member_id}`)}
                />
                {member.memorial_state === "in_memory" ? (
                  // A label, so it survives greyscale and a screen reader
                  // (§29.4). Never a dimmed row.
                  <div className="px-1 pt-1">
                    <Chip>{t(MEMORIAL_COPY.badgeKey)}</Chip>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </YouShell>
  );
}
