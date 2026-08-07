"use client";

/**
 * S03 — Sign-up `/start/auth` (§24.4, §28.1): region-ordered auth buttons +
 * phone field. Phone OTP + Google are P0; Apple is a config-flagged stub
 * (§26.1 decision log). All copy via i18n keys, tokens-only styling.
 */

import { FirebaseError } from "firebase/app";
import { GoogleAuthProvider, signInWithPhoneNumber, signInWithPopup } from "firebase/auth";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { ErrorAlert, ProgressDots } from "@/components/onboarding";
import { useRouter } from "@/i18n/navigation";
import { setPendingPhone } from "@/lib/auth-flow";
import { APPLE_SIGNIN_ENABLED, firebaseAuth, invisibleRecaptcha } from "@/lib/firebase";
import { normalizeIndianPhone } from "@/lib/phone";
import { exchangeSession, firebaseErrorKey, isDobRequired } from "@/lib/session";

export default function AuthPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();

  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const recaptchaHost = useRef<HTMLDivElement>(null);

  async function startPhoneSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !recaptchaHost.current) return;
    setBusy(true);
    setErrorKey(null);
    const auth = firebaseAuth(locale);
    try {
      const e164 = normalizeIndianPhone(phone);
      const verifier = invisibleRecaptcha(auth, recaptchaHost.current);
      const confirmation = await signInWithPhoneNumber(auth, e164, verifier);
      setPendingPhone(e164, confirmation);
      router.push("/start/verify");
    } catch (err) {
      console.warn("[auth] phone sign-in failed:", err);
      setErrorKey(firebaseErrorKey(err instanceof FirebaseError ? err.code : ""));
      setBusy(false);
    }
  }

  async function googleSignIn() {
    if (busy) return;
    setBusy(true);
    setErrorKey(null);
    const auth = firebaseAuth(locale);
    try {
      const cred = await signInWithPopup(auth, new GoogleAuthProvider());
      const result = await exchangeSession(await cred.user.getIdToken(), {
        locale,
        deviceName: navigator.platform || "Web",
      });
      if (result.ok) {
        router.push("/");
        return;
      }
      if (isDobRequired(result)) {
        router.push("/start/verify"); // continues as the DOB step (§22.4 gate)
        return;
      }
      setErrorKey(result.error.message_key);
      setBusy(false);
    } catch (err) {
      setErrorKey(firebaseErrorKey(err instanceof FirebaseError ? err.code : ""));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-8 p-8">
      <ProgressDots current={3} />

      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-display text-brand-navy">{t("auth.title")}</h1>
        <p className="text-h3 text-ink-muted">{t("auth.subtitle")}</p>
      </header>

      <form
        onSubmit={startPhoneSignIn}
        className="flex flex-col gap-4 rounded-card border border-line bg-surface p-6 shadow-card"
      >
        <label className="flex flex-col gap-2">
          <span className="text-caption text-ink-muted">{t("auth.phone_label")}</span>
          <input
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder={t("auth.phone_placeholder")}
            className="rounded-chip border border-line bg-bg-canvas p-3 text-body text-ink-primary outline-none focus:border-gold"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-chip bg-brand-navy p-3 text-body text-surface disabled:opacity-60"
        >
          {busy ? t("auth.sending") : t("auth.continue")}
        </button>

        <div className="flex items-center gap-3" aria-hidden="true">
          <span className="h-px flex-1 bg-line" />
          <span className="text-caption text-ink-muted">{t("auth.or")}</span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <button
          type="button"
          onClick={googleSignIn}
          disabled={busy}
          className="rounded-chip border border-line bg-bg-canvas p-3 text-body text-ink-primary disabled:opacity-60"
        >
          {t("auth.google")}
        </button>
        {APPLE_SIGNIN_ENABLED ? (
          // §26.1: Apple ships M+2 — the slot exists behind the flag from day 1.
          <button type="button" disabled className="rounded-chip border border-line p-3 text-body">
            Apple
          </button>
        ) : null}

        <ErrorAlert messageKey={errorKey} />
      </form>

      <p className="text-caption text-ink-muted">{t("auth.legal_hint")}</p>
      <div ref={recaptchaHost} />
    </main>
  );
}
