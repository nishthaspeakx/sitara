#!/usr/bin/env node
/**
 * Token lint (SPEC §24.2 / §29.4 / playbook §1.5). Three gates, all CI-blocking:
 *
 *   1. SOURCE      — no raw hex colours or raw px lengths in app source.
 *   2. TEXT ROLES  — no fill-only token used as a text colour (a utility class is
 *                    theme-agnostic, so a token that fails AA in EITHER theme is
 *                    banned as text everywhere; the paired *-text token exists).
 *   3. CONTRAST    — every declared pair in src/contrast-matrix.json is verified
 *                    numerically against the BUILT css, in both themes, plus the
 *                    §24.2 hue-shift audit for night-derived tokens.
 *
 * Usage: node scripts/token-lint.mjs [--source-only | --contrast-only]
 */
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { contrast, toHsl } from "./contrast.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(here, "..");
const repoRoot = path.resolve(pkgRoot, "../..");

const args = new Set(process.argv.slice(2));
const runSource = !args.has("--contrast-only");
const runContrast = !args.has("--source-only");

const violations = [];
const notes = [];

// ---------------------------------------------------------------- gate 1 + 2
const SCAN_ROOTS = ["apps"].map((p) => path.join(repoRoot, p));
const EXTS = new Set([".ts", ".tsx", ".css", ".scss", ".jsx", ".js"]);
const SKIP_DIRS = new Set(["node_modules", ".next", "dist", ".turbo", "storybook-static"]);

const HEX = /#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g;
const PX = /(?<![\w-])\d+(?:\.\d+)?px\b/g;
// Allowed px: 0px is meaningless to tokenise; 1px hairlines are a CSS-reality
// exemption (border widths), matching the design-system convention.
const PX_ALLOW = new Set(["0px", "1px"]);

const matrix = JSON.parse(readFileSync(path.join(pkgRoot, "src/contrast-matrix.json"), "utf-8"));
const RESTRICTED = matrix.restrictedAsText;
// `text-gold`, `placeholder-caution`, `caret-danger`, … — `decoration-*` is
// deliberately NOT here: an underline is a non-text visual, and a gold underline
// is how an interactive label carries the §0.13 signal without carrying the text.
const TEXT_UTIL = new RegExp(
  `(?<![\\w-])(?:text|placeholder|caret)-(${Object.keys(RESTRICTED)
    .sort((a, b) => b.length - a.length)
    .join("|")})(?![\\w-])`,
  "g",
);

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else if (EXTS.has(path.extname(name))) yield full;
  }
}

