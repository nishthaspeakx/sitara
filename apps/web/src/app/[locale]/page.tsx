"use client";

/**
 * S01 — launch (§29.1 `/`, §0.11).
 *
 * "skippable anim; →S02 or Today". The sequence runs, then this decides where
 * the user lands: an authenticated user with a finished stack goes to Today,
 * everyone else enters the onboarding stack at whichever step they left off.
 *
 * The resume probe runs CONCURRENTLY with the animation rather than after it.
 * §0.11 budgets "cold-start-to-interactive (animation skipped) ≤2.5s p75", and
 * a request that starts only when the last frame lands turns a 5.5s ceremony
 * into 5.5s plus a round trip — the one place where the sequence would actually
 * be costing the user time rather than giving her something.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useRouter } from "@/i18n/navigation";
import { fetchState, STEP_ROUTES, STEPS, useOnboarding } from "@/lib/onboarding";

import { LaunchSequence } from "./_launch/LaunchSequence";

export default function LaunchPage() {
  const router = useRouter();
  const setStore = useOnboarding((s) => s.set);
  const destination = useRef<string | null>(null);
  const [sequenceDone, setSequenceDone] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const result = await fetchState(controller.signal);
      if (!result.ok) {
        // Unauthenticated, or the API is unreachable. Either way the honest
        // destination is the start of the stack — never a blank screen and
        // never an error on the very first frame of the product (§24.6).
        destination.current = STEP_ROUTES[STEPS.LANGUAGE]!;
        return;
      }
      const state = result.data;
      setStore({
        completedSteps: state.completed_steps,
        nextStep: state.next_step,
        hasBirthDetails: state.has_birth_details,
        interest: state.interest,
        priorities: state.priorities,
        displayName: state.display_name ?? "",
        briefTime: state.brief_time ?? "07:00",
        voiceEnabled: state.voice_enabled,
      });
      destination.current = state.completed_steps.includes(STEPS.READING)
        ? "/today"
        : (STEP_ROUTES[state.next_step] ?? STEP_ROUTES[STEPS.LANGUAGE]!);
    })();
    return () => controller.abort();
  }, [setStore]);

  const onFinished = useCallback(() => setSequenceDone(true), []);

  useEffect(() => {
    if (!sequenceDone) return;
    // §0.11: skip "lands on Home in ≤300ms". If the probe has not answered yet
    // the stack's own resume guard corrects the landing, so this never waits.
    router.replace(destination.current ?? STEP_ROUTES[STEPS.LANGUAGE]!);
  }, [sequenceDone, router]);

  return (
    <main className="min-h-screen bg-brand-navy-deep">
      <LaunchSequence onFinished={onFinished} />
    </main>
  );
}
