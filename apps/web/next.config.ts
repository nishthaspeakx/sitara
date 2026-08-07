import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// §34.5/§6.2 — the API's httpOnly session cookies must be first-party, so
// /auth/* proxies to the backend (same-origin in the browser; the refresh
// cookie's Path=/auth then matches exactly). Production terminates on one site.
const API_BASE_URL = process.env.API_PROXY_TARGET ?? "http://localhost:8001";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/auth/:path*", destination: `${API_BASE_URL}/auth/:path*` }];
  },
};

export default withNextIntl(nextConfig);
