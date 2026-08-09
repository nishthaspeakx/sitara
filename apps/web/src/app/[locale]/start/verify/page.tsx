"use client";

/**
 * S04 — OTP verify (§29.1 `/start/verify`, §24.4, §22.4).
 *
 * Two steps in one route, because they are one question from the user's side:
 * confirm the code, and — for a NEW account only — give a date of birth so the
 * §22.4 age gate can run. The exchange answers `errors.auth.dob_required` when
 * it needs the second, so the screen never guesses which it is.
 *
 * §37.2 governs what happens next: the gate is evaluated in the westernmost
 * zone the evidence permits, and an under-18 date comes back as AUTH_UNDERAGE
 * with an honest in-locale explanation and no account. That refusal is a legal
 * act, and the screen states it plainly rather than dressing it as an error.
 *
 * Rebuilt on the §24.3 library in M8 — the logic is M1's.
 */

import { FirebaseError } from "firebase/app";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { Button, Card, ErrorState, Input, SectionHeader } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { clearPendingAuth, getPendingPhone, setPendingPhone } from "@/lib/auth-flow";
import { authClient } from "@/lib/auth-client";
import { patchState, STEPS } from "@/lib/onboarding";
import { exchangeSession, firebaseErrorKey, isDobRequired } from "@/lib/session";

import { useStepCommit } from "../_step";

const RESEND_SECONDS = 60;

function envelope(messageKey: string): ErrorEnvelope {
  return { code: "AUTH_INVALID_TOKEN", message_key: messageKey, trace_id: "", retryable: true };
}

export default function VerifyPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  useStepCommit(STEPS.VERIFY);

  const pending = getPendingPhone();

  const [step, setStep] = useState<"otp" | "dob">("otp");
  const [code, setCode] = useState("");
  const [dob, setDob] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const [resendIn, setResendIn] = useState(RESEND_SECONDS);
  const recaptchaHost = useRef<HTMLDivElement>(null);

  // Arriving without an OTP in flight: a Google sign-in continues straight to
  // the DOB step; otherwise there is nothing to verify — back to S03.
  useEffect(() => {
    if (pending) return;
    void (async () => {
      const token = await authClient.currentIdToken(locale);
      if (token) setStep("dob");
      else router.replace("/start/auth");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (step !== "otp" || resendIn <= 0) return;
    const timer = setInterval(() => setResendIn((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [step, resendIn]);

  async function finishExchange(idToken: string, dateOfBirth?: string) {
    const result = await exchangeSession(idToken, {
      locale,
      dateOfBirth,
      deviceName: navigator.platform || "Web",
    });
    if (result.ok) {
      clearPendingAuth();
      // S03 and S04 are the only steps that cannot record themselves as they
      // happen: there is no session to PATCH against until the exchange
      // succeeds. Recording them here is not bookkeeping — §24.4's resume takes
      // "where to continue" from the LOWEST unrecorded step, so without this a
      // user who had signed in, consented and entered her birth details would
      // come back to the sign-up screen.
      await patchState({ completed_step: STEPS.AUTH });
      await patchState({ completed_step: STEPS.VERIFY });
      router.push("/start/consent");
      return;
    }
    if (isDobRequired(result)) {
      setStep("dob");
      setError(null);
      setBusy(false);
      return;
    }
    setError(result.error);
    setBusy(false);
  }

  async function verifyCode(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !pending) return;
    setBusy(true);
    setError(null);
    try {
      const idToken = await pending.confirmation.confirm(code.trim());
      await finishExchange(idToken);
    } catch (err) {
      setError(envelope(firebaseErrorKey(err instanceof FirebaseError ? err.code : "")));
      setBusy(false);
    }
  }

  async function resend() {
    if (busy || resendIn > 0 || !pending || !recaptchaHost.current) return;
    setBusy(true);
    setError(null);
    try {
      const next = await authClient.startPhoneSignIn(
        pending.phone,
        recaptchaHost.current,
        locale,
      );
      setPendingPhone(pending.phone, next);
      setResendIn(RESEND_SECONDS);
    } catch (err) {
      setError(envelope(firebaseErrorKey(err instanceof FirebaseError ? err.code : "")));
    }
    setBusy(false);
  }

  async function submitDob(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !dob) return;
    setBusy(true);
    setError(null);
    const token = await authClient.currentIdToken(locale);
    if (!token) {
      router.replace("/start/auth");
      return;
    }
    await finishExchange(token, dob);
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      {step === "otp" ? (
        <>
          <SectionHeader titleKey="verify.title" />
          <p className="text-body text-ink-muted">
            {t("verify.sent_to", { phone: pending?.phone ?? "" })}
          </p>

          <Card as="section">
            <form onSubmit={verifyCode} className="flex flex-col gap-4">
              <Input
                kind="otp"
                labelKey="verify.code_label"
                autoComplete="one-time-code"
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                data-testid="otp-input"
              />
              <Button type="submit" fullWidth loading={busy} data-testid="otp-verify">
                {t("verify.verify")}
              </Button>
              <div className="flex items-center justify-between">
                <Button
                  type="button"
                  variant="tertiary"
                  onClick={() => void resend()}
                  disabled={busy || resendIn > 0}
                >
                  {resendIn > 0 ? t("verify.resend_in", { seconds: resendIn }) : t("verify.resend")}
                </Button>
                <Link
                  href="/start/auth"
                  className="text-caption text-ink-primary underline decoration-gold underline-offset-4"
                >
                  {t("verify.change_number")}
                </Link>
              </div>
            </form>
          </Card>
        </>
      ) : (
        <>
          <SectionHeader titleKey="dob.title" subtitleKey="dob.subtitle" />
          <Card as="section">
            <form onSubmit={submitDob} className="flex flex-col gap-4">
              <Input
                kind="date"
                labelKey="dob.label"
                required
                value={dob}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDob(e.target.value)}
                data-testid="dob-input"
              />
              <Button type="submit" fullWidth loading={busy} data-testid="dob-continue">
                {t("dob.continue")}
              </Button>
            </form>
          </Card>
        </>
      )}

      {error ? <ErrorState error={error} onRetry={() => setError(null)} /> : null}

      <div ref={recaptchaHost} />
    </main>
  );
}
