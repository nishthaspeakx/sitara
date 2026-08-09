import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  /**
   * Everything EXCEPT the proxied API prefixes, Next internals and files.
   *
   * The exclusions are load-bearing, not tidiness. next-intl's middleware
   * exists to put a locale on every route it sees (§28.1: "every route is
   * locale-prefixed"), and it does that with a 307 — so a path it should not
   * have seen comes back as `/<locale>/<path>`, which matches no rewrite and no
   * page and 404s.
   *
   * That is precisely how `/v1/onboarding` broke in the browser while
   * `/auth/session` worked: `auth` was excluded here and `v1` was not, so every
   * onboarding step redirected to `/hi/v1/onboarding` and 404'd. **API routes
   * are never locale-prefixed** — the locale travels in the request body or
   * comes from the session.
   *
   * Next requires this to be a static literal it can analyse at build time, so
   * it cannot be built from `API_PREFIXES`. `tests/api-routing.spec.ts` asserts
   * the two agree instead, and fails on a prefix that is proxied but not
   * excluded here.
   */
  matcher: "/((?!api|auth|v1|_next|_vercel|.*\\..*).*)",
};
