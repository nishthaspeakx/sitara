#!/usr/bin/env node
/**
 * Token lint (SPEC §24.2 / playbook §1.5): components must use design tokens only.
 * Fails CI on raw hex colours or raw px lengths inside app source.
 * Scope: apps/[star]/src — tokens package itself and generated files are exempt.
 */
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const SCAN_ROOTS = ["apps"].map((p) => path.join(repoRoot, p));
const EXTS = new Set([".ts", ".tsx", ".css", ".scss", ".jsx", ".js"]);
const SKIP_DIRS = new Set(["node_modules", ".next", "dist", ".turbo"]);

const HEX = /#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g;
const PX = /(?<![\w-])\d+(?:\.\d+)?px\b/g;
// Allowed px: 0px is meaningless to tokenise; 1px hairlines are a CSS-reality
// exemption (border widths), matching the design-system convention.
const PX_ALLOW = new Set(["0px", "1px"]);

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else if (EXTS.has(path.extname(name))) yield full;
  }
}

const violations = [];
for (const root of SCAN_ROOTS) {
  if (!existsSync(root)) continue;
  for (const file of walk(root)) {
    // only lint source dirs
    if (!file.includes(`${path.sep}src${path.sep}`)) continue;
    const text = readFileSync(file, "utf-8");
    const lines = text.split("\n");
    lines.forEach((line, i) => {
      if (line.includes("token-lint-disable-line")) return;
      for (const m of line.matchAll(HEX)) {
        violations.push(`${path.relative(repoRoot, file)}:${i + 1}  raw hex ${m[0]}`);
      }
      for (const m of line.matchAll(PX)) {
        if (!PX_ALLOW.has(m[0])) {
          violations.push(`${path.relative(repoRoot, file)}:${i + 1}  raw px ${m[0]}`);
        }
      }
    });
  }
}

if (violations.length) {
  console.error("token-lint FAILED — use tokens from @sitara/tokens (SPEC §24.2):\n");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log("token-lint OK — no raw hex/px in app source");
