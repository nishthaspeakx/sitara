import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  TARA_APPROXIMATE_STATES_PENDING,
  TARA_ASSETS,
  TARA_LIKENESS,
  TARA_MOTION_STATUS,
} from "../src/components/ui/tara-assets";
import { PRESENCE_STATES } from "../src/components/ui/_util";

/**
 * CC-008 — Tara's likeness is AI-generated and exclusively owned. She is NOT a
 * real person and NOT a licensed human model.
 *
 * Two rules follow, and both are the kind that decay quietly under review
 * pressure, so they are enforced mechanically instead:
 *
 *   1. The permanent "Tara · AI guide" disclosure stays wherever her name or
 *      face appears.
 *   2. No asset name, alt text, caption or copy may describe her as a real
 *      person, a photograph of someone, a model, or a licensed likeness.
 *
 * The catalogs are checked in every locale, because a claim of realness is just
 * as false in Hindi.
 */

const repoRoot = path.join(__dirname, "..", "..", "..");
const uiDir = path.join(__dirname, "..", "src", "components", "ui");
const messagesDir = path.join(repoRoot, "packages", "i18n", "messages");

/** Phrases that would assert she is a real person or a licensed likeness. */
const FORBIDDEN = [
  /\blicensed (face )?model\b/i,
  /\bface model\b/i,
  /\breal person\b/i,
  /\breal woman\b/i,
  /\bphotograph of\b/i,
  /\bphoto shoot\b/i,
  /\bphotoshoot\b/i,
  /\bactress\b/i,
  /\bshe is real\b/i,
  /\bnot ai\b/i,
  /\bहमारी मॉडल\b/,
  /\bअसली (व्यक्ति|इंसान)\b/,
  /\basli (vyakti|insaan)\b/i,
];

/**
 * The disclaimer itself contains the words the rule bans — "she is NOT a real
 * person, NOT a licensed model" is the correct sentence, not a violation. So
 * negated occurrences are removed before matching; what remains is an assertion.
 */
const NEGATED =
  /\b(?:not|never|no|isn't|is not|aren't)\s+(?:a\s+|an\s+|the\s+)?(?:ai[- ])?(?:licensed\s+)?(?:human\s+)?(?:face\s+)?(?:model|real person|real woman|actress|photograph of[^.,;]*|photoshoot|photo shoot)\b/gi;

function assertsRealness(text: string): RegExp | null {
  const stripped = text.replace(NEGATED, " ");
  return FORBIDDEN.find((p) => p.test(stripped)) ?? null;
}

/** Places a claim of realness would actually reach a user. */
function userFacingStrings(obj: unknown, out: string[] = []): string[] {
  if (typeof obj === "string") out.push(obj);
  else if (obj && typeof obj === "object") {
    for (const v of Object.values(obj as Record<string, unknown>)) userFacingStrings(v, out);
  }
  return out;
}

test("the likeness is declared AI-generated and exclusively owned", () => {
  expect(TARA_LIKENESS.origin).toBe("ai-generated");
  expect(TARA_LIKENESS.ownership).toBe("exclusive");
  expect(TARA_LIKENESS.isRealPerson).toBe(false);
  expect(TARA_LIKENESS.isLicensedModel).toBe(false);
  expect(TARA_LIKENESS.changeControl).toBe("CC-008");
});

test("no catalog string claims she is a real person or a licensed model", () => {
  for (const file of readdirSync(messagesDir).filter((f) => f.endsWith(".json"))) {
    const catalog = JSON.parse(readFileSync(path.join(messagesDir, file), "utf-8"));
    for (const value of userFacingStrings(catalog)) {
      const hit = assertsRealness(value);
      expect(
        hit,
        `${file}: "${value}" matches ${hit} — CC-008 forbids describing Tara as real or licensed`,
      ).toBeNull();
    }
  }
});

test("the AI-guide disclosure key exists in every locale", () => {
  for (const file of readdirSync(messagesDir).filter((f) => f.endsWith(".json"))) {
    const catalog = JSON.parse(readFileSync(path.join(messagesDir, file), "utf-8"));
    const label = catalog?.ui?.tara?.ai_label;
    expect(label, `${file} must define ui.tara.ai_label`).toBeTruthy();
    // the disclosure must actually say AI — a translated label that drops it is
    // a disclosure that does not disclose
    expect(String(label), `${file}: ui.tara.ai_label must name AI`).toMatch(/AI/);
  }
});

/** Comments state the prohibitions, so only live code is checked for breaking them. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

test("TaraPresence renders the disclosure", () => {
  const source = readFileSync(path.join(uiDir, "TaraPresence.tsx"), "utf-8");
  expect(source).toContain("ui.tara.ai_label");
});

test("no component calls her an avatar, or claims she is real (glossary, CC-008)", () => {
  for (const file of readdirSync(uiDir).filter((f) => f.endsWith(".tsx") || f.endsWith(".ts"))) {
    const code = stripComments(readFileSync(path.join(uiDir, file), "utf-8"));
    expect(code.toLowerCase(), `${file} must not call Tara an avatar`).not.toMatch(/\bavatar\b/);
    const hit = assertsRealness(code);
    expect(hit, `${file} matches ${hit} — CC-008`).toBeNull();
  }
});

test("every presence state resolves to a real asset set", () => {
  const publicDir = path.join(__dirname, "..", "public");
  for (const state of PRESENCE_STATES) {
    const asset = TARA_ASSETS[state];
    expect(asset, `no asset for ${state}`).toBeTruthy();
    // the default src must exist on disk, not just typecheck
    const poster = path.join(publicDir, asset.poster);
    expect(statSync(poster).isFile(), `${asset.poster} missing`).toBe(true);
    expect(asset.circleWebp).toContain(".webp");
    expect(asset.circleJpeg).toContain(".jpg");
    expect(asset.portraitWebp).toContain("-full-");
  }
});

/**
 * The two records that say "this is a decision, not an oversight" only work if
 * they stay true. Both of these fail the moment reality moves past them, which
 * is the point: a stale deferral note is indistinguishable from a forgotten one.
 */
test("the cinemagraph deferral matches what is actually in the manifest", () => {
  const withLoops = PRESENCE_STATES.filter(
    (s) => TARA_ASSETS[s].cinemagraphH265 || TARA_ASSETS[s].cinemagraphVp9,
  );
  if (TARA_MOTION_STATUS.deferred) {
    expect(
      withLoops,
      "a state carries a cinemagraph while TARA_MOTION_STATUS still says deferred — flip `deferred` to false",
    ).toEqual([]);
  } else {
    expect(withLoops.length, "deferral is lifted but no state carries a loop").toBeGreaterThan(0);
  }
});

test("the pending-replacement record matches the states still flagged approximate", () => {
  const flagged = PRESENCE_STATES.filter((s) => TARA_ASSETS[s].approximate).sort();
  expect(
    flagged,
    "TARA_APPROXIMATE_STATES_PENDING has drifted from the manifest — when a replacement lands, drop the flag AND the pending entry",
  ).toEqual([...TARA_APPROXIMATE_STATES_PENDING.states].sort());
});

test("the placeholder posters are gone", () => {
  const placeholderDir = path.join(__dirname, "..", "public", "tara", "placeholder");
  let exists = true;
  try {
    statSync(placeholderDir);
  } catch {
    exists = false;
  }
  expect(exists, "public/tara/placeholder must not survive the real asset drop").toBe(false);
});
