/**
 * Firebase only accepts E.164 phone numbers, but India-first users (§2.1)
 * type local formats: bare 10 digits, a leading trunk 0, or spaced groups.
 * Normalise to E.164 with +91 as the default country code instead of
 * bouncing the sign-up with an error.
 */
export function normalizeIndianPhone(raw: string): string {
  const cleaned = raw.replace(/[\s().-]/g, "");
  if (cleaned.startsWith("+")) return cleaned;
  const digits = cleaned.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("0")) return `+91${digits.slice(1)}`;
  if (digits.length === 10) return `+91${digits}`;
  if (digits.length === 12 && digits.startsWith("91")) return `+${digits}`;
  return `+${digits}`;
}
