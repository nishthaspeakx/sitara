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

/**
 * Whether a string is a local ISO date this module can format.
 *
 * Exported because a ROUTE needs to answer it before it renders: `[date]` is a
 * path segment and a path segment is user input.
 */
export function isLocalDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = parseLocalDate(value);
  if (Number.isNaN(parsed.getTime())) return false;
  // Round-trips: rejects 2026-02-31, which `Date` silently rolls to 3 March.
  const [year, month, day] = value.split("-").map(Number);
  return (
    parsed.getFullYear() === year &&
    parsed.getMonth() === (month ?? 1) - 1 &&
    parsed.getDate() === day
  );
}

/**
 * Every formatter below is TOTAL — an unformattable input comes back
 * unchanged rather than throwing.
 *
 * `Intl.DateTimeFormat.format(new Date(NaN))` throws `RangeError: Invalid time
 * value`, and these run inside render. So `/journal/not-a-date` — a path
 * segment, which is to say user input — took the whole route down with a **500
 * in the browser**, found by hand on 16 Aug 2026. It was reachable by editing
 * the URL, by a stale link, and by anything that ever put a non-date in a date
 * slot.
 *
 * A formatter that throws inside render is a formatter that can only fail as a
 * blank screen, and these are called from the Journal, the vault's consent
 * stamps, the family screens and every subscription date. Making them total is
 * a smaller and more reliable fix than auditing every caller for input it
 * cannot vouch for — and the route ALSO checks (`isLocalDate`), because
 * rendering the slug as a heading would be honest but useless.
 */
function safely(iso: string, format: (date: Date) => string): string {
  const parsed = parseLocalDate(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  try {
    return format(parsed);
  } catch {
    return iso;
  }
}

/** "14 August 2026" — a journal day's heading. */
export function formatLongDate(isoDate: string, locale: string): string {
  return safely(isoDate, (date) =>
    new Intl.DateTimeFormat(intlLocale(locale), {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date),
  );
}

/** "Thu, 14 Aug" — a row in the timeline, where the year is the section. */
export function formatShortDate(isoDate: string, locale: string): string {
  return safely(isoDate, (date) =>
    new Intl.DateTimeFormat(intlLocale(locale), {
      weekday: "short",
      day: "numeric",
      month: "short",
    }).format(date),
  );
}

/** A consent stamp: "2 June 2026". Never a raw ISO string on a screen (§32.4).
 *
 *  Takes a TIMESTAMP rather than a local date, so it parses with `Date` and
 *  gets its own total wrapper — a consent row whose stamp is unreadable must
 *  still render the consent. */
export function formatStamp(isoTimestamp: string, locale: string): string {
  const parsed = new Date(isoTimestamp);
  if (Number.isNaN(parsed.getTime())) return isoTimestamp;
  try {
    return new Intl.DateTimeFormat(intlLocale(locale), {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(parsed);
  } catch {
    return isoTimestamp;
  }
}
