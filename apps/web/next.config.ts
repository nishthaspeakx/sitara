import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import createNextIntlPlugin from "next-intl/plugin";

import { distDirFor } from "./scripts/dist-dirs.mjs";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// §34.5/§6.2 — the API's httpOnly session cookies must be first-party, so
// /auth/* and /v1/* proxy to the backend (same-origin in the browser; the
// refresh cookie's Path=/auth then matches exactly). Production terminates on
// one site.
//
// **This is read at BUILD time, not at runtime.** Next evaluates `rewrites()`
// during `next build` and serialises the result into `routes-manifest.json`, so
// setting API_PROXY_TARGET on `next start` has no effect whatsoever — the
// destination is already baked in. That is a silent failure: the server starts,
// the routes work, and they point somewhere else entirely. It cost a debugging
// session when the flow suite's stub API turned out never to be receiving
// anything, and every deployment must therefore set this at build time.
const API_BASE_URL = process.env.API_PROXY_TARGET ?? "http://localhost:8001";

/**
 * Three modes, three output directories, chosen by PHASE rather than by an env
 * var a script has to remember to set.
 *
 * `next build` writes manifests into its output directory while a running
 * `next dev` is reading and rewriting the same files. When those are the same
 * directory the dev server is corrupted mid-flight — Next 15 surfaces it as
 * "Cannot find the middleware module" or `__webpack_modules__ is not a
 * function`, both of which name a symptom and not the cause, and neither of
 * which is fixed by deleting the directory: the dev server immediately rebuilds
 * into it and the next build clobbers it again.
 *
 * It was previously a documented gotcha and discipline. M8 made it fire far
 * more often — `design-qa` runs TWO Next builds, and it is now the routine
 * command — so it stops being discipline and becomes structure. `next dev`
 * cannot be pointed at a build's directory here, because the phase decides and
 * the phase is not something a caller passes in.
 *
 *   dev        .next-dev    never deployed, never built into
 *   build      .next        the deployable artefact
 *   build:test .next-test   carries NEXT_PUBLIC_AUTH_ADAPTER=fake; never deployed
 *
 * `next start` (the flow suite's server) is a production phase and still reads
 * NEXT_DIST_DIR, which is how Playwright points it at `.next-test`.
 */
export default function config(phase: string): NextConfig {
  const nextConfig: NextConfig = {
    distDir: distDirFor(phase === PHASE_DEVELOPMENT_SERVER ? "dev" : "build"),
    reactStrictMode: true,
    async rewrites() {
      return [
        { source: "/auth/:path*", destination: `${API_BASE_URL}/auth/:path*` },
        // §34.5's access cookie is httpOnly with Path=/, so every product API
        // the browser calls must be same-origin too — a cross-origin fetch
        // would simply not carry it, and the fix for that is never to move the
        // token somewhere JavaScript can read.
        { source: "/v1/:path*", destination: `${API_BASE_URL}/v1/:path*` },
      ];
    },
  };
  return withNextIntl(nextConfig);
}
