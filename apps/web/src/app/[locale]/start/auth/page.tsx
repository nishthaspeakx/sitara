"use client";

/**
 * S03 — sign-up (§29.1 `/start/auth`, §24.4, §37.2).
 *
 * "region-ordered auth buttons + phone field", <30s, zero marketing fields.
 *
 * **Phone-first is not a preference.** §37.2 evaluates the §22.4 age gate in a
 * CORROBORATED timezone, and the corroboration comes from the E.164 country of
 * the Firebase-verified phone number (intersected with the request-IP country
 * where a lookup exists). No phone means no corroborated zone, which means no
 * age check, which §37.2 fails closed on — so a Google sign-up cannot complete
 * today. That is a live limitation tracked as `auth.zone_corroboration_coverage`,
 * not an ordering aesthetic, and the phone field is the primary control
 * because it is the path that works.
 *
 * Rebuilt on the §24.3 library in M8. The logic is M1's, unchanged; what
 * changed is that the markup is now `Input`/`Button`/`Card`/`ErrorState`
 * instead of raw elements with hand-written Tailwind — which is what §24.3
 * means by "no screen may ship a one-off component".
 */

import { FirebaseError } from "firebase/app";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { Button, Card, Divider, ErrorState, Input, SectionHeader } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { setPendingPhone } from "@/lib/auth-flow";
import { authClient } from "@/lib/auth-client";
import { APPLE_SIGNIN_ENABLED } from "@/lib/firebase";
import { STEPS } from "@/lib/onboarding";
import { normalizeIndianPhone } from "@/lib/phone";
import { exchangeSession, firebaseErrorKey, isDobRequired } from "@/lib/session";

import { useStepCommit } from "../_step";

/** A client-side failure rendered as the §34.4 envelope every screen speaks. */
function envelope(messageKey: string): ErrorEnvelope {
  return { code: "AUTH_INVALID_TOKEN", message_key: messageKey, trace_id: "", retryable: true };
}

export default function AuthPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { busy: committing } = useStepCommit(STEPS.AUTH);

  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const recaptchaHost = useRef<HTMLDivElement>(null);

  async function startPhoneSignIn(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !recaptchaHost.current) return;
    setBusy(true);
    setError(null);
    try {
      const e164 = normalizeIndianPhone(phone);
      const pending = await authClient.startPhoneSignIn(e164, recaptchaHost.current, locale);
      setPendingPhone(e164, pending);
      router.push("/start/verify");
    } catch (err) {
      // Error CODES carry no PII, so logging one keeps field reports
      // diagnosable; the phone number never appears (§13).
      console.warn("[auth] phone sign-in failed:", err);
      setError(envelope(firebaseErrorKey(err instanceof FirebaseError ? err.code : "")));
      setBusy(false);
    }
  }

  async function googleSignIn() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const idToken = await authClient.signInWithGoogle(locale);
      const result = await exchangeSession(idToken, {
        locale,
        deviceName: navigator.platform || "Web",
      });
      if (result.ok) {
        router.push("/start/consent");
        return;
      }
      if (isDobRequired(result)) {
        router.push("/start/verify"); // continues as the DOB step (§22.4 gate)
        return;
      }
      setError(result.error);
      setBusy(false);
    } catch (err) {
      setError(envelope(firebaseErrorKey(err instanceof FirebaseError ? err.code : "")));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="auth.title" subtitleKey="auth.subtitle" />

      <Card as="section">
        <form onSubmit={startPhoneSignIn} className="flex flex-col gap-4">
          <Input
            kind="phone"
            labelKey="auth.phone_label"
            placeholder={t("auth.phone_placeholder")}
            autoComplete="tel"
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            data-testid="phone-input"
          />
          <Button
            type="submit"
            fullWidth
            loading={busy || committing}
            data-testid="phone-continue"
          >
            {t("auth.continue")}
          </Button>

          <Divider labelKey="auth.or" />

          <Button
            type="button"
            variant="secondary"
            fullWidth
            disabled={busy}
            onClick={() => void googleSignIn()}
            data-testid="google-signin"
          >
            {t("auth.google")}
          </Button>

          {/* §26.1: Apple ships M+2 — the slot exists behind the flag from
              day one so adding it later is a config change, not a layout one. */}
          {APPLE_SIGNIN_ENABLED ? (
            <Button type="button" variant="secondary" fullWidth disabled>
              Apple
            </Button>
          ) : null}
        </form>
      </Card>

      {error ? <ErrorState error={error} onRetry={() => setError(null)} /> : null}

      <p className="text-caption text-ink-muted">{t("auth.legal_hint")}</p>
      <div ref={recaptchaHost} />
    </main>
  );
}
