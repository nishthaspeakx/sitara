import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing, type AppLocale } from "./routing";

// Catalogs live in @sitara/i18n — the single home for all strings (§2.4).
// Explicit imports: the locale set is closed (a language ships 100% or not at all).
const catalogs: Record<AppLocale, () => Promise<{ default: Record<string, unknown> }>> = {
  en: () => import("@sitara/i18n/messages/en.json"),
  "hi-Latn": () => import("@sitara/i18n/messages/hi-Latn.json"),
  hi: () => import("@sitara/i18n/messages/hi.json"),
};

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;

  return {
    locale,
    messages: (await catalogs[locale]()).default as never,
  };
});
