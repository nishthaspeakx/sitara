import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { MEMORIAL_COPY, SCOPE_COPY } from "../src/lib/deletion-scope";
import { SEED, SKIP_LAUNCH, records, setupRecords } from "./_onboarding-fixtures";

/**
 * §30.5's deletion confirmations, on the real screens, over the real path.
 *
 * ── Why this suite exists next to `deletion-scope.spec.ts` ─────────────────
 *
 * That one asserts the copy is RIGHT: four scopes, each stating what it keeps,
 * no two sharing a key, all three locales. It reads catalogs off disk and can
 * say nothing about whether a screen renders the sentence it is holding.
 *
 * This one asserts the copy is READ and that the promise it makes is KEPT. The
 * gap between them is where the whole class of defect lives: the sheet renders
 * `vault.delete.keeps` — "anything already written in your journal stays
 * exactly as it is" — and then the delete cascades into the journal anyway.
 * Every gate stays green. The API returns 200. The row is gone. The sentence
 * she read before tapping was false, and only she finds out.
 *
 * So every case below does the same three things:
 *
 *   1. read the exact sentence off the sheet and compare it to the catalog,
 *   2. confirm,
 *   3. assert what SURVIVED as hard as what died — in the DOM *and* in the
 *      stub's own record state, because a screen that merely hid a row it
 *      never deleted would pass a DOM-only assertion perfectly.
 *
 * ── No `page.route`, anywhere (CL-013) ────────────────────────────────────
 *
 * The confirm sheets POST through the locale middleware and the `/v1` rewrite
 * like everything else. An intercept would stop each delete before the server
 * saw it, and this suite would then be verifying that the client handles a
 * response the test invented — while the deletion it is about never happened.
 */

const MESSAGES = path.join(__dirname, "..", "..", "..", "packages", "i18n", "messages");

function catalog(locale: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path.join(MESSAGES, `${locale}.json`), "utf-8")) as Record<
    string,
    unknown
  >;
}

/** The catalog sentence, with ICU's `{name}` filled the way the screen fills it. */
function copy(locale: string, key: string, values: Record<string, string> = {}): string {
  let node: unknown = catalog(locale);
  for (const part of key.split(".")) node = (node as Record<string, unknown>)?.[part];
  let text = String(node);
  for (const [k, v] of Object.entries(values)) text = text.split(`{${k}}`).join(v);
  return text;
}

