import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  DELETION_SCOPES,
  SCOPE_COPY,
  memoryCheckboxDefault,
  offersMemoryCheckbox,
  type DeletionScope,
} from "../src/lib/deletion-scope";

/**
 * §30.5's confirm copy, in the `library` project — no server, no browser.
 *
 * The user's ask for M10 was that the deletions have different blast radii and
 * that a person can prove a memory is gone. The proving happens server-side
 * (the §13 consent ledger); the KNOWING happens here, at the confirm step,
 * where §30.5 requires the scope be "stated".
 *
 * A sheet that promises the wrong radius passes every other test in the repo:
 * the deletion works, the API returns 200, the row is gone. Only the sentence
 * was false, and only a user finds out.
 */

const CATALOGS = ["en", "hi-Latn", "hi"] as const;

const MESSAGES = path.join(__dirname, "..", "..", "..", "packages", "i18n", "messages");

function catalog(locale: string): Record<string, unknown> {
  return JSON.parse(
    readFileSync(path.join(MESSAGES, `${locale}.json`), "utf-8"),
  ) as Record<string, unknown>;
}

function lookup(messages: Record<string, unknown>, key: string): string | undefined {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

test.describe("§30.5 — the four deletion scopes and what each confirm promises", () => {
  test("there are exactly four, and §32.15's is one of them", () => {
    // Three from §30.5, plus §32.15's family-member deletion, which §32.15
    // itself describes as "extends §30.5 scoped-deletion".
    expect([...DELETION_SCOPES]).toEqual([
      "memory",
      "journal_entry",
      "conversation",
      "family_member",
    ]);
  });

  test("every scope states what it KEEPS, not only what it deletes", () => {
    // §30.5's scopes are distinguished by what they do not touch. A sheet
    // listing only the damage teaches a user that deletion is always total,
    // and she then avoids the one that was safe.
    for (const scope of DELETION_SCOPES) {
      expect(SCOPE_COPY[scope].deletesKey, scope).toBeTruthy();
      expect(SCOPE_COPY[scope].keepsKey, scope).toBeTruthy();
    }
  });

  test("only the two scopes §30.5 gives a checkbox have one", () => {
    // Journal-entry deletion and §32.15's family deletion offer it. A
    // conversation delete does NOT: §30.5 has the memories survive outright,
    // so a checkbox there would offer a choice the spec already made.
    expect(offersMemoryCheckbox("journal_entry")).toBe(true);
    expect(offersMemoryCheckbox("family_member")).toBe(true);
    expect(offersMemoryCheckbox("conversation")).toBe(false);
    expect(offersMemoryCheckbox("memory")).toBe(false);
  });

  test("the checkbox defaults to KEEPING memories", () => {
    // §30.5: "memories sourced from it survive unless also deleted".
    // §32.15: "(default keep, listed)". One declaration, so no screen can
    // ship its own default.
    expect(memoryCheckboxDefault()).toBe(false);
  });

  test("every scope's copy resolves in all three launch locales", () => {
    // §2.4: no silent English fallback, ever — least of all on the screen
    // where someone is destroying something.
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      for (const scope of DELETION_SCOPES) {
        const copy = SCOPE_COPY[scope];
        for (const key of [
          copy.titleKey,
          copy.deletesKey,
          copy.keepsKey,
          copy.confirmKey,
          ...(copy.checkboxKey ? [copy.checkboxKey] : []),
        ]) {
          expect(lookup(messages, key), `${locale}: ${key}`).toBeTruthy();
        }
      }
    }
  });

  test("no two scopes share a copy key", () => {
    // The failure this catches: someone reuses `vault.delete.keeps` on the
    // conversation sheet because both are about memories surviving. They are
    // not the same promise — one keeps journal text, the other keeps every
    // memory — and a shared key makes one of them wrong forever.
    const keys = DELETION_SCOPES.flatMap((scope) => {
      const copy = SCOPE_COPY[scope];
      return [copy.titleKey, copy.deletesKey, copy.keepsKey, copy.confirmKey];
    });
    expect(new Set(keys).size).toBe(keys.length);
  });

  test("the conversation sheet promises memories SURVIVE", () => {
    // The scope most likely to be assumed total, so its promise is asserted
    // against the catalog text rather than only against a key existing.
    const en = catalog("en");
    const keeps = lookup(en, SCOPE_COPY.conversation.keepsKey) ?? "";
    expect(keeps.toLowerCase()).toContain("remember");
  });

  test("the memory sheet promises past journal text is unchanged", () => {
    // §30.5 states this one verbatim: "past journal text unchanged, stated at
    // confirm".
    const en = catalog("en");
    const keeps = lookup(en, SCOPE_COPY.memory.keepsKey) ?? "";
    expect(keeps.toLowerCase()).toContain("journal");
  });

  test("no confirm copy carries a countdown or a guilt line", () => {
    // §29.2: no dark patterns. A deletion sheet is where urgency copy is most
    // tempting and least acceptable.
    const forbidden = [
      "hurry",
      "last chance",
      "are you sure you want to lose",
      "you will regret",
      "expires in",
    ];
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      for (const scope of DELETION_SCOPES) {
        const copy = SCOPE_COPY[scope];
        const sentences = [copy.titleKey, copy.deletesKey, copy.keepsKey, copy.confirmKey]
          .map((key) => (lookup(messages, key) ?? "").toLowerCase())
          .join(" ");
        for (const phrase of forbidden) {
          expect(sentences, `${locale}/${scope}`).not.toContain(phrase);
        }
      }
    }
  });

  test("every scope is irreversible and says so rather than implying undo", () => {
    // None of the four has an undo anywhere in the product. A sheet that left
    // this ambiguous would be relying on a user's optimism.
    for (const scope of DELETION_SCOPES) {
      expect(SCOPE_COPY[scope as DeletionScope].irreversible, scope).toBe(true);
    }
  });
});
