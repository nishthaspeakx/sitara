#!/usr/bin/env node
/**
 * Tara asset pipeline (§4, §25.2, CC-008).
 *
 * Takes the delivered masters and produces the responsive, optimised set the
 * app ships: WebP with a JPEG fallback, at the widths TaraPresence actually
 * renders. The masters (~30MB PNGs) are NOT committed — they are escrow
 * material under §22.16, not repo material.
 *
 * The state → master mapping is the load-bearing part and lives in
 * src/components/ui/tara-assets.ts, next to the manifest it produces. It was
 * made by LOOKING at every master, not by matching filenames: §29.5 assigns
 * each state to specific surfaces, and a wrong mapping puts a festive portrait
 * on a safety screen.
 *
 * Usage: node scripts/build-tara-assets.mjs <masters-dir>
 */
import { existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import path from "node:path";

import sharp from "sharp";

const mastersDir = path.resolve(process.argv[2] ?? `${process.env.HOME}/Documents/tara-assets`);
const outDir = path.resolve("public/tara");

/**
 * §4.3 presence state → delivered master.
 *
 * Approximations are recorded rather than hidden: the delivered set has no
 * frame that reads as "concerned but kind", and none that is expressionless
 * enough for the safety surface, so those two borrow the calmest available
 * frames and are flagged for the next asset round.
 */
const STATE_MAP = {
  warm_neutral: "tara-master",
  listening: "tara-chat-listening",
  speaking_soft: "tara-call",
  smile: "tara-chat-smile",
  full_smile: "tara-casual-mug",
  thoughtful: "tara-chat-thinking",
  concerned_kind: "tara-casual-shirt",
  celebration: "tara-full",
  night: "tara-night",
  festival: "tara-story-festive",
  reading: "tara-story-journal",
  safety: "tara-story-window",
};

/**
 * Art direction for the CIRCLE crop, as data.
 *
 * A plain top-anchored square of a 3072×5504 master leaves the face a fifth of
 * the frame — legible at 160px, a smudge in the 56px header chip §24.1 makes
 * persistent. So the circle crop takes a square of `side` × image height
 * starting at `top` × image height, centred horizontally. Tuned per master by
 * looking at each one, because the framing genuinely differs: the tight chat
 * portraits need almost no crop, the standing full-length shot needs a lot.
 *
 * `top` is the fraction of image height where the square starts; `side` is the
 * square's side as a fraction of image height. Both are chosen so the crop
 * never cuts through the face (§29.4) and keeps headroom above it.
 */
const DEFAULT_CROP = { top: 0.05, side: 0.42 };
const CROP = {
  "tara-master": { top: 0.06, side: 0.42 },
  // the three chat masters are already square head-and-shoulders frames —
  // they need the whole frame, not a zoom into it
  "tara-chat-listening": { top: 0, side: 1 },
  "tara-chat-smile": { top: 0, side: 1 },
  "tara-chat-thinking": { top: 0, side: 1 },
  "tara-call": { top: 0.05, side: 0.46 },
  "tara-night": { top: 0.05, side: 0.44 },
  "tara-casual-mug": { top: 0.05, side: 0.42 },
  "tara-casual-shirt": { top: 0.06, side: 0.44 },
  "tara-casual-reading": { top: 0.08, side: 0.42 },
  "tara-full": { top: 0.06, side: 0.3 },
  "tara-story-festive": { top: 0.05, side: 0.34 },
  "tara-story-journal": { top: 0.08, side: 0.36 },
  "tara-story-window": { top: 0.12, side: 0.3 },
  "tara-story-chai": { top: 0.05, side: 0.42 },
};

/** §25.5 Stories (P1) — carried through the pipeline, not bound to a state. */
const STORY_ASSETS = ["tara-casual-reading", "tara-story-chai"];

/**
 * Circle widths cover TaraPresence sm/md/lg (56/96/160pt) at up to 3× DPR.
 * Portrait widths cover the full-bleed call layout on the device matrix.
 */
const CIRCLE_WIDTHS = [168, 288, 480];
const PORTRAIT_WIDTHS = [720, 1080, 1440];

const WEBP = { quality: 82, effort: 5 };
const JPEG = { quality: 82, mozjpeg: true, progressive: true };

async function emit(master, slug) {
  const src = path.join(mastersDir, `${master}.png`);
  if (!existsSync(src)) throw new Error(`master not found: ${src}`);
  const written = [];

  const meta = await sharp(src).metadata();
  const crop = CROP[master] ?? DEFAULT_CROP;
  const side = Math.min(meta.width, Math.round(meta.height * crop.side));
  const region = {
    left: Math.max(0, Math.round((meta.width - side) / 2)),
    top: Math.max(0, Math.min(Math.round(meta.height * crop.top), meta.height - side)),
    width: side,
    height: side,
  };

  for (const width of CIRCLE_WIDTHS) {
    const base = sharp(src).extract(region).resize(width, width);
    await base.clone().webp(WEBP).toFile(path.join(outDir, `${slug}-${width}.webp`));
    await base.clone().jpeg(JPEG).toFile(path.join(outDir, `${slug}-${width}.jpg`));
    written.push(`${slug}-${width}`);
  }

  for (const width of PORTRAIT_WIDTHS) {
    const base = sharp(src).resize({ width, withoutEnlargement: true });
    await base.clone().webp(WEBP).toFile(path.join(outDir, `${slug}-full-${width}.webp`));
    await base.clone().jpeg(JPEG).toFile(path.join(outDir, `${slug}-full-${width}.jpg`));
    written.push(`${slug}-full-${width}`);
  }
  return written;
}

if (!existsSync(mastersDir)) {
  console.error(`masters directory not found: ${mastersDir}`);
  process.exit(1);
}

// the placeholder posters are replaced wholesale, not layered over
const placeholderDir = path.join(outDir, "placeholder");
if (existsSync(placeholderDir)) rmSync(placeholderDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

let count = 0;
for (const [state, master] of Object.entries(STATE_MAP)) {
  const written = await emit(master, state);
  count += written.length * 2;
  console.log(`${state.padEnd(16)} ← ${master}`);
}
for (const master of STORY_ASSETS) {
  const slug = `story-${master.replace(/^tara-(story-)?/, "")}`;
  const written = await emit(master, slug);
  count += written.length * 2;
  console.log(`${slug.padEnd(16)} ← ${master}  (§25.5 P1)`);
}

const total = readdirSync(outDir)
  .filter((f) => f.endsWith(".webp") || f.endsWith(".jpg"))
  .reduce((sum, f) => sum + statSync(path.join(outDir, f)).size, 0);
console.log(`\n${count} files, ${(total / 1024 / 1024).toFixed(1)} MB total in public/tara`);
