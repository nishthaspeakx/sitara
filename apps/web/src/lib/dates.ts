/**
 * Dates as the user reads them.
 *
 * §2.4 makes the whole app native-language "incl. numerals", and a journal is
 * mostly dates — so `Intl.DateTimeFormat` with the active locale is not a
 * nicety here, it is most of the screen. `toLocaleDateString()` with no locale
 * would render the SERVER's or the browser's, which for a Hindi user in Chrome
 * set to English is English inside a Devanagari page.
 *
 * ── The digits are LATIN in every locale, by ruling (§46, CC-013) ──────────
 *
 * Devanagari has its own digit set, so §29.2's "100% locale incl. numerals"
 * admitted two readings. §46 fixes it: Latin, including in `hi`. Modern Hindi
 * readers expect Latin digits for dates and times, and Devanagari numerals read
 * as ceremonial — they belong to a wedding invitation, not to an app's calendar
 * — so rendering the clock in them makes the product feel archaic rather than
 * authentic. Tithi and nakshatra VALUES are unaffected; those are terms, not
 * quantities.
 *
 * There is nothing to do to get this: `Intl` renders Latin digits for `hi-IN`
 * unless asked for `-u-nu-deva`. **So the thing to preserve is the ABSENCE of
 * that extension** — a well-meant `hi-IN-u-nu-deva` here would silently
 * implement the reading §46 rejected.
 *
 * ── `hi-Latn` is Hinglish, and Intl has never heard of it ──────────────────
 *
 * `Intl` resolves `hi-Latn` to Hindi and formats in Devanagari — which is
 * exactly the failure `voice/providers/base.py` records for the locale map:
 * `locale.split("-")[0]` sends Hinglish to `hi` and fills every Hinglish
 * surface with a script its readers did not choose, while every other metric
 * stays green. Hinglish is Latin script, so it formats through `en-IN`: Indian
 * date order, Latin numerals, which is what a Hinglish reader expects.
 *
 * The mapping is declared data for the same reason the provider one is — an
 * unmapped locale is a decision, not a fallback.
 */

const INTL_LOCALE: Record<string, string> = {
  en: "en-IN",
  hi: "hi-IN",
  // NOT "hi". See the header.
  "hi-Latn": "en-IN",
};

function intlLocale(locale: string): string {
  return INTL_LOCALE[locale] ?? "en-IN";
}

/** An ISO local date (`2026-08-14`) as a date, with no timezone shift.
 *
 *  `new Date("2026-08-14")` parses as UTC midnight, so west of Greenwich it
 *  formats as the 13th — a journal day off by one for every user in the
 *  Americas, and correct on every machine CI has ever run on. */
function parseLocalDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}

/** "14 August 2026" — a journal day's heading. */
export function formatLongDate(isoDate: string, locale: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parseLocalDate(isoDate));
}

/** "Thu, 14 Aug" — a row in the timeline, where the year is the section. */
export function formatShortDate(isoDate: string, locale: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(parseLocalDate(isoDate));
}

/** A consent stamp: "2 June 2026". Never a raw ISO string on a screen (§32.4). */
export function formatStamp(isoTimestamp: string, locale: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(isoTimestamp));
}
