import { expect, test } from "@playwright/test";

import { SKIP_LAUNCH, setupToday } from "./_onboarding-fixtures";

/**
 * The dev device frame (Task A) — and the three ways a wrapper fails to be one.
 *
 * These are behavioural, not visual: no baseline is recorded here. The frame's
 * whole job is to change what the app is measured AGAINST, so a screenshot of
 * the frame proves the chrome drew and nothing about containment.
 *
 * The `screens` project runs at 390×844, below the frame's 900px activation
 * threshold, so every other spec in the suite runs UNFRAMED without opting
 * out. That is deliberate: the existing ~400 baselines were recorded at that
 * viewport and the frame must not be able to touch them.
 */

const FRAMED = { width: 1440, height: 900 };

test.describe("the frame contains what a wrapper cannot", () => {
  test.use({ viewport: FRAMED });

  test("the app root is exactly one iPhone 17", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    const frame = page.locator('[data-testid="device-frame"]');
    await frame.waitFor({ state: "visible" });

    const box = await frame.boundingBox();
    expect(box?.width).toBe(402);
    expect(box?.height).toBe(874);
  });

  test("a position:fixed descendant resolves against the phone, not the window", async ({
    page,
  }) => {
    /**
     * The mechanism, asserted directly. `position: fixed` positions against
     * the viewport unless an ancestor establishes a containing block — which
     * is why the Sheet, the Modal, the Toast and the launch sequence would
     * otherwise cover the laptop. `contain: layout paint` is what makes this
     * pass; deleting it fails here rather than in a screenshot nobody reads.
     */
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.locator('[data-testid="device-frame"]').waitFor({ state: "visible" });

    const result = await page.evaluate(() => {
      const vp = document.querySelector('[data-testid="device-frame-viewport"]')!;
      const frame = document
        .querySelector('[data-testid="device-frame"]')!
        .getBoundingClientRect();
      const probe = document.createElement("div");
      probe.style.cssText = "position:fixed;inset:0;";
      vp.appendChild(probe);
      const r = probe.getBoundingClientRect();
      probe.remove();
      return {
        frame: { x: Math.round(frame.x), y: Math.round(frame.y), w: frame.width, h: frame.height },
        fixed: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        window: { w: window.innerWidth, h: window.innerHeight },
      };
    });

    expect(result.fixed).toEqual({
      x: result.frame.x,
      y: result.frame.y,
      w: result.frame.w,
      h: result.frame.h,
    });
    // And it is genuinely NOT the window, or the assertion above is vacuous.
    expect(result.fixed.w).toBeLessThan(result.window.w);
  });

  test("the tab bar lands inside the phone", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    const frame = page.locator('[data-testid="device-frame"]');
    await frame.waitFor({ state: "visible" });

    const frameBox = (await frame.boundingBox())!;
    const nav = page.locator("nav").first();
    await nav.scrollIntoViewIfNeeded();
    const navBox = (await nav.boundingBox())!;

    expect(navBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
    expect(navBox.x + navBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  });

  test("--app-vh is the phone's height, and the app measures against it", async ({
    page,
  }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.locator('[data-testid="device-frame"]').waitFor({ state: "visible" });

    const vars = await page.evaluate(() => {
      const backdrop = document.querySelector('[data-testid="device-frame-backdrop"]')!;
      const s = getComputedStyle(backdrop);
      return {
        vh: s.getPropertyValue("--app-vh").trim(),
        top: s.getPropertyValue("--app-safe-top").trim(),
        bottom: s.getPropertyValue("--app-safe-bottom").trim(),
        rootVh: getComputedStyle(document.documentElement).getPropertyValue("--app-vh").trim(),
      };
    });
    expect(vars.vh).toBe("874px");
    expect(vars.top).toBe("59px");
    expect(vars.bottom).toBe("34px");
    // The unframed fallback is untouched — this is what every other spec and
    // every real phone reads.
    expect(vars.rootVh).toBe("100dvh");
  });

  test("?frame=0 turns it off for one load", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today?frame=0`);
    await page.locator('[data-testid="today"]').waitFor({ state: "visible" });
    await expect(page.locator('[data-testid="device-frame"]')).toHaveCount(0);
  });
});

test.describe("it is inert where it must be", () => {
  test("below 900px the frame does not mount", async ({ page }) => {
    /**
     * This is why the other ~400 baselines cannot churn: the `screens`
     * project's 390×844 viewport is below the threshold, so every existing
     * spec runs unframed without knowing the frame exists.
     */
    await page.setViewportSize({ width: 390, height: 844 });
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.locator('[data-testid="today"]').waitFor({ state: "visible" });

    await expect(page.locator('[data-testid="device-frame"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="device-frame-backdrop"]')).toHaveCount(0);
  });

  test("a coarse pointer does not get a phone drawn inside a phone", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: FRAMED,
      hasTouch: true,
      isMobile: false,
    });
    const page = await context.newPage();
    // `hasTouch` alone does not always make the media query coarse, so force
    // the condition the component actually reads.
    await page.emulateMedia({ reducedMotion: null });
    await page.addInitScript(() => {
      const real = window.matchMedia.bind(window);
      window.matchMedia = ((q: string) =>
        q.includes("coarse") ? ({ matches: true, media: q, addEventListener() {}, removeEventListener() {} } as unknown as MediaQueryList) : real(q)) as typeof window.matchMedia;
    });
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.locator('[data-testid="today"]').waitFor({ state: "visible" });

    await expect(page.locator('[data-testid="device-frame"]')).toHaveCount(0);
    await context.close();
  });
});
