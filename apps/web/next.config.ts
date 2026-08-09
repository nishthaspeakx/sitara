import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// §34.5/§6.2 — the API's httpOnly session cookies must be first-party, so
// /auth/* proxies to the backend (same-origin in the browser; the refresh
// cookie's Path=/auth then matches exactly). Production terminates on one site.
const API_BASE_URL = process.env.API_PROXY_TARGET ?? "http://localhost:8001";

// The flow suite needs a build carrying `NEXT_PUBLIC_AUTH_ADAPTER=fake`, and
// NEXT_PUBLIC_* is inlined at BUILD time — so that build must not be able to
// become the deployed one by accident. It gets its own output directory
// instead; nothing deploys `.next-test`.
const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/auth/:path*", destination: `${API_BASE_URL}/auth/:path*` },
      // §34.5's access cookie is httpOnly with Path=/, so every product API the
      // browser calls must be same-origin too — a cross-origin fetch would
      // simply not carry it, and the fix for that is never to move the token
      // somewhere JavaScript can read.
      { source: "/v1/:path*", destination: `${API_BASE_URL}/v1/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
