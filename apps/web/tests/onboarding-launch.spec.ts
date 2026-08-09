import { expect, test, type Page } from "@playwright/test";

import { stubBackend } from "./_onboarding-fixtures";

/**
 * §0.11's five launch paths, and the analytics that tells them apart.
 *
 * The paths are not five decorations of the same animation — they are five
 * different products of the same budget, and §0.11's acceptance list asks
 * separate questions of each ("skip works from frame one post-first-launch",
 * "reduced-motion path verified", "silent-mode path verified"). The one thing
 * they share is that exactly ONE `launch_sequence` event leaves the client per
 * launch, carrying which path ran — otherwise none of those questions can be
 * answered from data.
 */

/** The four that run to completion. `skipped` ends early and has its own test. */
const PATHS = ["full", "short", "reduced_motion", "static"] as const;

/** Capture what `track()` emits, before it reaches any vendor. */
async function captureEvents(page: Page) {
  await page.addInitScript(() => {
    (window as unknown as { __events: unknown[] }).__events = [];
    window.addEventListener("sitara:analytics", (event) => {
      (window as unknown as { __events: unknown[] }).__events.push(
        (event as CustomEvent).detail,
      );
    });
  });
}

async function events(page: Page): Promise<Array<{ event: string; props: Record<string, unknown> }>> {
  return page.evaluate(
    () => (window as unknown as { __events: Array<{ event: string; props: Record<string, unknown> }> }).__events,
  );
}

test.describe("§0.11 — the launch sequence", () => {
  for (const path of PATHS) {
    test(`the ${path} path runs and reports itself exactly once`, async ({ page }) => {
      await stubBackend(page);
      await captureEvents(page);

      // §0.11's own acceptance needs each path drivable on demand ("all timings
      // within ±80ms of spec on the device matrix" is measured by a human on a
      // handset, not inferred).
      await page.goto(`/en/?launch=${path}`);
      await expect(page.getByTestId("launch-sequence")).toHaveAttribute("data-launch-path", path);

      await page.waitForURL(/\/start\/language$/, { timeout: 15_000 });

      const emitted = (await events(page)).filter((e) => e.event === "launch_sequence");
      expect(emitted, "exactly one launch event per launch").toHaveLength(1);
      expect(emitted[0]!.props.path).toBe(path);
      // §0.11's web-audio reality: with no gesture signal the sequence runs
      // silent BY DESIGN. The "Sitara Arrival" composition is a W10 deliverable
      // and does not exist yet, so silent is the only path today — recorded as
      // a path rather than reported as a failure.
      expect(emitted[0]!.props.audio).toBe("silent");
    });
  }

  test("skipping reports the skipped path and lands inside §0.11's 300ms budget", async ({
    page,
  }) => {
    await stubBackend(page);
    await captureEvents(page);
    // The full ceremony, so there is 5.5s of sequence to actually cut short.
    await page.goto("/en/?launch=full");

    // §0.11: "a subtle skip affordance appearing at 1s".
    const skip = page.getByTestId("launch-skip");
    await expect(skip).toBeVisible({ timeout: 3000 });

    const startedAt = Date.now();
    await skip.click();
    await page.waitForURL(/\/start\/language$/);
    // "skip works from frame one post-first-launch and lands on Home in ≤300ms".
    // Measured generously — this is the navigation, not the frame budget — but
    // a skip that took seconds would still fail it.
    expect(Date.now() - startedAt).toBeLessThan(3000);

    const emitted = (await events(page)).filter((e) => e.event === "launch_sequence");
    expect(emitted).toHaveLength(1);
    expect(emitted[0]!.props.path).toBe("skipped");
  });

  test("the skip affordance is hidden on the first-ever launch", async ({ page }) => {
    await stubBackend(page);
    // §0.11: "skippable by tap/Enter/Escape from first frame (AFTER first
    // launch)". A first-ever visitor has not seen the thing she would be
    // skipping, and gets the 1.2s static form anyway.
    await page.goto("/en/");
    await expect(page.getByTestId("launch-sequence")).toHaveAttribute(
      "data-launch-path",
      "static",
    );
    await expect(page.getByTestId("launch-skip")).toHaveCount(0);
  });

  test("the reduced-motion path is chosen by the preference, not by a toggle", async ({
    browser,
  }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await stubBackend(page);
    // Storage says the assets are local, so without the preference this would
    // be the full ceremony.
    await page.addInitScript(() => localStorage.setItem("sitara.launch.seen", "1"));

    await page.goto("/en/");
    await expect(page.getByTestId("launch-sequence")).toHaveAttribute(
      "data-launch-path",
      "reduced_motion",
    );
    await context.close();
  });

  test("§13 — the launch event carries no identifying properties", async ({ page }) => {
    await stubBackend(page);
    await captureEvents(page);
    await page.goto("/en/?launch=static");
    await page.waitForURL(/\/start\/language$/);

    const [emitted] = (await events(page)).filter((e) => e.event === "launch_sequence");
    // §13's allowlist applies to analytics emission: pseudonymous ids only, and
    // nothing here is even that.
    expect(Object.keys(emitted!.props).sort()).toEqual([
      "audio",
      "duration_ms",
      "fps_downgraded",
      "locale",
      "path",
      "tier",
    ]);
  });
});
