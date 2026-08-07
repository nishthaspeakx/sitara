import { defineRouting } from "next-intl/routing";

/** SPEC §2.4 — launch locales en, hi-Latn (Hinglish), hi; locale in URL,
 *  cookie-pinned; a language ships 100% complete or not at all. */
export const routing = defineRouting({
  locales: ["en", "hi-Latn", "hi"],
  defaultLocale: "en",
  localePrefix: "always",
});

export type AppLocale = (typeof routing.locales)[number];
