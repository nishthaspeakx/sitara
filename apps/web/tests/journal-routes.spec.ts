import { expect, test } from "@playwright/test";

import { SEED, SKIP_LAUNCH, setupRecords } from "./_onboarding-fixtures";

/**
 * The M10 routes, reached the way a browser reaches them.
 *
 * ── The one that would rot silently ───────────────────────────────────────
 *
 * `/journal/search` (S23) is a STATIC sibling of `/journal/[date]` (S22). Next
 * resolves a static segment before a dynamic one, so it works — until somebody
 * reorganises the folder, renames the segment, or "simplifies" the two into one
 * catch-all. Then `/journal/search` arrives at S22 as a date, fails to parse,
 * and renders an empty day: no error, no 404, no failing typecheck. Search
 * would simply stop existing and look like a Tuesday nothing happened on.
 *
 * That is the same shape as CL-013's defect — a routing outcome invisible to
 * everything except a request that actually travels the router — so it is
 * asserted here rather than trusted to Next's precedence rules.
 *
 * Every navigation below is a real one through the locale middleware. No
 * `page.route` anywhere.
 */

test.describe("§29.1 — M10's routes resolve", () => {
  test("/journal/search is S23, not S22 reading `search` as a date", async ({ page }) => {
    await setupRecords(page);
    await page.goto(`/en/journal/search${SKIP_LAUNCH}`);
    await expect(page.getByTestId("journal-search")).toBeVisible();
    await expect(page.getByTestId("journal-day")).toHaveCount(0);
  });

  test("the Journal's search control reaches it", async ({ page }) => {
    // §24.6: an affordance that leads nowhere is worse than a missing one, and
    // a 404'd RSC prefetch also hangs every `networkidle` wait in the suite —
    // which is how the Today sub-routes were found to matter.
    await setupRecords(page);
    await page.goto(`/en/journal${SKIP_LAUNCH}`);
    await page.getByTestId("journal-search-link").click();
    await expect(page).toHaveURL(/\/en\/journal\/search$/);
    await expect(page.getByTestId("journal-search")).toBeVisible();
  });

  test("a day heading opens that day", async ({ page }) => {
    await setupRecords(page);
    await page.goto(`/en/journal${SKIP_LAUNCH}`);
    await page.getByTestId("open-day").first().click();
    await expect(page).toHaveURL(/\/en\/journal\/2026-08-15$/);
    await expect(page.getByTestId("journal-day")).toBeVisible();
  });

  test("the You tab reaches both of the destinations it lists", async ({ page }) => {
    // §24.1 gives this tab six; M10 built two. The other four have no row at
    // all rather than a disabled one — see `you/page.tsx` — so this asserts the
    // two that exist actually arrive.
    await setupRecords(page);
    await page.goto(`/en/you${SKIP_LAUNCH}`);
    await page.getByRole("button", { name: /What Tara remembers/ }).click();
    await expect(page).toHaveURL(/\/en\/you\/memories$/);

    await page.goto(`/en/you${SKIP_LAUNCH}`);
    await page.getByRole("button", { name: /Your people/ }).click();
    await expect(page).toHaveURL(/\/en\/you\/family$/);
  });

  test("the You home links to nothing it has not built", async ({ page }) => {
    // The rule this protects: no row navigates to a route that does not exist,
    // and no row is rendered disabled. `you.later` is a sentence, not a control.
    await setupRecords(page);
    await page.goto(`/en/you${SKIP_LAUNCH}`);
    await expect(page.getByTestId("you-later")).toBeVisible();
    const disabled = await page.locator("button[disabled], a[aria-disabled='true']").count();
    expect(disabled).toBe(0);
  });

  test("a member id that resolves to nobody is an honest miss, not a 404", async ({ page }) => {
    // §30.5 scopes family to the account holder, so an id that is not hers
    // resolves to nothing — and §24.6 has no dead ends, so it is a sentence
    // rather than a crash. The id is ObjectId-shaped: the real router parses
    // every path id and this asserts the MISS, not a validation error.
    await setupRecords(page);
    await page.goto(`/en/you/family/6f10000000000000000000ff${SKIP_LAUNCH}`);
    await expect(page.getByTestId("member-missing")).toBeVisible();
  });

  test("a vault id that no longer exists says so instead of a blank detail", async ({ page }) => {
    await setupRecords(page);
    await page.goto(`/en/you/memories/6b10000000000000000000ff${SKIP_LAUNCH}`);
    await expect(page.getByTestId("memory-missing")).toBeVisible();
  });

  test("every M10 surface is behind the §34.5 session, as its API is", async ({ page }) => {
    // The stub refuses `/v1` without a session because the real API does. This
    // asserts the SCREENS surface that refusal rather than rendering an empty
    // list — a signed-out vault that looked merely empty would be the most
    // reassuring possible lie.
    await setupRecords(page, {});
    await page.goto(`/en/you/memories${SKIP_LAUNCH}`);
    await expect(page.getByTestId("vault")).toBeVisible();
  });
});

