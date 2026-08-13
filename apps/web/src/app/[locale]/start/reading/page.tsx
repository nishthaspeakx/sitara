"use client";

/**
 * S13 — the first reading (§29.1 `/start/reading`, §0.17 minute 3, §24.4).
 *
 * "full-screen Tara ceremony → reading cards → first question → memory chip →
 * brief-time picker", CTA "meet your mornings".
 *
 * `tests/ceremony-degradation.spec.ts` was written before this file and is its
 * contract. Four invariants hold on every path through this screen:
 *
 *   1. no `aria-busy` element survives the deadline
 *   2. what replaces the skeleton is a real localised sentence or an honest
 *      ErrorState — never an empty region
 *   3. no raw i18n key can leak, because the client expands a closed set of
 *      line IDs into declared dynamic keys rather than rendering a message key
 *      the server named
 *   4. "meet your mornings" always works
 *
 * (4) is the one worth defending. §28.1 says onboarding "never exits to blank",
 * and a ceremony the user can neither complete nor leave is the worst version
 * of that. So the CTA is rendered from the first frame and is never gated on
 * the reading arriving.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import {
  Button,
  Card,
  ConfidenceChip,
  ErrorState,
  MemoryChip,
  SectionHeader,
  Skeleton,
  Slider,
  TaraPresence,
  VerifiedSourceRow,
} from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { track } from "@/lib/analytics";
import {
  CEREMONY_DEADLINE_MS,
  fetchFirstReading,
  patchState,
  STEPS,
  useOnboarding,
  type DegradeReason,
  type Reading,
  type ReadingLine,
} from "@/lib/onboarding";

/** §24.4: the picker is a Slider; 15-minute steps across the morning. */
const BRIEF_MIN = 5 * 60;
const BRIEF_MAX = 11 * 60;
const BRIEF_STEP = 15;
const toClock = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** The §34.4 envelope the deadline produces — retryable, and honest about why. */
const TIMEOUT_ENVELOPE: ErrorEnvelope = {
  code: "SYS_UNAVAILABLE",
  message_key: "errors.sys.unavailable",
  trace_id: "",
  retryable: true,
};

