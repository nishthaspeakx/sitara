#!/usr/bin/env node
/**
 * i18n lint (SPEC §2.4 / playbook §1.5): the locale catalogs must carry
 * IDENTICAL key sets — no silent English fallback, ever. Fails CI on any
 * missing or extra key in any locale.
 */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const pkg = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const messagesDir = path.join(pkg, "messages");
const REQUIRED_LOCALES = ["en", "hi-Latn", "hi"];

function flatten(obj, prefix = "") {
  const keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") keys.push(...flatten(v, full));
    else keys.push(full);
  }
  return keys;
}

const files = readdirSync(messagesDir).filter((f) => f.endsWith(".json"));
const locales = files.map((f) => f.replace(/\.json$/, ""));
const missingLocales = REQUIRED_LOCALES.filter((l) => !locales.includes(l));
if (missingLocales.length) {
  console.error(`i18n-lint FAILED — missing locale catalog(s): ${missingLocales.join(", ")}`);
  process.exit(1);
}

const keySets = new Map(
  files.map((f) => [
    f.replace(/\.json$/, ""),
    new Set(flatten(JSON.parse(readFileSync(path.join(messagesDir, f), "utf-8")))),
  ]),
);

const reference = keySets.get("en");
let failed = false;
for (const [locale, keys] of keySets) {
  if (locale === "en") continue;
  const missing = [...reference].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !reference.has(k));
  for (const k of missing) {
    console.error(`i18n-lint: ${locale} missing key "${k}" (no silent English fallback — SPEC §2.4)`);
    failed = true;
  }
  for (const k of extra) {
    console.error(`i18n-lint: ${locale} has extra key "${k}" not in en`);
    failed = true;
  }
}

if (failed) process.exit(1);
console.log(`i18n-lint OK — ${keySets.size} locales, ${reference.size} keys each, full parity`);
