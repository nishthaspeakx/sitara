"use client";

/**
 * S28 Family member — §29.1 `/you/family/[id]`, §32.15 and §45.
 *
 * ── The chart is CC-007's diagram, drawn ──────────────────────────────────
 *
 * `KundliChart` shipped its contract and an honest unbuilt state in M7 so the
 * §24.3 count was true at 49; M10 drew it, and this is the first product
 * surface that renders one. Every placement arrives as an engine fact resolved
 * by `lib/chart.ts` — no ephemeris, no house maths here — and the mapping from
 * the API's rashi NAME to the diagram's index is by name, never by the position
 * of a house in the response array. `lib/chart.ts` records why at length: a
 * positional read draws a chart that is internally consistent, plausible, and
 * wrong to the one user who has had hers on paper for forty years.
 *
 * **A member with no birth details gets no chart and is told so** (§5.3: the
 * engine declines rather than guessing, and so does the screen). The API
 * answers `ASTRO_INSUFFICIENT_BIRTH_DATA`, which is non-retryable, so
 * `ErrorState` would render a retry control for something no retry can fix —
 * hence a plain sentence instead.
 *
 * ── One control opens §45.3's sheet, and it is not called "delete" ─────────
 *
 * §32.15 puts the "in memory of" conversion on the SAME sheet as the deletion
 * and §45.3 puts it first. A control labelled "Delete" would mean the gentle
 * option is found only by someone who already knew it was there — which, at the
 * moment this sheet exists for, is nobody. So the control is
 * `family.record_action` and the sheet decides the order from
 * `FAMILY_SHEET_ORDER`.
 */