export default function ReadingPage() {
  const t = useTranslations();
  const router = useRouter();
  const { priorities, briefTime, set } = useOnboarding();

  const [reading, setReading] = useState<Reading | null>(null);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  /** Set when the client deadline fired before anything arrived. */
  const [timedOut, setTimedOut] = useState(false);
  const [memoryOffered, setMemoryOffered] = useState(true);
  const [finishing, setFinishing] = useState(false);
  const [briefMinutes, setBriefMinutes] = useState(() => {
    const [h, m] = briefTime.split(":").map(Number);
    return (h || 7) * 60 + (m || 0);
  });
  const startedAt = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTimedOut(false);
    startedAt.current = Date.now();

    const controller = new AbortController();
    // The deadline is the client's own, and it is not a duplicate of the
    // server's: a server deadline cannot rescue a request that never gets a
    // response at all — a dropped connection, a proxy that holds the socket
    // open. That is the case this timer exists for, and it is the one that
    // produces a spinner nobody can escape.
    const deadline = window.setTimeout(() => {
      controller.abort();
      setTimedOut(true);
      setLoading(false);
    }, CEREMONY_DEADLINE_MS);

    const result = await fetchFirstReading(controller.signal);
    window.clearTimeout(deadline);

    if (result.ok) {
      setReading(result.data);
      setLoading(false);
      track("first_reading_shown", {
        status: result.data.status,
        confidence: result.data.confidence,
        degrade_reason: result.data.degrade_reason,
        line_count: result.data.lines.length,
        latency_ms: Date.now() - startedAt.current,
        locale: document.documentElement.lang,
      });
      return;
    }
    // An aborted fetch resolves through the client's own envelope; the timeout
    // state above already describes it, so it must not also render as a
    // generic error and give the screen two voices at once.
    if (!controller.signal.aborted) {
      setError(result.error);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** §0.17 minute 5: the brief-time promise, then Today. */
  async function finish() {
    setFinishing(true);
    const result = await patchState({
      brief_time: toClock(briefMinutes),
      completed_step: STEPS.READING,
    });
    setFinishing(false);
    if (!result.ok) {
      // This used to advance regardless, which reads as generous and strands
      // her permanently: `next_step` is the LOWEST unrecorded step, so an
      // unrecorded step 13 drops her back into the ceremony on every future
      // launch, with nothing ever explaining why. Every other step surfaces
      // its failure and stays put; so does this one.
      setError(result.error);
      return;
    }
    router.push("/today");
  }

  const degrade: DegradeReason | null = timedOut ? "timeout" : (reading?.degrade_reason ?? null);
  const showTara = !error && !(reading?.status === "unavailable");

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12" data-testid="reading-ceremony">
      {/* §29.5: no Tara on an error surface. She is the ceremony's host, not a
          mascot to keep on stage while the product apologises. */}
      {showTara ? (
        <div className="flex justify-center">
          <TaraPresence size="lg" state="calm_guidance" still showAiLabel />
        </div>
      ) : null}

      <SectionHeader titleKey="start.reading.title" subtitleKey="start.reading.subtitle" />

      {loading ? (
        // §24.6: a skeleton mirroring the final layout — never a spinner on a
        // content surface.
        <Skeleton variant="brief" count={3} />
      ) : null}

      {!loading && reading && reading.lines.length > 0 ? (
        <Card as="section" measure className="flex flex-col gap-4">
          {reading.lines.map((line) => (
            <p key={line.id} className="text-body text-ink-primary" data-testid="reading-line">
              {renderLine(t, line)}
            </p>
          ))}
          {/* §30.4 — the row states what is TRUE today. The M8 live run found
              this hardcoded to "verified against 2 sources" while both panchang
              vendors were down and only Layer A had answered: a real fact, a
              resolving citation, and a badge that lied. */}
          <VerifiedSourceRow state={reading.source_state} />
        </Card>
      ) : null}

      {!loading && (reading || timedOut) ? (
        <div data-testid="reading-confidence" data-state={reading?.confidence ?? "cannot_calculate"}>
          <ConfidenceChip
            state={(reading?.confidence ?? "cannot_calculate") as never}
            withDescription
          />
        </div>
      ) : null}

      {degrade ? (
        <p className="text-body text-ink-muted" data-testid="reading-degraded-note">
          {t(`start.reading.degraded.${degrade}`)}
        </p>
      ) : null}

      {/* §28.2's missing-birth-time variant: ASK, and make the asking a route
          back to the question rather than a note the user can do nothing with. */}
      {reading?.missing.includes("birth_time") ? (
        <Button
          variant="secondary"
          data-testid="reading-add-birth-time"
          // S06, not S07. The birth row is written WHOLE through §13's facade —
          // date, place, time and accuracy in one call — so S07 alone cannot
          // submit and correctly bounces back when it has no date or place.
          // Landing the user on the step that can actually complete is the
          // difference between an affordance and a redirect she did not ask for.
          onClick={() => router.push("/start/birth")}
        >
          {t("start.reading.add_birth_time")}
        </Button>
      ) : null}

      {error ? <ErrorState error={error} onRetry={() => void load()} /> : null}
      {timedOut && !reading ? (
        <ErrorState error={TIMEOUT_ENVELOPE} onRetry={() => void load()} />
      ) : null}

      {/* §0.17 minute 4 — the first memory chip, offered from what she told us
          rather than from anything Tara inferred. */}
      {!loading && memoryOffered && priorities.length > 0 ? (
        <MemoryChip
          state="offer"
          summary={t("start.reading.memory_offer", {
            priority: t(`start.priorities.option.${priorities[0]}`),
          })}
          onAccept={() => setMemoryOffered(false)}
          onDecline={() => setMemoryOffered(false)}
        />
      ) : null}

      {/* §0.17 minute 5 — the morning-brief promise. */}
      <Card as="section" className="flex flex-col gap-3">
        <p className="font-serif text-h3 text-ink-primary">{t("start.reading.brief_time.title")}</p>
        <p className="text-caption text-ink-muted">{t("start.reading.brief_time.body")}</p>
        <Slider
          labelKey="start.reading.brief_time.label"
          min={BRIEF_MIN}
          max={BRIEF_MAX}
          step={BRIEF_STEP}
          value={briefMinutes}
          format={toClock}
          onChange={(value) => {
            setBriefMinutes(value);
            set({ briefTime: toClock(value) });
          }}
        />
      </Card>

      {/* Rendered from the first frame, on every path. This is invariant (4). */}
      <Button fullWidth loading={finishing} data-testid="reading-continue" onClick={() => void finish()}>
        {t("start.reading.continue")}
      </Button>
    </main>
  );
}

/**
 * Expand a line ID into copy.
 *
 * The server sends an ID from a closed set, never a message key: a
 * server-supplied key is invisible to `i18n-lint`'s source scan, so a typo'd
 * one reaches the user as a raw dotted path in Hindi. Both templates below are
 * declared in `packages/i18n/src/dynamic-keys.json`, so every key they can
 * produce is verified to exist in all three catalogs at build time.
 */
function renderLine(t: ReturnType<typeof useTranslations>, line: ReadingLine): string {
  if (line.id === "observation" && line.house) {
    return t(`start.reading.observation.${line.house}`, line.values);
  }
  return t(`start.reading.line.${line.id}`, line.values);
}
