/**
 * The one door to the backend. Every API call in the app goes through here.
 *
 * ── The browser always calls its OWN origin. That is not a shortcut ────────
 *
 * §34.5 exchanges a Firebase ID token exactly once and receives httpOnly
 * session cookies; §6.2 sets `sitara_access` on `Path=/` and `sitara_refresh`
 * on `Path=/auth`. A cookie marked httpOnly is unreachable from JavaScript by
 * design — the BROWSER attaches it, and it attaches it to same-origin requests.
 * So the browser calls its own origin and the server proxies, which is what
 * `next.config.ts`'s rewrites are for and what §6.2 states directly:
 * "Production terminates on one site."
 *
 * This module briefly supported a `NEXT_PUBLIC_API_BASE_URL` so the client
 * could name the API's origin instead. `.env.example` had shipped
 * `http://localhost:8001` as its default, so every developer build picked it
 * up, and the result is exactly what the design predicts: every call became a
 * cross-origin fetch, the browser refused it on CORS preflight, and any call
 * that HAD succeeded would have arrived without the session cookie. The knob is
 * gone rather than defaulted-to-empty, because a value that breaks §34.5
 * whenever it is set is not a configuration option.
 *
 * **The origin is still env-configured and still lives in exactly one place —
 * `API_PROXY_TARGET`, on the server side of the proxy** (`next.config.ts`,
 * read at BUILD time). That is the correct side: it moves the backend without
 * touching the cookie posture the spec chose.
 *
 * ── What this module removes ───────────────────────────────────────────────
 *
 * Before it, `session.ts` wrote `fetch("/auth/session")` and `onboarding.ts`
 * wrote `fetch(`/v1${path}`)` — two modules each knowing a prefix, an origin
 * convention and an error shape. `API_PREFIXES` is now the single list of what
 * gets proxied, and `src/middleware.ts` must exclude every entry in it: a
 * prefix the locale middleware does not exclude is redirected to
 * `/<locale>/<prefix>/…`, which matches no rewrite and no page and 404s. That
 * is exactly how `/v1/onboarding` broke while `/auth/session` worked.
 */

import type { ErrorEnvelope } from "@sitara/schemas";

/**
 * Path prefixes the web app proxies to `sitara-api`.
 *
 * Adding one means adding it to THREE places, and `tests/api-routing.spec.ts`
 * fails until all three agree:
 *   · here
 *   · `next.config.ts`'s rewrites (so the proxy exists)
 *   · `src/middleware.ts`'s matcher (so next-intl leaves it alone)
 */
export const API_PREFIXES = ["auth", "v1"] as const;

/**
 * The URL to call. Root-relative on purpose — see the header.
 *
 * `path` starts with a proxied prefix and NEVER with a locale: API routes are
 * not locale-prefixed, and one that is gets a 307 from the locale middleware to
 * `/<locale>/<path>`, which matches no rewrite and no page and 404s. The locale
 * travels as a field on the request body (`PATCH /v1/onboarding`) or comes from
 * the session; §34.4's `message_key` is resolved client-side from the catalogs.
 */
export function apiUrl(path: string): string {
  if (!path.startsWith("/")) throw new Error(`api path must be absolute: ${path}`);
  const prefix = path.split("/")[1];
  if (!API_PREFIXES.includes(prefix as (typeof API_PREFIXES)[number])) {
    // Catches `apiUrl("/en/v1/onboarding")` and any future prefix that was
    // added to the proxy but not to this list, at the call site rather than as
    // a 404 in a console someone has to notice.
    throw new Error(`"${path}" is not a proxied API path (prefixes: ${API_PREFIXES.join(", ")})`);
  }
  return path;
}

/** The envelope a transport failure becomes, so no caller needs a try/catch. */
const TRANSPORT_FAILURE: ErrorEnvelope = {
  code: "SYS_UNAVAILABLE",
  message_key: "errors.sys.unavailable",
  trace_id: "",
  retryable: true,
};

/** §34.4 — the only two shapes a call can resolve to. */
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ErrorEnvelope };

/**
 * Every API call in the app.
 *
 * A non-2xx or a network failure resolves to a §34.4 envelope rather than
 * throwing, because every screen renders an envelope and none of them should
 * need a try/catch — a screen that forgets one is a screen that swallows the
 * failure, which is the defect this file was written alongside.
 */
export async function apiCall<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      // §34.5: the session cookies are httpOnly and first-party. This is the
      // only credentials mode that both works and keeps them that way.
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const body = response.status === 204 ? null : await response.json().catch(() => null);
    if (response.ok) return { ok: true, data: body as T };
    // A 404 or a proxy error has no envelope in it. Returning the raw body
    // would hand the screen `undefined.message_key`; this keeps the contract.
    if (body && typeof body === "object" && "message_key" in body) {
      return { ok: false, error: body as ErrorEnvelope };
    }
    console.warn(`[api] ${response.status} from ${path} with no §34.4 envelope`);
    return { ok: false, error: { ...TRANSPORT_FAILURE, trace_id: `http-${response.status}` } };
  } catch {
    return { ok: false, error: TRANSPORT_FAILURE };
  }
}

/**
 * §25.4's playback URL for a stored ORIGINAL recording (§33.1).
 *
 * Built here rather than inline in the bubble for the reason this whole module
 * records about `NEXT_PUBLIC_API_BASE_URL`: an origin that must agree with a
 * cookie posture and a deployment topology is a way for the two to disagree
 * silently. `<audio src>` sends the httpOnly session cookie only on a
 * same-origin request, and the endpoint checks ownership against it.
 */
export function voiceNoteAudioUrl(assetId: string): string {
  return apiUrl(`/v1/voice/notes/${encodeURIComponent(assetId)}/audio`);
}