import { useTranslations } from "next-intl";
import { use, useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { FamilyRecordSheet } from "@/components/deletion/FamilyRecordSheet";
import { YouShell } from "@/components/you/YouShell";
import { Button, Card, ErrorState, KundliChart, Skeleton } from "@/components/ui";
import type { KundliStyle } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { loadChart, toKundliHouses, type Chart } from "@/lib/chart";
import { MEMORIAL_COPY } from "@/lib/deletion-scope";
import {
  deleteMember,
  loadMember,
  loadMemoriesAbout,
  setMemorialState,
  type FamilyMember,
  type MemoryAboutMember,
} from "@/lib/family";

type View =
  | { kind: "loading" }
  | { kind: "ready"; member: FamilyMember; chart: Chart | null; candidates: MemoryAboutMember[] }
  | { kind: "missing" }
  | { kind: "error"; error: ErrorEnvelope };

export default function FamilyMemberPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sheetError, setSheetError] = useState<ErrorEnvelope | null>(null);
  // CC-007: "neither is a fallback for the other" — a reader of one cannot read
  // the other by squinting, which is why the switch exists at all. North is the
  // default; the choice is per-view and deliberately not persisted, because it
  // is how this reader reads a chart, not a fact about the chart.
  const [style, setStyle] = useState<KundliStyle>("north");

  // A BARE identifier, hoisted out of the JSX: `i18n-lint` matches the literal
  // template text against `dynamic-keys.json`, and it cannot expand a call or a
  // member expression — so it cannot verify one either. Same rule as
  // `ui.module.${module}`.
  const relation = view.kind === "ready" ? view.member.relation : "other";

  const refresh = useCallback(async () => {
    const member = await loadMember(id);
    if (!member.ok) {
      // A member she removed a moment ago is MISSING, not an error.
      setView(
        member.error.code === "SYS_VALIDATION"
          ? { kind: "missing" }
          : { kind: "error", error: member.error },
      );
      return;
    }

    // §32.15's candidates are read BEFORE the sheet can render its checkboxes:
    // the list has to be seen before it can be consented to.
    const [chart, candidates] = await Promise.all([
      member.data.has_birth_details
        ? loadChart({ localDate: todayFor(), subjectId: id })
        : Promise.resolve(null),
      loadMemoriesAbout(id),
    ]);

    setView({
      kind: "ready",
      member: member.data,
      chart: chart && chart.ok ? chart.data : null,
      candidates: candidates.ok ? candidates.data : [],
    });
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <YouShell
      testId="member"
      title={view.kind === "ready" ? view.member.name : undefined}
      titleKey={view.kind === "ready" ? undefined : "family.title"}
      withTabs={false}
      onBack={() => router.push("/you/family")}
    >
      {view.kind === "loading" ? <Skeleton variant="brief" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "missing" ? (
        <p data-testid="member-missing" className="text-body text-ink-muted">
          {t("family.not_found")}
        </p>
      ) : null}

      {view.kind === "ready" ? (
        <>
          <Card className="flex flex-col gap-2">
            <p className="text-body text-ink-primary">
              {t(`family.relation.${relation}`)}
            </p>
            <p className="text-caption text-ink-muted">
              {t(view.member.has_birth_details ? "family.birth_details" : "family.no_birth_details")}
            </p>
            {view.member.attested ? (
              // §13's attestation, stated rather than assumed. The account
              // holder asserted she may hold someone else's birth details, and
              // the record of that assertion is the legal basis for the row.
              <p className="text-caption text-ink-muted">{t("family.attested")}</p>
            ) : null}
            {view.member.memorial_state === "in_memory" ? (
              <p data-testid="member-memorial" className="text-caption text-ink-muted">
                {t(MEMORIAL_COPY.badgeKey)}
              </p>
            ) : null}
          </Card>

          {view.chart ? (
            // The chart names ITSELF, so there is no heading above it saying
            // one thing while the card says another — which is exactly what
            // the first Devanagari baseline of this screen showed.
            <KundliChart
              houses={toKundliHouses(view.chart)}
              confidence={view.chart.confidence as never}
              titleKey="family.chart_title"
              style={style}
              onStyleChange={setStyle}
            />
          ) : (
            <>
              <h2 className="pt-2 font-serif text-h3 text-ink-primary">
                {t("family.chart_title")}
              </h2>
              {/* §5.3 in one sentence. Not an `ErrorState`: the envelope is
                  non-retryable, and a retry control for a chart that cannot
                  exist would be a button that can only ever fail. */}
              <p data-testid="member-chart-unavailable" className="text-body text-ink-muted">
                {t("family.chart_unavailable")}
              </p>
            </>
          )}

          <h2 className="pt-2 font-serif text-h3 text-ink-primary">{t("family.memories_about")}</h2>
          {view.candidates.length === 0 ? (
            <p className="text-body text-ink-muted">{t("family.memories_none")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {view.candidates.map((candidate) => (
                <li key={candidate.memory_id} className="text-body text-ink-primary">
                  {candidate.content}
                </li>
              ))}
            </ul>
          )}

          {/* One control, §45.3's sheet. Deliberately not labelled "Delete". */}
          <Button
            variant="secondary"
            fullWidth
            data-testid="member-record"
            onClick={() => {
              setSheetError(null);
              setSheetOpen(true);
            }}
          >
            {t("family.record_action")}
          </Button>
        </>
      ) : null}

      {sheetOpen && view.kind === "ready" ? (
        <FamilyRecordSheet
          open
          onClose={() => setSheetOpen(false)}
          member={view.member}
          candidates={view.candidates}
          busy={busy}
          error={sheetError}
          onMemorial={async (state) => {
            setBusy(true);
            const result = await setMemorialState(view.member.member_id, state);
            setBusy(false);
            if (!result.ok) {
              setSheetError(result.error);
              return;
            }
            setSheetOpen(false);
            // Re-read rather than patching state locally: §45.2's guarantee is
            // about what the SERVER holds, and a screen that reported success
            // from its own optimism would be the one place that cannot.
            await refresh();
          }}
          onDelete={async (choice) => {
            setBusy(true);
            const result = await deleteMember(view.member.member_id, choice.memoryIds);
            setBusy(false);
            if (!result.ok) {
              setSheetError(result.error);
              return;
            }
            setSheetOpen(false);
            router.push("/you/family");
          }}
        />
      ) : null}
    </YouShell>
  );
}

/**
 * The chart's date.
 *
 * A natal chart does not depend on today at all — but `/v1/chart` takes
 * `local_date` because the same endpoint serves transit-bearing reads, and the
 * parameter is required. This is the one place in M10 that reads a clock, and
 * it is safe precisely because the answer cannot change the houses: S24's
 * reflection takes its date from the Today payload instead, because there the
 * day IS the record.
 */
function todayFor(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
