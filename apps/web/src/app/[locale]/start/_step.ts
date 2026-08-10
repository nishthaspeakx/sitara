"use client";

/**
 * The commit-and-advance move every onboarding screen makes.
 *
 * The ORDER is the contract: persist, and only then navigate. A screen that
 * navigates first cannot show its own error, because the component holding the
 * error state is gone by the time the request resolves.
 *
 * Not a §24.3 component — it has no DOM surface. It is the shape of "this
 * screen's answer is complete": persist it (§24.4's per-step persistence),
 * record the analytics event, then move to the next route. Twelve screens
 * hand-rolling that is twelve chances to forget the analytics event, and the
 * §0.17 ≥80% completion gate is measured from those events.
 */

import { useLocale } from "next-intl";
import { useCallback, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { useRouter } from "@/i18n/navigation";
import { track } from "@/lib/analytics";
import type { ApiResult } from "@/lib/api";
import { STEP_ROUTES, useOnboarding } from "@/lib/onboarding";

export function useStepCommit(step: number) {
  const router = useRouter();
  const locale = useLocale();
  const markComplete = useOnboarding((s) => s.markComplete);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorEnvelope | null>(null);

  const commit = useCallback(
    async <T,>(
      request: () => Promise<ApiResult<T>>,
      options: { next?: string; locale?: string } = {},
    ): Promise<boolean> => {
      if (busy) return false;
      setBusy(true);
      setError(null);
      const result = await request();
      if (!result.ok) {
        // §24.6: the screen renders the envelope and offers one retry. It does
        // NOT advance — an answer that failed to persist would be silently
        // lost on resume, which is the failure §24.4's rule exists to prevent.
        setError(result.error);
        setBusy(false);
        return false;
      }
      markComplete(step);
      track("onboarding_step_completed", { step, locale });
      const steps = Object.keys(STEP_ROUTES).map(Number).sort((a, b) => a - b);
      const nextStep = steps[steps.indexOf(step) + 1];
      const fallback = nextStep === undefined ? undefined : STEP_ROUTES[nextStep];
      // `options.locale` switches locale and advances in ONE navigation. Doing
      // them as two — switch, then commit — unmounts this component while the
      // request is in flight, so a failure sets state on a tree that is being
      // replaced and the user sees nothing happen at all. That was a live bug
      // on S02: a dead button, no error, no retry.
      router.push(options.next ?? fallback ?? "/today", { locale: options.locale });
      return true;
    },
    [busy, locale, markComplete, router, step],
  );

  return { commit, busy, error, clearError: () => setError(null) };
}

/**
 * The same move for a step that has NO server to persist to yet.
 *
 * §29.1 orders onboarding language (S02) → auth (S03), so S02 runs before any
 * session exists — and every onboarding write is behind `CurrentSession`
 * (§33.2's product identity comes from the §34.5 cookie). S02 used the
 * server-backed `useStepCommit` anyway: every tap 401'd, `commit` correctly
 * refused to advance a step it could not persist, and the FIRST screen of
 * onboarding was a dead end for anyone without a stale cookie. Same language or
 * different made no difference — there was nothing to authorise the write.
 *
 * Selecting and advancing are two different things, and so are "persisted" and
 * "recorded". This records the step locally and advances; the answer reaches
 * the server at the first authenticated moment, since `POST /auth/session`
 * already carries `locale` and stores it on the user. §24.4's per-step
 * persistence is not weakened — there is simply nowhere to put an answer until
 * there is a someone to put it against.
 *
 * Deliberately has no `error`: there is no request, so nothing can fail, and a
 * screen offering a retry for a call it never makes would be theatre.
 */
export function useLocalStepCommit(step: number) {
  const router = useRouter();
  const locale = useLocale();
  const markComplete = useOnboarding((s) => s.markComplete);
  const [busy, setBusy] = useState(false);

  const commit = useCallback(
    (options: { next?: string; locale?: string } = {}) => {
      if (busy) return;
      setBusy(true);
      markComplete(step);
      track("onboarding_step_completed", { step, locale });
      const steps = Object.keys(STEP_ROUTES).map(Number).sort((a, b) => a - b);
      const nextStep = steps[steps.indexOf(step) + 1];
      const fallback = nextStep === undefined ? undefined : STEP_ROUTES[nextStep];
      router.push(options.next ?? fallback ?? "/today", { locale: options.locale });
    },
    [busy, locale, markComplete, router, step],
  );

  return { commit, busy };
}
