import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * Per-component, per-locale screenshot baselines (§24.8 design-QA gate, §14
 * Language QA).
 *
 * The suite is driven by the BUILT Storybook index rather than a hand-kept
 * list, so a new component that ships without its `AllStates` story simply has
 * no baseline — and `library.test.ts` catches the missing component. Nothing
 * silently drops out of coverage.
 *
 * Each component's `AllStates` story holds every state the spec names for it,
 * so one baseline per component per locale covers all of its states and a
 * regression in any one of them surfaces as a diff.
 */

interface StoryIndexEntry {
  id: string;
  name: string;
  title: string;
  type: string;
  exportName: string;
}

const indexPath = path.join(__dirname, "..", "storybook-static", "index.json");

function loadStories(): StoryIndexEntry[] {
  let raw: string;
  try {
    raw = readFileSync(indexPath, "utf-8");
  } catch {
    throw new Error(
      "storybook-static/index.json is missing — run `pnpm --filter web build-storybook` before the screenshot suite",
    );
  }
  const index = JSON.parse(raw) as { entries: Record<string, StoryIndexEntry> };
  return Object.values(index.entries)
    .filter((e) => e.type === "story" && e.exportName === "AllStates")
    .sort((a, b) => a.id.localeCompare(b.id));
}

/** The §2.4 launch three plus the §24.3 Tamil-length pseudo-locale. */
const LOCALES = ["en", "hi", "hi-Latn", "ta-Pseudo"] as const;
/** §24.2 light/reading and §34.8 night/dusk. */
const THEMES = ["light", "night"] as const;

/** Components whose stories contain a loop, so the §0.12 reduced-motion path is real. */
const ANIMATED = ["foundation-button", "sitara-voicebar", "sitara-voicenotebubble", "feedback-skeleton"];

/** Storybook reads globals from the URL; `;` separates them. */
function storyUrl(id: string, globals: Record<string, string>) {
  const g = Object.entries(globals)
    .map(([k, v]) => `${k}:${v}`)
    .join(";");
  return `/iframe.html?id=${encodeURIComponent(id)}&viewMode=story&globals=${encodeURIComponent(g)}`;
}

async function openStory(page: Page, id: string, globals: Record<string, string>) {
  await page.goto(storyUrl(id, globals));
  const root = page.locator('[data-testid="story-root"]');
  await root.waitFor({ state: "visible" });
  // Storybook mounts the story asynchronously; settle before capturing.
  await page.waitForLoadState("networkidle");
  return root;
}

/** Short, stable file name: `button-en-light.png`. */
function componentSlug(id: string) {
  return id.replace(/--all-states$/, "").split("-").slice(1).join("-");
}

const stories = loadStories();

test("the story index carries every component's AllStates story", () => {
  // 49 components (§34.7 as amended by CC-007) — the suite fails loudly if
  // coverage silently shrinks.
  expect(stories.length).toBe(49);
});

for (const story of stories) {
  const slug = componentSlug(story.id);
  test.describe(story.title, () => {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${slug} · ${locale} · ${theme}`, async ({ page }) => {
          const root = await openStory(page, story.id, { locale, theme, motion: "full" });
          await expect(root).toHaveScreenshot(`${slug}-${locale}-${theme}.png`);
        });
      }
    }
  });
}

test.describe("reduced motion (§0.12)", () => {
  for (const story of stories.filter((s) => ANIMATED.includes(s.id.replace(/--all-states$/, "")))) {
    const slug = componentSlug(story.id);
    test(`${slug} · reduced motion`, async ({ page }) => {
      const root = await openStory(page, story.id, {
        locale: "en",
        theme: "light",
        motion: "reduced",
      });
      await expect(root).toHaveScreenshot(`${slug}-reduced-motion.png`);
    });
  }
});
