import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { API_PREFIXES, apiUrl } from "../src/lib/api";

/**
 * An API path has to survive three separate mechanisms to reach the backend,
 * and each one fails differently and silently.
 *
 * The live bug: `/v1` was proxied by `next.config.ts` but NOT excluded from
 * next-intl's middleware matcher. The middleware exists to put a locale on
 * every route it sees, so it 307'd `/v1/onboarding` to `/hi/v1/onboarding` —
 * which matches no rewrite and no page, and 404s. `/auth` was excluded and
 * worked, so the two prefixes behaved differently for a reason nothing in the
 * code connected. Every onboarding step 404'd in a real browser.
 *
 * These are the three places that must agree, asserted against each other
 * rather than trusted to stay in sync.
 */

const webRoot = path.join(__dirname, "..");
const read = (file: string) => readFileSync(path.join(webRoot, file), "utf-8");

test.describe.configure({ mode: "parallel" });

test("every proxied prefix is excluded from the locale middleware", () => {
  const middleware = read("src/middleware.ts");
  const matcher = /matcher:\s*"([^"]+)"/.exec(middleware)?.[1];
  expect(matcher, "middleware must declare a matcher").toBeTruthy();

  for (const prefix of API_PREFIXES) {
    // The matcher's negative lookahead is what keeps next-intl off API paths.
    expect(
      matcher,
      `"${prefix}" is proxied but not excluded — the middleware will 307 it to /<locale>/${prefix}/… and it will 404`,
    ).toContain(`${prefix}|`);
  }
});

test("every proxied prefix has a rewrite to the backend", () => {
  const config = read("next.config.ts");
  for (const prefix of API_PREFIXES) {
    expect(config, `"${prefix}" is declared proxied but has no rewrite`).toContain(
      `source: "/${prefix}/:path*"`,
    );
  }
});

test("the middleware excludes nothing it does not need to", () => {
  // Next internals and dotted files are the framework's own; anything else in
  // the exclusion list should be a declared API prefix, or it is a route the
  // app silently serves without a locale (§28.1: every route is locale-prefixed).
  const matcher = /matcher:\s*"([^"]+)"/.exec(read("src/middleware.ts"))![1]!;
  const excluded = /\(\?!([^)]+)\)/.exec(matcher)![1]!.split("|");
  // `.*\..*` (anything with a dot) is the static-file escape; it is read out
  // of the source with its backslashes still escaped, so it is matched by
  // shape rather than by an equally-escaped literal.
  const isFramework = (e: string) =>
    ["api", "_next", "_vercel"].includes(e) || e.includes("\\");
  const unexplained = excluded.filter(
    (e) => !isFramework(e) && !API_PREFIXES.includes(e as (typeof API_PREFIXES)[number]),
  );
  expect(unexplained, "excluded from locale routing for no declared reason").toEqual([]);
});

test("apiUrl refuses a locale-prefixed path", () => {
  // The shape of the live defect, caught at the call site.
  expect(() => apiUrl("/hi/v1/onboarding")).toThrow(/not a proxied API path/);
  expect(() => apiUrl("/en/auth/session")).toThrow(/not a proxied API path/);
  expect(() => apiUrl("v1/onboarding")).toThrow(/must be absolute/);
});

test("apiUrl returns a root-relative path, never an origin", () => {
  // §34.5: the session cookies are httpOnly and first-party, so the browser has
  // to call its own origin. An absolute URL here fails CORS preflight and, if it
  // ever got through, would arrive without the cookie.
  for (const path of ["/v1/onboarding", "/auth/session"]) {
    const url = apiUrl(path);
    expect(url).toBe(path);
    expect(url).not.toMatch(/^https?:\/\//);
  }
});

test("no module builds an API path by hand", () => {
  // One door. Two modules each keeping their own prefix is how one of them
  // ended up on a prefix the middleware rewrites and the other did not.
  for (const file of ["src/lib/onboarding.ts", "src/lib/session.ts"]) {
    const source = read(file);
    expect(source, `${file} must call the API through lib/api.ts`).not.toMatch(
      /fetch\(\s*[`"']\//,
    );
  }
});
