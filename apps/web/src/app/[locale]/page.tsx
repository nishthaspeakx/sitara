import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

export default function HomePage() {
  const t = useTranslations();

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-display text-brand-navy">{t("app.title")}</h1>
        <p className="text-h3 text-ink-muted">{t("app.tagline")}</p>
      </header>

      <section className="rounded-card bg-surface p-6 shadow-card border border-line flex flex-col gap-3">
        <p className="text-h2 font-serif">{t("home.greeting")}</p>
        <p className="text-body">{t("home.placeholder")}</p>
        <p className="text-caption text-success">{t("home.services", { count: 3 })}</p>
        <p className="text-caption text-ink-muted">{t("home.locale_label")}</p>
      </section>

      <nav className="flex gap-4">
        {routing.locales.map((locale) => (
          <Link
            key={locale}
            href="/"
            locale={locale}
            className="text-caption text-gold underline underline-offset-4"
          >
            {locale}
          </Link>
        ))}
      </nav>
    </main>
  );
}