if (runSource) {
  for (const root of SCAN_ROOTS) {
    if (!existsSync(root)) continue;
    for (const file of walk(root)) {
      // only lint source dirs
      if (!file.includes(`${path.sep}src${path.sep}`)) continue;
      const rel = path.relative(repoRoot, file);
      const lines = readFileSync(file, "utf-8").split("\n");
      lines.forEach((rawLine, i) => {
        if (rawLine.includes("token-lint-disable-line")) return;
        // A spec citation in a comment ("§24.1 fixes the chip at 56px") is prose,
        // not a hardcoded style. Skip whole-line comments — doc blocks, JSX
        // comments and continuation lines — rather than pushing authors to
        // paraphrase the numbers the spec actually states.
        if (/^\s*(\/\/|\/\*|\*|\{\/\*)/.test(rawLine)) return;
        // …and a TRAILING citation is the same prose in a different column.
        // `speed: 8 + n * 6, // §0.11: 8–14px/s` was being reported as a raw
        // px length; the alternative is an author who stops writing the
        // citation, which costs more than the lint saves. `(?<!:)` keeps
        // `https://` out of it.
        const line = rawLine.replace(/(?<!:)\/\/.*$/, "");
        for (const m of line.matchAll(HEX)) {
          violations.push(`${rel}:${i + 1}  raw hex ${m[0]}`);
        }
        for (const m of line.matchAll(PX)) {
          if (!PX_ALLOW.has(m[0])) violations.push(`${rel}:${i + 1}  raw px ${m[0]}`);
        }
        for (const m of line.matchAll(TEXT_UTIL)) {
          violations.push(
            `${rel}:${i + 1}  ${m[0]} — ${m[1]} is a fill token, not a text token: ${RESTRICTED[m[1]]}`,
          );
        }
      });
    }
  }
}

// -------------------------------------------------------------------- gate 3
if (runContrast) {
  const cssPath = path.join(pkgRoot, "dist/css/tokens.css");
  if (!existsSync(cssPath)) {
    console.error("token-lint FAILED — dist/css/tokens.css missing; run `pnpm --filter @sitara/tokens build` first");
    process.exit(1);
  }
  const css = readFileSync(cssPath, "utf-8");

  /** parse the :root block and the [data-theme="night"] block into var maps */
  function block(startRe) {
    const m = css.match(startRe);
    if (!m) throw new Error(`token-lint: could not find block ${startRe}`);
    const body = css.slice(m.index + m[0].length, css.indexOf("}", m.index));
    const vars = {};
    for (const line of body.split("\n")) {
      const kv = line.match(/^\s*--([\w-]+):\s*(.+);\s*$/);
      if (kv) vars[kv[1]] = kv[2].trim();
    }
    return vars;
  }
  const lightVars = block(/^:root \{/m);
  const nightVars = { ...lightVars, ...block(/^\[data-theme="night"\] \{/m) };
  const themes = { light: lightVars, night: nightVars };

  const min = matrix.minRatio;
  for (const [theme, pairs] of Object.entries(matrix.pairs)) {
    const vars = themes[theme];
    for (const { fg, bg, role } of pairs) {
      const fgHex = vars[`color-${fg}`];
      const bgHex = vars[`color-${bg}`];
      if (!fgHex || !bgHex) {
        violations.push(`contrast[${theme}] unknown token in pair ${fg} on ${bg}`);
        continue;
      }
      const ratio = contrast(fgHex, bgHex);
      const need = min[role];
      if (ratio < need) {
        violations.push(
          `contrast[${theme}] ${fg} (${fgHex}) on ${bg} (${bgHex}) = ${ratio}:1, needs ≥${need}:1 for role "${role}" (SPEC §24.2)`,
        );
      }
    }
  }

  // §24.2 hue-shift audit — every derived value must keep its source's hue.
  for (const { token, from, hueTolerance } of matrix.derived) {
    for (const [theme, source] of Object.entries(from)) {
      const vars = themes[theme];
      const value = vars[`color-${token}`];
      // "@light:x" means this night value was derived from the LIGHT theme's x
      const crossTheme = source.startsWith("@light:");
      const sourceName = crossTheme ? source.slice("@light:".length) : source;
      const sourceValue = (crossTheme ? lightVars : vars)[`color-${sourceName}`];
      if (!value || !sourceValue) {
        violations.push(`derived[${theme}] ${token} — missing token or source ${sourceName}`);
        continue;
      }
      const [th, ts, tl] = toHsl(value);
      const [sh, ss, sl] = toHsl(sourceValue);
      let dh = Math.abs(th - sh);
      if (dh > 180) dh = 360 - dh;
      if (dh > hueTolerance) {
        violations.push(
          `derived[${theme}] ${token} ${value} (h${th.toFixed(0)}) drifted ${dh.toFixed(0)}° from its source ${sourceName} ${sourceValue} (h${sh.toFixed(0)}) — tolerance ${hueTolerance}° (SPEC §24.2 hue-shift rule)`,
        );
      }
      notes.push(
        `derived[${theme}] ${token} ← ${crossTheme ? "light:" : ""}${sourceName}: Δhue ${dh.toFixed(0)}°, ` +
          `Δlightness ${tl - sl >= 0 ? "+" : ""}${((tl - sl) * 100).toFixed(1)}%, ` +
          `Δsaturation ${ts - ss >= 0 ? "+" : ""}${((ts - ss) * 100).toFixed(1)}%`,
      );
    }
  }
}

// -------------------------------------------------------------------- report
// The derivation ledger is long and only interesting when a value is questioned.
if (args.has("--explain")) for (const n of notes) console.log("  " + n);
if (violations.length) {
  console.error("\ntoken-lint FAILED — SPEC §24.2/§29.4:\n");
  for (const v of violations) console.error("  " + v);
  console.error("");
  process.exit(1);
}
const gates = [runSource && "source (hex/px/text-role)", runContrast && "contrast (both themes, AA)"]
  .filter(Boolean)
  .join(" + ");
console.log(`token-lint OK — ${gates}`);
