import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * Every internal navigation target resolves to a route that exists.
 *
 * This exists because `/you/help` did not, and was the PRIMARY button on the
 * L3+ safety takeover — the crisis screen — in all three locales, reached from
 * both `ask/page.tsx` and `support/now/page.tsx`. It was found by accident,
 * while looking at something else.
 *
 * A 404 is the worst class of bug this product can have on that screen, and
 * nothing was watching for it: a typecheck cannot know that a string is a
 * route, and no screenshot fails because a button's HANDLER is wrong. So this
 * reads the App Router tree, reads every `router.push`/`href` literal in the
 * source, and asserts the second set is contained in the first.
 *
 * It is a static test on purpose — no server, no browser. A dead link should
 * fail in the cheapest suite there is, not in a smoke test somebody runs
 * before a demo.
 */

const SRC = path.join(process.cwd(), "src");
const APP = path.join(SRC, "app", "[locale]");

/** Every routable path under `app/[locale]`, as a matchable pattern. */
function routes(dir: string, prefix = ""): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (!statSync(full).isDirectory()) {
      if (entry === "page.tsx") found.push(prefix || "/");
      continue;
    }
    // `_`-prefixed folders are private to the router and are not routes;
    // `(group)` folders do not appear in the URL.
    if (entry.startsWith("_")) continue;
    const segment = entry.startsWith("(") ? "" : `/${entry}`;
    found.push(...routes(full, prefix + segment));
  }
  return found;
}

/** `/journal/[date]` → matches `/journal/anything`. */
function toMatcher(route: string): RegExp {
  const pattern = route
    .split("/")
    .map((s) => (s.startsWith("[") ? "[^/]+" : s.replace(/[.*+?^${}()|\\]/g, "\\$&")))
    .join("/");
  return new RegExp(`^${pattern}$`);
}

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(entry) && !entry.includes(".stories.")) out.push(full);
  }
  return out;
}

/**
 * Internal targets, from the two ways this app navigates.
 *
 * Template literals with an interpolation (`` `/${tab}` ``) are skipped: the
 * value is not knowable statically, and the tab set has its own coverage.
 */
function navigationTargets(): { file: string; target: string }[] {
  const found: { file: string; target: string }[] = [];
  const patterns = [
    /router\.(?:push|replace)\(\s*["'`](\/[^"'`$]*)["'`]\s*\)/g,
    /href=\{?\s*["'`](\/[^"'`$]*)["'`]/g,
  ];
  for (const file of sourceFiles(SRC)) {
    const text = readFileSync(file, "utf-8");
    for (const re of patterns) {
      for (const m of text.matchAll(re)) {
        const target = m[1]!.split("?")[0]!.split("#")[0]!;
        if (target.startsWith("//")) continue; // protocol-relative, external
        found.push({ file: path.relative(SRC, file), target });
      }
    }
  }
  return found;
}

test.describe("no internal link points at a route that does not exist", () => {
  test("every router.push and href target resolves", () => {
    const matchers = routes(APP).map(toMatcher);
    const targets = navigationTargets();

    // Guard the guard: a regex that matched nothing would pass silently, and
    // this test's whole value is that it is actually looking.
    expect(targets.length).toBeGreaterThan(10);
    expect(matchers.length).toBeGreaterThan(10);

    const dead = targets.filter(
      ({ target }) => !matchers.some((m) => m.test(target)),
    );

    expect(
      dead.map((d) => `${d.file} → ${d.target}`),
      "these navigate to routes that do not exist",
    ).toEqual([]);
  });

  test("the safety takeover's exits both resolve", () => {
    /**
     * Named separately from the sweep above because this is the screen where a
     * 404 is not a bug but a harm, and a targeted failure message is worth
     * more than being one line in a list.
     */
    const matchers = routes(APP).map(toMatcher);
    const fromSafety = navigationTargets().filter(
      ({ file }) => file.includes("support/now") || file.includes("SafetyTakeover"),
    );
    for (const { file, target } of fromSafety) {
      expect(
        matchers.some((m) => m.test(target)),
        `${file} exits the crisis screen to ${target}, which is not a route`,
      ).toBe(true);
    }
  });
});