async function open(page: Page, locale: string, route: string, ready: string): Promise<void> {
  await page.goto(`/${locale}${route}${SKIP_LAUNCH}`);
  await page.locator(ready).first().waitFor({ state: "visible" });
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

/** A memory still in the vault, by id — the survival assertion's other half. */
function hasMemory(state: Awaited<ReturnType<typeof records>>, id: string): boolean {
  return state.memories.some((m) => m.memory_id === id);
}

function day(state: Awaited<ReturnType<typeof records>>, date: string) {
  return state.journal.find((d) => d.local_date === date);
}

// ───────────────────────────────────────────────────────────────────────────
// §30.5 — delete a memory
// ───────────────────────────────────────────────────────────────────────────

test.describe("S26 — forgetting a memory (§30.5)", () => {
  test("the sheet says exactly what the catalog says, in all three locales", async ({ page }) => {
    // §2.4 has no exception for a destructive confirm — least of all here. A
    // sheet that fell back to English on the screen where someone is destroying
    // something is the worst instance of the defect §2.4 forbids.
    for (const locale of ["en", "hi", "hi-Latn"]) {
      await setupRecords(page, { locale });
      await open(page, locale, `/you/memories/${SEED.memories.preference}`, '[data-testid="memory"]');
      await page.getByTestId("memory-forget").click();

      const sheet = page.getByTestId("confirm-memory");
      await expect(sheet).toBeVisible();
      await expect(sheet.getByTestId("confirm-deletes")).toHaveText(
        copy(locale, SCOPE_COPY.memory.deletesKey),
      );
      await expect(sheet.getByTestId("confirm-keeps")).toHaveText(
        copy(locale, SCOPE_COPY.memory.keepsKey),
      );
      await expect(sheet.getByTestId("confirm-submit")).toHaveText(
        copy(locale, SCOPE_COPY.memory.confirmKey),
      );
    }
  });

  test("§30.5's promise holds: Tara forgets it, the journal text does not change", async ({
    page,
  }) => {
    const client = await setupRecords(page);
    const before = await records(client);
    // The entry the memory was learned from, with the words it was learned in.
    const entryBefore = day(before, "2026-08-14")?.entries.find(
      (e) => e.ref === SEED.journal.guidance,
    );
    expect(entryBefore?.preview).toBeTruthy();

    await open(page, "en", `/you/memories/${SEED.memories.preference}`, '[data-testid="memory"]');
    await page.getByTestId("memory-forget").click();
    await page.getByTestId("confirm-submit").click();

    // What died.
    await expect(page).toHaveURL(/\/you\/memories$/);
    await expect(page.getByTestId("vault")).toBeVisible();
    await expect(
      page.locator(`[data-memory-id="${SEED.memories.preference}"]`),
    ).toHaveCount(0);

    // What survived — asserted at least as hard. The journal entry is still
    // there AND still says the same thing: "past journal text unchanged" is a
    // promise about the words, not merely about the row's existence.
    const after = await records(client);
    expect(hasMemory(after, SEED.memories.preference)).toBe(false);
    const entryAfter = day(after, "2026-08-14")?.entries.find(
      (e) => e.ref === SEED.journal.guidance,
    );
    expect(entryAfter).toBeTruthy();
    expect(entryAfter?.preview).toBe(entryBefore?.preview);

    // And the two memories this deletion had no business touching.
    expect(hasMemory(after, SEED.memories.anniversary)).toBe(true);
    expect(hasMemory(after, SEED.memories.practice)).toBe(true);

    // The screen agrees with the server about the journal.
    await open(page, "en", "/journal/2026-08-14", '[data-testid="journal-day"]');
    await expect(page.getByText(entryBefore!.preview!)).toBeVisible();
  });

  test("closing the sheet deletes nothing", async ({ page }) => {
    // §29.2: close is always available. It is also the branch nobody writes a
    // test for, which is how a sheet ends up firing its request on dismiss.
    const client = await setupRecords(page);
    await open(page, "en", `/you/memories/${SEED.memories.practice}`, '[data-testid="memory"]');
    await page.getByTestId("memory-forget").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("confirm-memory")).toHaveCount(0);
    expect(hasMemory(await records(client), SEED.memories.practice)).toBe(true);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// §30.5 — delete a journal entry, and its checkbox
// ───────────────────────────────────────────────────────────────────────────

test.describe("S22 — deleting a journal entry (§30.5)", () => {
  test("the checkbox is offered, and it is UNTICKED", async ({ page }) => {
    // §30.5: "memories sourced from it survive unless also deleted". The
    // default IS the promise. A ticked box would make the sheet's own `keeps`
    // line false on arrival.
    await setupRecords(page);
    await open(page, "en", "/journal/2026-08-14", '[data-testid="journal-day"]');
    await page.locator(`[data-ref="${SEED.journal.guidance}"]`).getByTestId("entry-delete").click();

    const sheet = page.getByTestId("confirm-journal_entry");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByTestId("confirm-keeps")).toHaveText(
      copy("en", SCOPE_COPY.journal_entry.keepsKey),
    );
    await expect(sheet.getByTestId("confirm-checkbox")).not.toBeChecked();
  });

  test("unticked: the entry goes, the memory it taught her stays", async ({ page }) => {
    const client = await setupRecords(page);
    await open(page, "en", "/journal/2026-08-14", '[data-testid="journal-day"]');
    await page.locator(`[data-ref="${SEED.journal.guidance}"]`).getByTestId("entry-delete").click();
    await page.getByTestId("confirm-submit").click();

    await expect(page.locator(`[data-ref="${SEED.journal.guidance}"]`)).toHaveCount(0);

    const after = await records(client);
    expect(day(after, "2026-08-14")?.entries.some((e) => e.ref === SEED.journal.guidance)).toBe(
      false,
    );
    // The whole point of the sheet. The memory outlives its source artefact.
    expect(hasMemory(after, SEED.memories.preference)).toBe(true);
  });

  test("ticked: the entry goes and so does the memory sourced from it", async ({ page }) => {
    // The other half of the same promise, and it has to be tested with the same
    // weight — a checkbox that quietly did nothing would pass every assertion
    // in the test above.
    const client = await setupRecords(page);
    await open(page, "en", "/journal/2026-08-14", '[data-testid="journal-day"]');
    await page.locator(`[data-ref="${SEED.journal.guidance}"]`).getByTestId("entry-delete").click();
    await page.getByTestId("confirm-checkbox").check();
    await page.getByTestId("confirm-submit").click();

    const after = await records(client);
    expect(day(after, "2026-08-14")?.entries.some((e) => e.ref === SEED.journal.guidance)).toBe(
      false,
    );
    expect(hasMemory(after, SEED.memories.preference)).toBe(false);
    // Scoped to what this entry taught her, and to nothing else. A tick that
    // meant "delete every memory" would still pass the line above.
    expect(hasMemory(after, SEED.memories.anniversary)).toBe(true);
    expect(hasMemory(after, SEED.memories.practice)).toBe(true);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// §32.15 — removing a family member, and §45's alternative on the same sheet
// ───────────────────────────────────────────────────────────────────────────

test.describe("S28 — the family record sheet (§32.15, §45)", () => {
  const MOTHER = "Sudha";

  test("§45.3: the non-destructive option is presented first", async ({ page }) => {
    // Not "is present" — is FIRST. §45.3 fixes the order because this sheet
    // appears at exactly one moment, and the option a grieving person meets
    // first is a product decision, not a layout one.
    await setupRecords(page);
    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();

    const sheet = page.getByTestId("family-record-sheet");
    await expect(sheet).toBeVisible();
    const memorial = await sheet.getByTestId("memorial-section").boundingBox();
    const remove = await sheet.getByTestId("delete-section").boundingBox();
    expect(memorial!.y).toBeLessThan(remove!.y);
  });

  test("the memorial half says what stays, what changes, and that it can be undone", async ({
    page,
  }) => {
    // All three, in all three locales. §45.2 names one behavioural change and
    // the sheet has to name it too — copy that promised only survival would be
    // false the first morning a birthday did not arrive.
    for (const locale of ["en", "hi", "hi-Latn"]) {
      await setupRecords(page, { locale });
      await open(page, locale, `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
      await page.getByTestId("member-record").click();

      const memorial = page.getByTestId("memorial-section");
      await expect(memorial.getByTestId("memorial-keeps")).toHaveText(
        copy(locale, MEMORIAL_COPY.keepsKey),
      );
      await expect(memorial.getByTestId("memorial-reminders")).toHaveText(
        copy(locale, MEMORIAL_COPY.remindersKey),
      );
      await expect(memorial.getByTestId("memorial-reversible")).toHaveText(
        copy(locale, MEMORIAL_COPY.reversibleKey),
      );
    }
  });

  test("the conversion destroys nothing — asserted collection by collection", async ({ page }) => {
    // §45.2: "one $set, one field, no cascade". The danger here is INVERTED
    // from a deletion's: a conversion that quietly removed something is a
    // bereaved user losing her mother's birth chart because she chose the
    // gentle option, and nobody audits for it because nobody expects the gentle
    // option to take anything. So survival is asserted piece by piece rather
    // than by a single "the member is still there".
    const client = await setupRecords(page);
    const before = await records(client);

    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await page.getByTestId("memorial-confirm").click();

    const after = await records(client);
    const member = after.family.find((m) => m.member_id === SEED.family.mother);
    expect(member?.memorial_state).toBe("in_memory");

    expect(member?.has_birth_details).toBe(true);
    expect(after.birth_details[SEED.family.mother]).toBe(before.birth_details[SEED.family.mother]);
    expect(after.charts[SEED.family.mother]).toBe(before.charts[SEED.family.mother]);
    expect(after.attestations[SEED.family.mother]).toBe(before.attestations[SEED.family.mother]);
    expect(after.memories).toEqual(before.memories);
    expect(after.journal).toEqual(before.journal);

    // And she is still in the family list, marked rather than removed.
    await open(page, "en", "/you/family", '[data-testid="family"]');
    const card = page.locator(`[data-member-id="${SEED.family.mother}"]`);
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-memorial", "in_memory");
  });

  test("the conversion is reversible, and undoing it destroys nothing either", async ({ page }) => {
    // §45.2 makes a wrong tap survivable. A revert that lost anything would
    // turn the safety net into the second loss.
    const client = await setupRecords(page);
    const before = await records(client);

    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await page.getByTestId("memorial-confirm").click();

    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("memorial-revert")).toBeVisible();
    await page.getByTestId("memorial-revert").click();

    const after = await records(client);
    expect(after.family.find((m) => m.member_id === SEED.family.mother)?.memorial_state).toBe(
      "living",
    );
    expect(after.memories).toEqual(before.memories);
    expect(after.journal).toEqual(before.journal);
    expect(after.birth_details[SEED.family.mother]).toBe(before.birth_details[SEED.family.mother]);
  });

  test("§32.15's checkbox LISTS the candidates rather than asserting a count", async ({ page }) => {
    // "about them" is a name match, which is a judgement. §32.15 requires the
    // judgement be shown and ticked, never made silently — a boolean would take
    // "Sudha's birthday is 11 March" along with a stranger's remark containing
    // the word.
    await setupRecords(page);
    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();

    const remove = page.getByTestId("delete-section");
    const candidate = remove.locator(`[data-memory-id="${SEED.memories.anniversary}"]`);
    await expect(candidate).toBeVisible();
    // Shown with its CONTENT — she is being asked whether to delete this, so
    // showing it is the whole point.
    await expect(candidate).toContainText("11 March");
    await expect(candidate.getByRole("checkbox")).not.toBeChecked();
  });

  test("removing her: the chart dies, the unticked note and the journal live", async ({ page }) => {
    const client = await setupRecords(page);
    const before = await records(client);

    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("confirm-deletes")).toHaveText(
      copy("en", SCOPE_COPY.family_member.deletesKey, { name: MOTHER }),
    );
    await page.getByTestId("confirm-submit").click();

    const after = await records(client);
    // What dies (§32.15's radius).
    expect(after.family.some((m) => m.member_id === SEED.family.mother)).toBe(false);
    expect(after.birth_details[SEED.family.mother] ?? 0).toBe(0);
    expect(after.charts[SEED.family.mother] ?? 0).toBe(0);
    // What lives, and each is its own clause of §32.15.
    expect(hasMemory(after, SEED.memories.anniversary)).toBe(true); // unticked
    expect(after.journal).toEqual(before.journal); // "keeps past journal text"
    // DPDP: the consent is a fact about the account-holder; the birth details
    // were a fact about someone else. The attestation is REVOKED, never erased.
    expect(after.attestations[SEED.family.mother]).toBe("revoked");
    // The other member is untouched.
    expect(after.family.some((m) => m.member_id === SEED.family.son)).toBe(true);
  });

  test("removing her with the note ticked takes that note and no other", async ({ page }) => {
    const client = await setupRecords(page);
    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await page
      .locator(`[data-memory-id="${SEED.memories.anniversary}"]`)
      .getByRole("checkbox")
      .check();
    await page.getByTestId("confirm-submit").click();

    const after = await records(client);
    expect(hasMemory(after, SEED.memories.anniversary)).toBe(false);
    expect(hasMemory(after, SEED.memories.preference)).toBe(true);
    expect(hasMemory(after, SEED.memories.practice)).toBe(true);
  });

  test("a member already in memory can still be removed, with the same radius", async ({
    page,
  }) => {
    // §45.3: the conversion is an alternative, never a replacement. The path
    // that would rot is exactly this one — the destructive half hidden or
    // weakened once the gentle state is set, so a user who converts by mistake
    // and then genuinely wants the record gone cannot get there.
    const client = await setupRecords(page);
    await open(page, "en", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await page.getByTestId("memorial-confirm").click();

    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("delete-section")).toBeVisible();
    await page.getByTestId("confirm-submit").click();

    const after = await records(client);
    expect(after.family.some((m) => m.member_id === SEED.family.mother)).toBe(false);
    expect(after.birth_details[SEED.family.mother] ?? 0).toBe(0);
    expect(after.attestations[SEED.family.mother]).toBe("revoked");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The properties every confirm sheet shares
// ───────────────────────────────────────────────────────────────────────────

test.describe("every confirm sheet, whatever it is confirming", () => {
  const SHEETS = [
    {
      id: "memory",
      route: `/you/memories/${SEED.memories.practice}`,
      ready: '[data-testid="memory"]',
      opener: "memory-forget",
    },
    {
      id: "journal_entry",
      route: "/journal/2026-08-14",
      ready: '[data-testid="journal-day"]',
      opener: "entry-delete",
    },
    {
      id: "family_member",
      route: `/you/family/${SEED.family.son}`,
      ready: '[data-testid="member"]',
      opener: "member-record",
    },
  ] as const;

  for (const sheet of SHEETS) {
    test(`${sheet.id}: states what it keeps, not only what it takes`, async ({ page }) => {
      // §30.5's scopes are distinguished by what they do NOT touch. A sheet
      // listing only the damage teaches a user that deletion is always total,
      // and she then avoids the one that was safe.
      await setupRecords(page);
      await open(page, "en", sheet.route, sheet.ready);
      await page.getByTestId(sheet.opener).first().click();
      await expect(page.getByTestId("confirm-deletes").first()).toBeVisible();
      await expect(page.getByTestId("confirm-keeps").first()).toBeVisible();
    });

    test(`${sheet.id}: close is always available (§29.2)`, async ({ page }) => {
      await setupRecords(page);
      await open(page, "en", sheet.route, sheet.ready);
      await page.getByTestId(sheet.opener).first().click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("button", { name: /close|बंद|band/i }).first()).toBeVisible();
    });

    test(`${sheet.id}: no countdown, no guilt, no urgency (§29.2)`, async ({ page }) => {
      // The catalog is checked for this too, but a screen can add a sentence
      // the catalog never held — a "3 days to change your mind" rendered from a
      // date, say. This reads what is actually on the sheet.
      await setupRecords(page);
      await open(page, "en", sheet.route, sheet.ready);
      await page.getByTestId(sheet.opener).first().click();
      const text = (await page.getByRole("dialog").innerText()).toLowerCase();
      for (const phrase of ["hurry", "last chance", "you will lose", "act now", "expires"]) {
        expect(text, sheet.id).not.toContain(phrase);
      }
    });
  }
});
