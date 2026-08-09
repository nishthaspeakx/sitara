import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { LIBRARY, LIBRARY_SIZE } from "../src/components/ui";

/**
 * §24.3 as amended by CC-007 — the library is 49 components: 9 foundation +
 * 18 Sitara-specific + 10 structure + 12 feedback. §34.7 fixed it at 48;
 * KundliChart made it 49.
 *
 * "No screen may ship a one-off component without design-system review." These
 * checks are the mechanical half of that rule: a component that appears on disk
 * without entering the manifest, or a manifest entry with no file, no story or
 * no export, fails CI rather than passing quietly.
 */

const uiDir = path.join(__dirname, "..", "src", "components", "ui");
const NON_COMPONENT = new Set(["_util", "_story-utils", "tara-assets", "index"]);

const families = Object.entries(LIBRARY);
const declared = families.flatMap(([, names]) => names as readonly string[]);

test.describe.configure({ mode: "parallel" });

test("the family counts are the §34.7 counts as amended by CC-007", () => {
  const counts = Object.fromEntries(families.map(([f, n]) => [f, (n as readonly string[]).length]));
  expect(counts).toEqual({ foundation: 9, sitara: 18, structure: 10, feedback: 12 });
  expect(declared.length).toBe(LIBRARY_SIZE);
});

test("TrustSheet is the canonical name and WhyThisSheet is retired (§34.7)", () => {
  expect(declared).toContain("TrustSheet");
  expect(declared).not.toContain("WhyThisSheet");
  const files = readdirSync(uiDir);
  expect(files.some((f) => f.startsWith("WhyThisSheet"))).toBe(false);
});

test("every component on disk is declared, and every declaration has a file", () => {
  const onDisk = readdirSync(uiDir)
    .filter((f) => f.endsWith(".tsx") && !f.endsWith(".stories.tsx"))
    .map((f) => f.replace(/\.tsx$/, ""))
    .filter((n) => !NON_COMPONENT.has(n));

  expect([...onDisk].sort()).toEqual([...declared].sort());
});

test("every component has a story file with an AllStates export", () => {
  for (const name of declared) {
    const storyPath = path.join(uiDir, `${name}.stories.tsx`);
    const source = readFileSync(storyPath, "utf-8");
    expect(source, `${name} must export AllStates for the screenshot suite`).toContain(
      "export const AllStates",
    );
  }
});

test("every component is exported from the barrel", () => {
  const barrel = readFileSync(path.join(uiDir, "index.ts"), "utf-8");
  for (const name of declared) {
    // the export list may be wrapped across lines, so match the block, not a prefix
    const exported = new RegExp(String.raw`export\s*\{[^}]*\b${name}\b[^}]*\}\s*from`, "s");
    expect(exported.test(barrel), `${name} must be exported from index.ts`).toBe(true);
  }
});
