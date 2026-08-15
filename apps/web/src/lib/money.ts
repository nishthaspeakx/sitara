/**
 * Money as the user reads it (§2.3, §30.3, CC-013).
 *
 * `dates.ts` is this file's sibling and the reasoning is the same shape — the
 * server sends a value, the client renders it in the locale, and the trap is
 * that `Intl` has an opinion nobody asked for. Three rules, and two of them
 * are places `Intl` gets it wrong on its own.
 *
 * ── 1. The GROUPING follows the CURRENCY, not the locale ───────────────────
 *
 * §2.3: "Indian digit grouping (₹1,45,000) for INR and Western grouping for
 * USD/GBP/etc., currency by billing region."
 *
 * `Intl.NumberFormat` groups by LOCALE. So `new Intl.NumberFormat("en-IN")`
 * renders a USD amount as `$14,50,000.00` — Indian grouping on a dollar price,
 * which is exactly what §2.3's sentence forbids and exactly what the obvious
 * implementation produces. And §30.3 makes the mismatch ordinary rather than
 * exotic: a subscriber who moves abroad keeps billing in ₹ until renewal, and
 * an NRI gift is bought in USD and redeemed in India, so a `hi` reader looking
 * at a USD price is a case the product ships with.
 *
 * So the formatting locale is chosen by the CURRENCY (`en-IN` for INR, `en-US`
 * for USD) and the user's locale chooses nothing here. That is safe precisely
 * because CC-013 already fixed digits as Latin everywhere — there is no
 * script to lose by formatting a number through `en-*`, and the currency
 * symbols (₹, $) are the same glyphs in every launch locale.
 *
 * ── 2. The digits are LATIN in every locale, by ruling (§46, CC-013) ────────
 *
 * Same ruling `dates.ts` records, and the same thing to preserve: the ABSENCE
 * of a `-u-nu-deva` extension. A well-meant `hi-IN-u-nu-deva` here would
 * render ₹३,९९९ — the reading §46 rejected — and §46's scope names prices
 * explicitly.
 *
 * ── 3. Minor units in, string out. No floats, ever ─────────────────────────
 *
 * The server sends `{minor: 49900, currency: "INR"}` (`payments/money.py`'s
 * `as_wire`). Dividing by 100 at the boundary is unavoidable to hand `Intl` a
 * number, and it is safe HERE and nowhere else: it happens once, on the way to
 * a string, and no arithmetic follows it. Every sum, difference and comparison
 * has already happened on the server in integers.
 */

import { CURRENCIES, type Currency } from "@sitara/schemas";

/** The shape `payments/money.py`'s `as_wire()` sends. */
export interface WireMoney {
  minor: number;
  currency: string;
}

/**
 * Currency → the locale whose grouping convention §2.3 assigns it.
 *
 * Declared data, not derived, for the reason every map in this codebase is
 * declared data: an unmapped currency is a DECISION, not a fallback. A new
 * currency arriving without a row here throws at the call site rather than
 * silently borrowing Indian grouping for a European price.
 */
const GROUPING_LOCALE: Record<string, string> = {
  // 1,45,000 — the lakh/crore grouping §2.3 names.
  INR: "en-IN",
  // 145,000 — Western grouping, for every currency §2.3 puts in "etc.".
  USD: "en-US",
};

/** The minor-unit divisor. Declared for the reason `MINOR_UNITS` is in
 *  `payments/money.py`: it is not 100 for every currency in the world, and a
 *  hardcoded 100 is a hundredfold error the first time that matters. */
const MINOR_UNITS: Record<string, number> = {
  INR: 100,
  USD: 100,
};

export class UnknownCurrency extends Error {}

function requireCurrency(code: string): string {
  if (!(code in GROUPING_LOCALE) || !(code in MINOR_UNITS)) {
    throw new UnknownCurrency(
      `no §2.3 grouping declared for ${code}. Add a row rather than defaulting — ` +
        `Indian grouping on a European price is wrong in a way nothing would flag.`,
    );
  }
  return code;
}

/**
 * "₹499" / "$12.99" — a headline price.
 *
 * Whole amounts drop their decimals (₹499, not ₹499.00) and fractional ones
 * keep them ($12.99). §29.2 puts the price at display size on S31, and two
 * trailing zeros there are noise a reader has to look past.
 */
export function formatMoney(money: WireMoney): string {
  const code = requireCurrency(money.currency);
  const value = money.minor / MINOR_UNITS[code]!;
  const whole = money.minor % MINOR_UNITS[code]! === 0;
  return new Intl.NumberFormat(GROUPING_LOCALE[code]!, {
    style: "currency",
    currency: code,
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  }).format(value);
}

/**
 * The plain saving between two prices, for §29.2's "savings stated plainly".
 *
 * Returns null rather than zero when there is nothing to say — a "save ₹0"
 * chip is the shape of a dark pattern even when the number is honest, and
 * `PriceCard` takes `savingsLabel` as optional for exactly that reason.
 *
 * **Refuses to compare across currencies**, which is `Money._same` on the
 * server expressed on the client: §30.3 forbids conversion, so a saving
 * between ₹3,999 and $12.99 is not a number that exists.
 */
export function annualSaving(monthly: WireMoney, annual: WireMoney): WireMoney | null {
  if (monthly.currency !== annual.currency) {
    throw new UnknownCurrency(
      `cannot compare ${monthly.currency} with ${annual.currency} — §30.3 forbids the ` +
        `conversion that would make this a number, and there is no rate to reach for.`,
    );
  }
  const twelveMonths = monthly.minor * 12;
  const saved = twelveMonths - annual.minor;
  if (saved <= 0) return null;
  return { minor: saved, currency: annual.currency };
}

/**
 * Whether a currency code is one the schemas declare.
 *
 * Used at the API boundary: a server that somehow sent a currency this build
 * has never heard of should surface as an honest failure rather than as
 * `NaN` inside a price card.
 */
export function isKnownCurrency(code: string): code is Currency {
  return (CURRENCIES as readonly string[]).includes(code);
}
