import { hasLocale, NextIntlClientProvider } from "next-intl";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { DeviceFrame } from "@/components/dev/DeviceFrame";
import { routing } from "@/i18n/routing";
import "@sitara/tokens/css";
import "../globals.css";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

/**
 * Locale → script (§2.3). EN and Hinglish are Latin; HI is Devanagari. The
 * wave-2/3 locales join here with their scripts as they ship: gu → gujarati,
 * pa → gurmukhi, mr → devanagari, ta → tamil, te → telugu.
 */
const LOCALE_SCRIPT: Record<string, string> = {
  en: "latin",
  "hi-Latn": "latin",
  hi: "devanagari",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();

  return (
    // §24.2: [data-script] is what applies the per-script family, size factor,
    // line-height and tracking. Without it the Indic locales fall back to
    // whatever font the device happens to have — which renders, and renders
    // wrong: the tuning exists precisely because untuned Devanagari sets badly.
    <html lang={locale} data-script={LOCALE_SCRIPT[locale]}>
      <body className="bg-bg-canvas text-ink-primary min-h-app font-script">
        <NextIntlClientProvider>
          {/* DEV ONLY, and a no-op everywhere else — see the component. It
              wraps INSIDE the provider so the app's own tree is unchanged and
              every string still resolves the same way. */}
          <DeviceFrame>{children}</DeviceFrame>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
