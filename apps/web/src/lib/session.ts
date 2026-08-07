/**
 * §34.5 session exchange client. Calls go to the same-origin /auth proxy so
 * the httpOnly cookies are first-party; errors are always the §34.4 envelope
 * whose message_key resolves through the i18n catalogs (§2.4).
 */
import type { ErrorEnvelope } from "@sitara/schemas";

export type ExchangeOk = { ok: true; userId: string; isNewUser: boolean };
export type ExchangeErr = { ok: false; error: ErrorEnvelope };
export type ExchangeResult = ExchangeOk | ExchangeErr;

const FALLBACK_ENVELOPE: ErrorEnvelope = {
  code: "SYS_INTERNAL",
  message_key: "errors.sys.internal",
  trace_id: "",
  retryable: true,
};

export async function exchangeSession(
  idToken: string,
  opts: { locale: string; dateOfBirth?: string; deviceName?: string },
): Promise<ExchangeResult> {
  try {
    const res = await fetch("/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        id_token: idToken,
        locale: opts.locale,
        date_of_birth: opts.dateOfBirth ?? null,
        device_name: opts.deviceName ?? null,
      }),
    });
    const body = await res.json();
    if (res.ok) {
      return { ok: true, userId: body.user_id, isNewUser: body.is_new_user };
    }
    return { ok: false, error: body as ErrorEnvelope };
  } catch {
    return { ok: false, error: FALLBACK_ENVELOPE };
  }
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
