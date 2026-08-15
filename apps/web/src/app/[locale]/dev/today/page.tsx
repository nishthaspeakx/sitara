"use client";

/**
 * The §28.2 variant switcher — every state, side by side, from real engine
 * output.
 *
 * Sixteen variants × three densities × three locales × two themes is 288
 * screens, and most of them cannot be arranged by using the app: you cannot
 * make it be Raksha Bandhan, make a provider fail, or be four days into a
 * trial. So this page drives `GET /v1/dev/today`, which fixes the FACTS and the
 * account state and then runs the real ranking engine, the real composer and
 * the real §7.1 degradation ladder over them.
 *
 * It renders the real `<TodayScreen>` — not a preview of it. A switcher with
 * its own rendering path shows states the product never serves, which is the
 * failure mode it exists to prevent.
 *
 * **Dev only, twice over.** The route 404s in a production build, and the
 * endpoint behind it is mounted by `app.py` only when
 * `settings.environment == "dev"`. Either alone would do; both, because a
 * preview tool that can reach production data is not a preview tool.
 *
 * **Not `_dev/`.** Next's App Router treats a `_`-prefixed folder as PRIVATE and
 * excludes it from routing entirely — which is what `_launch/` relies on, and
 * what made the first version of this page a silent 404 in a browser while
 * typechecking, linting and building without a word.
 */

import { notFound, useParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { Density, TodayPayload } from "@sitara/schemas";

import { TodayScreen } from "@/components/today/TodayScreen";
import { apiCall } from "@/lib/api";
import {
  EXTRA_FIXTURES,
  TODAY_VARIANTS,
  resolveChrome,
  type TodayVariant,
} from "@/lib/today-variant";

const DENSITIES: Density[] = ["low", "med", "high"];
const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

export default function DevTodayPage() {
  const [variant, setVariant] = useState<TodayVariant>("normal_morning");
  const [density, setDensity] = useState<Density>("med");
  // The page's OWN locale, from the route. Changing only the API's locale
  // showed Hindi fact lines under English card titles — which is precisely the
  // §2.4 defect this tool exists to make visible, manufactured by the tool.
  const routeLocale = String(useParams()?.locale ?? "en");
  const [theme, setTheme] = useState<(typeof THEMES)[number]>("light");
  const [reduced, setReduced] = useState(false);
  const [payload, setPayload] = useState<TodayPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.setAttribute("data-motion", reduced ? "reduced" : "full");
  }, [theme, reduced]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setError(null);
      const result = await apiCall<TodayPayload>(
        `/v1/dev/today?variant=${variant}&density=${density}&locale=${routeLocale}`,
      );
      if (cancelled) return;
      if (result.ok) setPayload(result.data);
      else {
        setPayload(null);
        setError(result.error.code);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [variant, density, routeLocale]);

  // A real 404, not a blank page: an empty 200 at a known URL in production is
  // an invitation to wonder what used to be there.
  if (process.env.NODE_ENV === "production") notFound();

  // §28.2's offline variant is the SCREEN's own state, not a payload the API
  // can serve: a failed fetch over a cached brief. The switcher reproduces the
  // condition rather than asking the server to pretend.
  const offline = variant === "offline";

  const chrome = payload
    ? resolveChrome({
        state: payload.state,
        localTime: payload.local_time,
        status: payload.status,
        offline,
      })
    : null;

  return (
    <div className="flex min-h-app flex-col">
      {/* Dev chrome. Deliberately plain — this is a tool, and dressing it in
          product components would make it another thing to keep in sync. */}
      <div className="sticky top-0 z-50 flex flex-wrap items-center gap-2 border-b border-border-subtle bg-surface p-3 text-caption">
        <select
          aria-label="variant"
          value={variant}
          onChange={(e) => setVariant(e.target.value as TodayVariant)}
          className="rounded-chip border border-border-subtle bg-bg-canvas px-2 py-1"
        >
          {[...TODAY_VARIANTS, ...EXTRA_FIXTURES].map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>

        {DENSITIES.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDensity(d)}
            className={`rounded-chip border px-2 py-1 ${
              density === d ? "border-gold" : "border-border-subtle"
            }`}
          >
            {d}
          </button>
        ))}

        {LOCALES.map((l) => (
          <a
            key={l}
            href={`/${l}/dev/today`}
            className={`rounded-chip border px-2 py-1 ${
              routeLocale === l ? "border-gold" : "border-border-subtle"
            }`}
          >
            {l}
          </a>
        ))}

        {THEMES.map((th) => (
          <button
            key={th}
            type="button"
            onClick={() => setTheme(th)}
            className={`rounded-chip border px-2 py-1 ${
              theme === th ? "border-gold" : "border-border-subtle"
            }`}
          >
            {th}
          </button>
        ))}

        <button
          type="button"
          onClick={() => setReduced((v) => !v)}
          className={`rounded-chip border px-2 py-1 ${
            reduced ? "border-gold" : "border-border-subtle"
          }`}
        >
          reduced-motion
        </button>

        {chrome ? (
          <span className="text-ink-muted">
            → {chrome.variant} · {chrome.band} · banners [{chrome.banners.join(", ")}]
          </span>
        ) : null}
      </div>

      {error ? (
        <p className="p-5 text-body text-ink-primary">
          {error} — is sitara-api running in dev?
        </p>
      ) : null}

      {payload && chrome ? (
        <TodayScreen payload={payload} chrome={chrome} defaultExpanded />
      ) : null}
    </div>
  );
}
