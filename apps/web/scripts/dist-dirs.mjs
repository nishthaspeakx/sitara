/**
 * The three Next output directories, in one place.
 *
 * `next build` rewrites manifests in its output directory while a running
 * `next dev` reads and rewrites the same files. Sharing one directory between
 * the two corrupts whichever is running — Next 15 reports "Cannot find the
 * middleware module" or `__webpack_modules__ is not a function`, and deleting
 * the directory does not help, because the dev server rebuilds into it and the
 * next build clobbers it again.
 *
 * So the modes are disjoint by construction. `next.config.ts` picks from here
 * by build PHASE, not by an environment variable, so `next dev` cannot be
 * pointed at a build's directory even by a caller who sets NEXT_DIST_DIR.
 *
 * `tests/dist-dirs.spec.ts` asserts they stay three distinct values and that
 * every one of them is git-ignored — collapsing them back into one is how this
 * regresses, and committing a build output is how the repo bloats.
 */

/** @type {{ dev: string, build: string, test: string }} */
export const DIST_DIRS = {
  /** `next dev`. Never deployed, never built into. */
  dev: ".next-dev",
  /** `next build` — the deployable artefact. */
  build: ".next",
  /**
   * `next build` for the flow suite. Carries `NEXT_PUBLIC_AUTH_ADAPTER=fake`,
   * which is inlined at BUILD time, so it must never be able to become the
   * deployed artefact by accident. A separate directory is what guarantees
   * that; nothing deploys `.next-test`.
   */
  test: ".next-test",
};

/**
 * The directory for a mode. `build` honours NEXT_DIST_DIR so `build:test` and
 * `next start` can select the test output; `dev` never does — that override is
 * exactly the mistake this module exists to make unrepresentable.
 *
 * @param {"dev" | "build"} mode
 * @returns {string}
 */
export function distDirFor(mode) {
  if (mode === "dev") return DIST_DIRS.dev;
  return process.env.NEXT_DIST_DIR ?? DIST_DIRS.build;
}