test.describe("S24 — the night reflection is Today's evening state", () => {
  test("it lives under /today, not as a fifth tab (§24.1)", async ({ page }) => {
    await setupRecords(page);
    await page.goto(`/en/today/reflection${SKIP_LAUNCH}`);
    await expect(page.getByTestId("reflection")).toBeVisible();
    // Four tabs, and only four. A reflection route that had grown its own tab
    // would be visible here and nowhere else.
    await expect(page.getByRole("navigation")).toHaveCount(0);
  });

  test("nothing on it counts, streaks or nags (§29.2)", async ({ page }) => {
    await setupRecords(page);
    await page.goto(`/en/today/reflection${SKIP_LAUNCH}`);
    await expect(page.getByTestId("reflection-gentle")).toBeVisible();
    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const phrase of ["streak", "don't break", "keep it up", "you missed", "day in a row"]) {
      expect(body).not.toContain(phrase);
    }
  });

  test("what she writes survives a reload — §6.4's unique index on (user, date)", async ({
    page,
  }) => {
    // A PUT that is idempotent on the day is what makes it safe to save as she
    // writes. §29.2 wants no moment where closing the app loses the evening.
    await setupRecords(page);
    await page.goto(`/en/today/reflection${SKIP_LAUNCH}`);
    const box = page.getByRole("textbox").first();
    await box.fill("The week finally settled.");
    await page.getByRole("button", { name: "Keep this" }).first().click();
    await expect(page.getByTestId("reflection-saved")).toBeVisible();

    await page.reload();
    await expect(page.getByRole("textbox").first()).toHaveValue("The week finally settled.");
  });

  test("the prompts are asked in the order the SERVER gave", async ({ page }) => {
    // `prompt_order` is served, never assumed from the client's own list — two
    // declarations of a ceremony's order are two things that can disagree about
    // the shape of the ceremony.
    await setupRecords(page);
    await page.goto(`/en/today/reflection${SKIP_LAUNCH}`);
    // `evaluateAll` on an empty locator resolves to `[]` rather than waiting,
    // so without this the assertion races the first paint and compares against
    // nothing. It passed in isolation and failed under four workers — the same
    // shape as the `data-connected` race `ask()` documents.
    await expect(page.getByRole("textbox")).toHaveCount(3);
    const labels = await page.getByRole("textbox").evaluateAll((nodes) =>
      nodes.map((n) => n.previousElementSibling?.textContent ?? ""),
    );
    expect(labels).toEqual([
      "What are you glad of today?",
      "What sat heavy?",
      "What would you like tomorrow to hold?",
    ]);
  });
});

test.describe("S26 — mute and delete are opposites and stay that way", () => {
  test("muting keeps the memory in the vault and says it is set aside", async ({ page }) => {
    // §30.5's "don't remember this": withheld from retrieval, KEPT, reversible.
    // The failure this catches is a mute wired to the delete endpoint, which
    // would look identical on the screen that performed it.
    await setupRecords(page);
    await page.goto(`/en/you/memories/${SEED.memories.practice}${SKIP_LAUNCH}`);
    await page.getByRole("switch").click();

    await page.goto(`/en/you/memories${SKIP_LAUNCH}`);
    const row = page.locator(`[data-memory-id="${SEED.memories.practice}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("data-muted", "true");
  });
});

test.describe("§34.5 — a spent access token refreshes instead of failing", () => {
  test("a 401 mid-session is recovered, not rendered as a fatal error", async ({ page }) => {
    // The access cookie lives 15 minutes and the refresh cookie 30 days. That
    // pair exists so a session SURVIVES, and no client code called the refresh
    // endpoint — so every app open older than a quarter of an hour met a 401 on
    // its first read and rendered "Tara will be right back … that sign-in
    // didn't go through", with a trace code, as though something had broken.
    //
    // The stub spends the token exactly ONCE, so this fails against a client
    // that gives up quietly AND against one that loops.
    await setupRecords(page, { scenario: "session_expires_once" });
    await page.goto(`/en/journal${SKIP_LAUNCH}`);

    await expect(page.getByTestId("journal")).toBeVisible();
    await expect(page.getByText(/right back/i)).toHaveCount(0);
    await expect(page.getByText(/didn't go through/i)).toHaveCount(0);
  });

  test("the refresh endpoint itself is never retried", async ({ page }) => {
    // A 401 from the refresh means the refresh cookie is spent too — a real
    // sign-out, not a hiccup. Retrying it would loop forever behind a screen
    // that looks merely slow.
    const calls: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/auth/session/refresh")) calls.push(r.url());
    });
    await setupRecords(page, { state: { session_user_id: null } });
    await page.goto(`/en/journal${SKIP_LAUNCH}`);
    await expect(page.getByTestId("journal")).toBeVisible();
    expect(calls.length).toBeLessThanOrEqual(1);
  });
});
