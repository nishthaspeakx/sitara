import type { Decorator, Preview } from "@storybook/nextjs";
import { NextIntlClientProvider } from "next-intl";
import * as React from "react";

import en from "@sitara/i18n/messages/en.json";
import hi from "@sitara/i18n/messages/hi.json";
import hiLatn from "@sitara/i18n/messages/hi-Latn.json";
import "@sitara/tokens/css";
import "../src/app/fonts.css";
import "../src/app/globals.css";

import { makePseudoLocale } from "./pseudo-locale";

/**
 * The locale matrix every component story renders in.
 *
 * The three launch locales (§2.4) plus the Tamil-length pseudo-locale that
 * stands in for the §24.3 longest-string test. `script` drives the [data-script]
 * attribute, which is what applies the §24.2 per-script size factor,
 * line-height, tracking and Noto family.
 */
export const LOCALES = [
  { id: "en", label: "English", script: "latin", dir: "ltr" },
  { id: "hi", label: "हिन्दी", script: "devanagari", dir: "ltr" },
  { id: "hi-Latn", label: "Hinglish", script: "latin", dir: "ltr" },
  { id: "ta-Pseudo", label: "Tamil-length (pseudo)", script: "tamil", dir: "ltr" },
] as const;

export type LocaleId = (typeof LOCALES)[number]["id"];

const MESSAGES: Record<LocaleId, Record<string, unknown>> = {
  en,
  hi,
  "hi-Latn": hiLatn,
  "ta-Pseudo": makePseudoLocale(en as never) as Record<string, unknown>,
};

const SCRIPT: Record<LocaleId, string> = {
  en: "latin",
  hi: "devanagari",
  "hi-Latn": "latin",
  "ta-Pseudo": "tamil",
};

/**
 * Wraps every story in the locale/theme/script/motion context the design system
 * needs. The attributes are set on the story's own wrapper rather than on
 * <html>, so a single Storybook page can hold several combinations and the
 * screenshot suite can target one deterministically.
 */
const withSitara: Decorator = (Story, context) => {
  const locale = (context.globals.locale ?? "en") as LocaleId;
  const theme = (context.globals.theme ?? "light") as "light" | "night";
  const motion = (context.globals.motion ?? "full") as "full" | "reduced";

  return (
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale] as never} timeZone="Asia/Kolkata">
      <div
        data-theme={theme === "night" ? "night" : undefined}
        data-script={SCRIPT[locale]}
        data-motion={motion === "reduced" ? "reduced" : undefined}
        data-testid="story-root"
        lang={locale === "ta-Pseudo" ? "ta" : locale}
        className="bg-bg-canvas text-ink-primary font-ui p-4"
      >
        <Story />
      </div>
    </NextIntlClientProvider>
  );
};

const preview: Preview = {
  globalTypes: {
    locale: {
      description: "Locale (§2.4 launch three + the Tamil-length pseudo-locale)",
      toolbar: {
        icon: "globe",
        items: LOCALES.map((l) => ({ value: l.id, title: l.label })),
        dynamicTitle: true,
      },
    },
    theme: {
      description: "Theme (§24.2 light/reading · §34.8 night/dusk)",
      toolbar: {
        icon: "circlehollow",
        items: [
          { value: "light", title: "Light / reading" },
          { value: "night", title: "Night / dusk" },
        ],
        dynamicTitle: true,
      },
    },
    motion: {
      description: "Motion (§0.12 — every animation has a reduced-motion equivalent)",
      toolbar: {
        icon: "play",
        items: [
          { value: "full", title: "Full motion" },
          { value: "reduced", title: "Reduced motion" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { locale: "en", theme: "light", motion: "full" },
  decorators: [withSitara],
  parameters: {
    layout: "fullscreen",
    controls: { expanded: true },
    a11y: {
      // §24.2/§29.4 target WCAG 2.2 AA; the token layer is verified numerically
      // by token-lint, and this catches the structural half (names, roles, order).
      config: { rules: [{ id: "color-contrast", enabled: true }] },
    },
    options: {
      storySort: {
        order: ["Foundation", "Sitara", "Structure", "Feedback"],
      },
    },
  },
};

export default preview;
