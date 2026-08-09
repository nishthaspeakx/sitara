/**
 * §34.5 session exchange client. Calls go to the same-origin /auth proxy so
 * the httpOnly cookies are first-party; errors are always the §34.4 envelope
 * whose message_key resolves through the i18n catalogs (§2.4).
 */
import type { ErrorEnvelope } from "@sitara/schemas";

import { apiCall } from "./api";

export type ExchangeOk = { ok: true; userId: string; isNewUser: boolean };
export type ExchangeErr = { ok: false; error: ErrorEnvelope };
export type ExchangeResult = ExchangeOk | ExchangeErr;

export async function exchangeSession(
  idToken: string,
  opts: { locale: string; dateOfBirth?: string; deviceName?: string },
): Promise<ExchangeResult> {
  // The locale rides in the BODY. API routes are never locale-prefixed — a
  // prefixed one is redirected by the locale middleware and 404s.
  const result = await apiCall<{ user_id: string; is_new_user: boolean }>("/auth/session", {
    method: "POST",
    body: JSON.stringify({
      id_token: idToken,
      locale: opts.locale,
      date_of_birth: opts.dateOfBirth ?? null,
      device_name: opts.deviceName ?? null,
    }),
  });
  if (result.ok) {
    return { ok: true, userId: result.data.user_id, isNewUser: result.data.is_new_user };
  }
  return { ok: false, error: result.error };
}

export function isDobRequired(result: ExchangeResult): boolean {
  return !result.ok && result.error.message_key === "errors.auth.dob_required";
}

/** Firebase client errors rendered through the same catalog keys (§2.4). */
export function firebaseErrorKey(code: string): string {
  switch (code) {
    case "auth/invalid-phone-number":
    case "auth/missing-phone-number":
      return "errors.auth.invalid_phone";
    case "auth/too-many-requests":
      return "errors.auth.otp_throttled";
    case "auth/invalid-verification-code":
    case "auth/code-expired":
      return "errors.auth.invalid_token";
    default:
      // Error codes carry no PII; logging them keeps field reports diagnosable.
      console.warn("[auth] unmapped firebase error:", code);
      return "errors.sys.internal";
  }
}
