"use client";

/**
 * S04 — OTP verify `/start/verify` (§24.4): 6-digit code with resend timer.
 * Also hosts the §22.4 sign-up DOB step: the exchange answers
 * `errors.auth.dob_required` for a new account, and an under-18 date comes
 * back as AUTH_UNDERAGE with an honest in-locale explanation — no account.
 */

import { FirebaseError } from "firebase/app";
import { signInWithPhoneNumber } from "firebase/auth";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ErrorAlert, ProgressDots } from "@/components/onboarding";
import { Link, useRouter } from "@/i18n/navigation";
import { clearPendingAuth, getPendingPhone, setPendingPhone } from "@/lib/auth-flow";
import { firebaseAuth, invisibleRecaptcha } from "@/lib/firebase";
import { exchangeSession, firebaseErrorKey, isDobRequired } from "@/lib/session";

const RESEND_SECONDS = 60;

export default function VerifyPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();

  const pending = getPendingPhone();
  const hasFirebaseUser = () => firebaseAuth(locale).currentUser !== null;

  const [step, setStep] = useState<"otp" | "dob">("otp");
  const [code, setCode] = useState("");
  const [dob, setDob] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(RESEND_SECONDS);
  const recaptchaHost = useRef<HTMLDivElement>(null);

  // Arriving without an OTP in flight: a Google sign-in continues straight to
  // the DOB step; otherwise there is nothing to verify — back to S03.
  useEffect(() => {
    if (!pending) {
      if (hasFirebaseUser()) setStep("dob");
      else router.replace("/start/auth");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (step !== "otp" || resendIn <= 0) return;
    const timer = setInterval(() => setResendIn((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [step, resendIn]);

  async function finishExchange(dateOfBirth?: string) {
    const user = firebaseAuth(locale).currentUser;
    if (!user) {
      router.replace("/start/auth");
      return;
    }
    const result = await exchangeSession(await user.getIdToken(), {
      locale,
      dateOfBirth,
      deviceName: navigator.platform || "Web",
    });
    if (result.ok) {
      clearPendingAuth();
      router.push("/");
      return;
    }
    if (isDobRequired(result)) {
      setStep("dob");
      setErrorKey(null);
      setBusy(false);
      return;
    }
    setErrorKey(result.error.message_key);
    setBusy(false);
  }

  async function verifyCode(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !pending) return;
    setBusy(true);
    setErrorKey(null);
    try {
      await pending.confirmation.confirm(code.trim());
      await finishExchange();
    } catch (err) {
      setErrorKey(firebaseErrorKey(err instanceof FirebaseError ? err.code : ""));
      setBusy(false);
    }
  }

  async function resend() {
    if (busy || resendIn > 0 || !pending || !recaptchaHost.current) return;
    setBusy(true);
    setErrorKey(null);
    try {
      const auth = firebaseAuth(locale);
      const verifier = invisibleRecaptcha(auth, recaptchaHost.current);
      const confirmation = await signInWithPhoneNumber(auth, pending.phone, verifier);
      setPendingPhone(pending.phone, confirmation);
      setResendIn(RESEND_SECONDS);
    } catch (err) {
      setErrorKey(firebaseErrorKey(err instanceof FirebaseError ? err.code : ""));
    }
    setBusy(false);
  }

  async function submitDob(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !dob) return;
    setBusy(true);
    setErrorKey(null);
    await finishExchange(dob);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-8 p-8">
      <ProgressDots current={4} />

      {step === "otp" ? (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="font-serif text-display text-ink-primary">{t("verify.title")}</h1>
            <p className="text-h3 text-ink-muted">
              {t("verify.sent_to", { phone: pending?.phone ?? "" })}
            </p>
          </header>

          <form
            onSubmit={verifyCode}
            className="flex flex-col gap-4 rounded-card border border-line bg-surface p-6 shadow-card"
          >
            <label className="flex flex-col gap-2">
              <span className="text-caption text-ink-muted">{t("verify.code_label")}</span>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="rounded-chip border border-line bg-bg-canvas p-3 text-h2 tracking-widest text-ink-primary outline-none focus:border-gold"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-chip bg-brand-navy p-3 text-body text-on-brand disabled:opacity-60"
            >
              {busy ? t("verify.verifying") : t("verify.verify")}
            </button>
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={resend}
                disabled={busy || resendIn > 0}
                className="text-caption text-ink-primary decoration-gold underline underline-offset-4 disabled:text-ink-muted disabled:no-underline"
              >
                {resendIn > 0
                  ? t("verify.resend_in", { seconds: resendIn })
                  : t("verify.resend")}
              </button>
              <Link href="/start/auth" className="text-caption text-ink-primary decoration-gold underline underline-offset-4">
                {t("verify.change_number")}
              </Link>
            </div>
            <ErrorAlert messageKey={errorKey} />
          </form>
        </>
      ) : (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="font-serif text-display text-ink-primary">{t("dob.title")}</h1>
            <p className="text-h3 text-ink-muted">{t("dob.subtitle")}</p>
          </header>

          <form
            onSubmit={submitDob}
            className="flex flex-col gap-4 rounded-card border border-line bg-surface p-6 shadow-card"
          >
            <label className="flex flex-col gap-2">
              <span className="text-caption text-ink-muted">{t("dob.label")}</span>
              <input
                type="date"
                required
                value={dob}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDob(e.target.value)}
                className="rounded-chip border border-line bg-bg-canvas p-3 text-body text-ink-primary outline-none focus:border-gold"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-chip bg-brand-navy p-3 text-body text-on-brand disabled:opacity-60"
            >
              {t("dob.continue")}
            </button>
            <ErrorAlert messageKey={errorKey} />
          </form>
        </>
      )}

      <div ref={recaptchaHost} />
    </main>
  );
}
