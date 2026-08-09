import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { DIST_DIRS, distDirFor } from "../scripts/dist-dirs.mjs";

/**
 * The three Next output directories must stay three.
 *
 * `next build` rewrites manifests in its output directory while a running
 * `next dev` reads and rewrites the same files. Point both at one directory and
 * whichever is running is corrupted mid-flight: Next 15 reports "Cannot find
 * the middleware module" or `__webpack_modules__ is not a function`, both of
 * which name a symptom rather than the cause. Deleting the directory does not
 * fix it — the dev server rebuilds into it and the next build clobbers it
 * again, which is what makes the failure feel unkillable.
 *
 * This was a documented gotcha and a matter of discipline until M8, when
 * `design-qa` started running TWO Next builds and became the routine command.
 * Discipline that has to hold every time somebody runs a build is not a
 * control. These are the ways it comes back, and each has an assertion:
 *
 *   · the directories get collapsed back into one ("why do we need .next-dev?")
 *   · `next dev` becomes overridable again, so a stray NEXT_DIST_DIR in a shell
 *     puts dev back on a build's directory
 *   · the config goes back to selecting on an env var rather than on the phase
 *   · a new directory ships uncommitted to .gitignore and a build output lands
 *     in the repository
 */

const webRoot = path.join(__dirname, "..");
const repoRoot = path.join(webRoot, "..", "..");

test.describe.configure({ mode: "parallel" });

test("dev, build and test outputs are three distinct directories", () => {
  const values = Object.values(DIST_DIRS);
  expect(values).toHaveLength(3);
  expect(new Set(values).size, "collapsing any two is the whole defect").toBe(3);
});

test("the dev directory cannot be overridden by NEXT_DIST_DIR", () => {
  const before = process.env.NEXT_DIST_DIR;
  try {
    // A build's directory, exported in a shell — exactly how a developer would
    // reproduce the corruption without meaning to.
    process.env.NEXT_DIST_DIR = DIST_DIRS.build;
    expect(distDirFor("dev")).toBe(DIST_DIRS.dev);
    // …while a BUILD still honours it, which is how `build:test` and the flow
    // suite's `next start` select the test output.
    expect(distDirFor("build")).toBe(DIST_DIRS.build);
    process.env.NEXT_DIST_DIR = DIST_DIRS.test;
    expect(distDirFor("build")).toBe(DIST_DIRS.test);
    expect(distDirFor("dev")).toBe(DIST_DIRS.dev);
  } finally {
    if (before === undefined) delete process.env.NEXT_DIST_DIR;
    else process.env.NEXT_DIST_DIR = before;
  }
});

test("next.config.ts selects the directory by PHASE, not by an env var", () => {
  const source = readFileSync(path.join(webRoot, "next.config.ts"), "utf-8");
  // The phase is not something a caller can pass in, which is what makes the
  // separation structural rather than a convention.
  expect(source).toContain("PHASE_DEVELOPMENT_SERVER");
  expect(source).toContain("distDirFor");
  // A bare `distDir: process.env.NEXT_DIST_DIR ?? ...` is the shape this
  // replaced: it applies to dev too, and that is the regression.
  expect(source).not.toMatch(/distDir:\s*process\.env/);
});

test("every output directory is git-ignored", () => {
  for (const dir of Object.values(DIST_DIRS)) {
    // `check-ignore` answers from the real ignore rules rather than from a
    // string match on .gitignore, so a rule that exists but does not apply
    // still fails here.
    const ignored = execFileSync(
      "git",
      ["check-ignore", "-q", "--no-index", path.join("apps", "web", dir, "x")],
      { cwd: repoRoot, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] },
      // execFileSync throws on a non-zero exit, which is what "not ignored"
      // returns — so reaching this line at all is the pass.
    );
    expect(ignored).toBeDefined();
  }
});

test("the package scripts use the directories they are supposed to", () => {
  const pkg = JSON.parse(readFileSync(path.join(webRoot, "package.json"), "utf-8")) as {
    scripts: Record<string, string>;
  };
  // `build:test` is the only script that may name a directory, and it must name
  // the test one. `dev` and `build` take theirs from the phase.
  expect(pkg.scripts["build:test"]).toContain(`NEXT_DIST_DIR=${DIST_DIRS.test}`);
  expect(pkg.scripts.dev).not.toContain("NEXT_DIST_DIR");
  expect(pkg.scripts.build).not.toContain("NEXT_DIST_DIR");
});
