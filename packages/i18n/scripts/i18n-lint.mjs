#!/usr/bin/env node
/**
 * i18n lint (SPEC §2.4 / playbook §1.5): the locale catalogs must carry
 * IDENTICAL key sets — no silent English fallback, ever. Fails CI on any
 * missing or extra key in any locale.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
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

// ---------------------------------------------------------------------------
// Gate 2: every key an app REFERENCES exists. Parity alone only proves the
// catalogs agree with each other — it cannot catch a component asking for a key
// nobody wrote, which surfaces to the user as a raw key or an English fallback.
// ---------------------------------------------------------------------------
const repoRoot = path.resolve(pkg, "../..");
const APP_ROOTS = [path.join(repoRoot, "apps")];
const CODE_EXTS = new Set([".ts", ".tsx"]);
const SKIP_DIRS = new Set(["node_modules", ".next", "dist", ".turbo", "storybook-static"]);

function* walk(dir) {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (CODE_EXTS.has(path.extname(name))) yield full;
  }
}

const dynamic = JSON.parse(readFileSync(path.join(pkg, "src/dynamic-keys.json"), "utf-8"));

/** Expand a declared template into the concrete keys it can produce. */
function expand(template, decl) {
  let values = decl.values;
  if (decl.valuesFrom) {
    const source = JSON.parse(readFileSync(path.join(repoRoot, decl.valuesFrom), "utf-8"));
    values = source.members.map((m) => m.id);
  }
  const placeholder = template.match(/\$\{[^}]+\}/)?.[0];
  if (!placeholder) return [template];
  return values.map((v) => template.replace(placeholder, v));
}

// `"ui.tabs.today"` and `` `ui.tabs.${tab}` ``
//
// The namespace list is the gate's blind spot and has to be maintained: a key
// whose namespace is absent here is simply not scanned, so gate 2 keeps
// reporting OK while the app references a key nobody wrote. M8 added `start`
// and `launch` (the S01–S13 stack); forgetting them would have hidden the
// entire onboarding string set from this check, and the user-visible failure
// mode is a raw dotted key on screen in Hindi.
//
// **It had happened.** S14–S17 shipped `today.*` and `festivals.*` and neither
// namespace was ever added here, so every string on the app's home surface and
// its three sub-routes was outside gate 2 for two milestones — parity kept them
// consistent across locales, and nothing checked that a key a screen asks for
// exists at all. M10 adds those two alongside its own five rather than only its
// own, because a blind spot you have already walked past once is not a blind
// spot any more.
const LITERAL_KEY =
  /"((?:ui|errors|auth|verify|dob|home|app|chat|panchang|numerology|terms|memory|start|launch|brief|today|festivals|journal|vault|family|you|reflection|call|subscription|payresult)\.[a-z0-9_.]+)"/g;
const TEMPLATE_KEY = /`([a-z0-9_.]+\.\$\{[^`]+)`/g;

const referenced = new Set();
const templatesSeen = new Set();
for (const root of APP_ROOTS) {
  for (const file of walk(root)) {
    if (!file.includes(`${path.sep}src${path.sep}`)) continue;
    const text = readFileSync(file, "utf-8");
    for (const m of text.matchAll(LITERAL_KEY)) referenced.add(m[1]);
    for (const m of text.matchAll(TEMPLATE_KEY)) {
      const template = m[1];
      templatesSeen.add(template);
      const decl = dynamic.templates[template];
      if (!decl) {
        console.error(
          `i18n-lint: ${path.relative(repoRoot, file)} builds key \`${template}\` at runtime but it is not declared in packages/i18n/src/dynamic-keys.json — an undeclared dynamic key cannot be verified (SPEC §2.4)`,
        );
        failed = true;
        continue;
      }
      for (const key of expand(template, decl)) referenced.add(key);
    }
  }
}

let missingRefs = 0;
for (const key of [...referenced].sort()) {
  if (!reference.has(key)) {
    console.error(`i18n-lint: app source references "${key}" but no catalog defines it (SPEC §2.4)`);
    failed = true;
    missingRefs += 1;
  }
}

// A declared template nobody uses is stale config, not a failure — but say so.
for (const template of Object.keys(dynamic.templates)) {
  if (!templatesSeen.has(template)) {
    console.log(`i18n-lint: note — declared template \`${template}\` is no longer used in app source`);
  }
}

if (failed) process.exit(1);
console.log(
  `i18n-lint OK — ${keySets.size} locales, ${reference.size} keys each, full parity; ` +
    `${referenced.size} referenced keys all defined (${missingRefs} missing)`,
);
