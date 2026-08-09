#!/usr/bin/env node
/**
 * Vendor the design system's fonts into the repo (§24.2, §2.3).
 *
 * Two reasons, and the second is the one that made it urgent:
 *  1. §2.3 requires per-script subsets, preloaded, font-display swap. Serving
 *     them ourselves is how that gets controlled.
 *  2. The §24.8 screenshot-diff gate is only as stable as its glyph raster.
 *     With no pinned fonts, every baseline was rasterised with whatever the
 *     machine happened to have, which is why maxDiffPixelRatio had to sit at
 *     0.02 — a tolerance wide enough to hide a real regression.
 *
 * Downloads the woff2 files Google Fonts serves for the families §24.2 names,
 * keeping only the subsets the eight launch languages actually need, and emits
 * a self-contained @font-face stylesheet. Run once; the output is committed and
 * CI never fetches anything.
 *
 * Usage: node scripts/vendor-fonts.mjs
 */
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const OUT_DIR = path.resolve("public/fonts");
const CSS_OUT = path.resolve("src/app/fonts.css");

// A Chrome UA makes the API serve woff2 rather than ttf.
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";

/**
 * §24.2: serif (Fraunces) for Tara's ceremonial lines and section headers,
 * Inter for UI; Noto per script (§2.3). Subsets are filtered to what the launch
 * and wave languages need — cyrillic/greek/vietnamese are dropped.
 */
const FAMILIES = [
  { name: "Fraunces", spec: "Fraunces:opsz,wght@9..144,400;9..144,600", subsets: ["latin", "latin-ext"] },
  { name: "Inter", spec: "Inter:wght@400;500;600", subsets: ["latin", "latin-ext"] },
  { name: "Noto Sans Devanagari", spec: "Noto+Sans+Devanagari:wght@400;600", subsets: ["devanagari", "latin"] },
  { name: "Noto Sans Gujarati", spec: "Noto+Sans+Gujarati:wght@400;600", subsets: ["gujarati", "latin"] },
  { name: "Noto Sans Gurmukhi", spec: "Noto+Sans+Gurmukhi:wght@400;600", subsets: ["gurmukhi", "latin"] },
  { name: "Noto Sans Tamil", spec: "Noto+Sans+Tamil:wght@400;600", subsets: ["tamil", "latin"] },
  { name: "Noto Sans Telugu", spec: "Noto+Sans+Telugu:wght@400;600", subsets: ["telugu", "latin"] },
];

/** Each @font-face block, tagged with the `/* subset *\/` comment above it. */
function parseFaces(css) {
  const faces = [];
  const re = /\/\*\s*([\w-]+)\s*\*\/\s*(@font-face\s*\{[^}]*\})/g;
  for (const m of css.matchAll(re)) faces.push({ subset: m[1], block: m[2] });
  return faces;
}

const field = (block, name) => block.match(new RegExp(`${name}:\\s*([^;]+);`))?.[1]?.trim();

mkdirSync(OUT_DIR, { recursive: true });

const out = [
  "/* GENERATED — do not edit. Source: apps/web/scripts/vendor-fonts.mjs.",
  "   Self-hosted so the §24.8 screenshot gate rasterises identically everywhere,",
  "   and so §2.3's per-script subsets are ours to control. */",
  "",
];
let files = 0;
let bytes = 0;

for (const family of FAMILIES) {
  const url = `https://fonts.googleapis.com/css2?family=${family.spec}&display=swap`;
  const css = await fetch(url, { headers: { "User-Agent": UA } }).then((r) => {
    if (!r.ok) throw new Error(`${family.name}: ${r.status} ${r.statusText}`);
    return r.text();
  });

  const kept = parseFaces(css).filter((f) => family.subsets.includes(f.subset));
  if (kept.length === 0) throw new Error(`${family.name}: no faces matched ${family.subsets}`);

  for (const face of kept) {
    const src = field(face.block, "src");
    const remote = src?.match(/url\((https:\/\/[^)]+)\)/)?.[1];
    if (!remote) continue;
    const weight = field(face.block, "font-weight") ?? "400";
    const slug = `${family.name.toLowerCase().replace(/\s+/g, "-")}-${face.subset}-${weight.replace(/\s+/g, "")}`;
    const file = `${slug}.woff2`;

    const buf = Buffer.from(await fetch(remote).then((r) => r.arrayBuffer()));
    writeFileSync(path.join(OUT_DIR, file), buf);
    files += 1;
    bytes += buf.length;

    out.push(
      face.block
        .replace(/src:[^;]+;/, `src: url('/fonts/${file}') format('woff2');`)
        .replace(/font-display:\s*[^;]+;/, "font-display: swap;")
        .replace(/^@font-face\s*\{/, `/* ${family.name} · ${face.subset} */\n@font-face {`),
      "",
    );
  }
  console.log(`${family.name.padEnd(24)} ${kept.length} faces`);
}

writeFileSync(CSS_OUT, out.join("\n"));
console.log(`\n${files} woff2 files, ${(bytes / 1024).toFixed(0)} KB → public/fonts`);
console.log(`stylesheet → ${path.relative(process.cwd(), CSS_OUT)}`);
