import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  CONVERSATION_DELETE_IS_UNBUILT,
  DELETION_SCOPES,
  FAMILY_SHEET_ORDER,
  MEMORIAL_COPY,
  MEMORIAL_PROMISE_KEYS,
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

/**
 * §45 (CC-012) — the alternative on the same sheet.
 *
 * The endpoint has existed since `a57dcaa` with no user-facing copy at all,
 * which meant that for one release the product could convert a member to
 * `in_memory` and had no sentence in any locale to describe doing it. These
 * tests are what that copy is held to.
 *
 * The direction of danger is INVERTED here and every assertion below follows
 * from that. A deletion that quietly kept something is a privacy bug an audit
 * finds. A conversion that quietly removed something is a bereaved user losing
 * her mother's birth chart because she chose the gentle option, and nobody
 * audits for it because nobody expects the gentle option to take anything.
 */
test.describe("§45 — 'in memory of', the non-destructive half of the same sheet", () => {
  test("it is reversible, and every deletion beside it is not", () => {
    // Asserted as a PAIR rather than alone. The two branches of one sheet must
    // never be presented at the same weight, and the day someone marks a
    // deletion reversible — or marks this irreversible to "keep the sheet
    // consistent" — is the day that stops being true.
    expect(MEMORIAL_COPY.reversible).toBe(true);
    for (const scope of DELETION_SCOPES) {
      expect(SCOPE_COPY[scope].irreversible, scope).toBe(true);
    }
  });

  test("§45.3 presents the non-destructive option first", () => {
    // "The two are offered together on one sheet, and the non-destructive one
    // is presented first." Order is data, so the sheet reads it rather than a
    // reviewer remembering it.
    expect([...FAMILY_SHEET_ORDER]).toEqual(["memorial", "delete"]);
    expect(FAMILY_SHEET_ORDER.indexOf("memorial")).toBeLessThan(
      FAMILY_SHEET_ORDER.indexOf("delete"),
    );
  });

  test("it states what survives, and states the one thing that changes", () => {
    // Both, and neither is optional. Copy that promised only survival would be
    // false the first morning a birthday did not arrive, and copy that named
    // only the change would leave the survival — the entire point — unsaid.
    expect(MEMORIAL_COPY.keepsKey).toBeTruthy();
    expect(MEMORIAL_COPY.remindersKey).toBeTruthy();
    const en = catalog("en");
    expect(lookup(en, MEMORIAL_COPY.keepsKey)?.toLowerCase()).toContain("nothing is deleted");
    // §45.2's reminders, named on the sheet rather than discovered in October.
    expect(lookup(en, MEMORIAL_COPY.remindersKey)?.toLowerCase()).toContain("birthday");
  });

  test("undoing it destroys nothing either, and says so", () => {
    // §45.2 makes the conversion reversible; the revert is therefore a second
    // write of one field. A user reversing a wrong tap is owed the same promise
    // as the one who made it.
    const en = catalog("en");
    const revert = lookup(en, MEMORIAL_COPY.revertBodyKey)?.toLowerCase() ?? "";
    expect(revert).toContain("nothing");
  });

  test("every memorial string resolves in all three launch locales", () => {
    // §2.4, on the sheet where a person is deciding what happens to the record
    // of someone who has died. An English fallback here would be the worst
    // place in the product for one.
    const keys = Object.entries(MEMORIAL_COPY)
      .filter(([, value]) => typeof value === "string")
      .map(([, value]) => value as string);
    expect(keys.length).toBeGreaterThan(0);
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      for (const key of keys) {
        expect(lookup(messages, key), `${locale}: ${key}`).toBeTruthy();
      }
    }
  });

  test("it shares no key with the deletion it sits above", () => {
    // The same rule the four scopes are held to, for the same reason and with
    // more at stake: these two blocks are eight lines apart on one sheet, and a
    // shared key would make the gentle promise and the destructive one the same
    // sentence — permanently wrong for one of them.
    const scopeKeys = new Set(
      DELETION_SCOPES.flatMap((scope) => {
        const copy = SCOPE_COPY[scope];
        return [
          copy.titleKey,
          copy.deletesKey,
          copy.keepsKey,
          copy.confirmKey,
          ...(copy.checkboxKey ? [copy.checkboxKey] : []),
        ];
      }),
    );
    for (const [field, value] of Object.entries(MEMORIAL_COPY)) {
      if (typeof value !== "string") continue;
      expect(scopeKeys.has(value), `${field} (${value})`).toBe(false);
    }
  });

  test("the two buttons on the sheet never read the same, in any locale", () => {
    // One sheet, two actions, opposite consequences. A locale where both
    // resolved to the same verb would be a coin toss over someone's records,
    // and it would look completely fine in English.
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      const keep = lookup(messages, MEMORIAL_COPY.confirmKey);
      const remove = lookup(messages, SCOPE_COPY.family_member.confirmKey);
      expect(keep, locale).toBeTruthy();
      expect(remove, locale).toBeTruthy();
      expect(keep, locale).not.toBe(remove);
    }
  });

  test("no promise it makes is written in the vocabulary of deletion", () => {
    // The failure this catches is concrete and likely: someone drafts this
    // block by copying `family.delete.*` and softening it, and one destructive
    // verb survives the edit. §45.2's guarantee is that the conversion "writes
    // one field and touches no other collection" — so no sentence describing it
    // may say anything was removed.
    //
    // `orDeleteKey` is deliberately excluded: it is the bridge to §32.15's
    // destructive half and says "remove" on purpose. Everything else here is a
    // sentence about the gentle option.
    const destructive: Record<string, string[]> = {
      en: ["delet", "remov", "erase", "wipe"],
      hi: ["मिट", "हटा", "मिटा"],
      "hi-Latn": ["delete", "hata", "mita", "remove"],
    };
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      for (const field of MEMORIAL_PROMISE_KEYS) {
        const key = MEMORIAL_COPY[field];
        if (typeof key !== "string") continue;
        // "Nothing is deleted" is the correct sentence and contains the verb,
        // so the check is negation-aware in the same way the CC-008 guard is —
        // but by REMOVING the negated phrase and checking what is left, not by
        // exempting the whole line. Exempting the line would let "nothing is
        // deleted, we remove the chart" through, which is the exact sentence
        // this test exists to stop.
        let text = (lookup(messages, key) ?? "").toLowerCase();
        for (const phrase of NEGATED_DELETION[locale] ?? []) text = text.split(phrase).join(" ");
        for (const verb of destructive[locale] ?? []) {
          expect(text, `${locale}/${String(field)}`).not.toContain(verb);
        }
      }
    }
  });

  test("nothing on this sheet hurries the decision (§29.2)", () => {
    // Someone is looking at the record of a person who has died. There is no
    // version of urgency copy that belongs here.
    const forbidden = ["hurry", "last chance", "act now", "expires in", "before it's too late"];
    for (const locale of CATALOGS) {
      const messages = catalog(locale);
      const sentences = Object.values(MEMORIAL_COPY)
        .filter((value): value is string => typeof value === "string")
        .map((key) => (lookup(messages, key) ?? "").toLowerCase())
        .join(" ");
      for (const phrase of forbidden) expect(sentences, locale).not.toContain(phrase);
    }
  });
});

/**
 * §30.5's fourth scope, and the marker that says why no screen renders it.
 *
 * The pattern is the one `MEMORIAL_STATE_IS_UNBUILT` used before CC-012 built
 * it, and `tests/journal/test_search_provenance.py` uses for the Atlas index:
 * an unbuilt thing is recorded in code with a test, so it stays visible and so
 * the marker FAILS on the commit that makes it obsolete. A TODO would have been
 * read once and then never again.
 */
test.describe("§30.5 — the conversation deletion, and why it is not here", () => {
  test("its copy exists and is correct even though nothing renders it", () => {
    // The copy is not the missing part, and leaving it unwritten would have
    // meant the gap was invisible: a scope with no strings looks like a scope
    // nobody has got to, and a scope with correct strings and no screen looks
    // like exactly what it is.
    const en = catalog("en");
    for (const key of [
      SCOPE_COPY.conversation.titleKey,
      SCOPE_COPY.conversation.deletesKey,
      SCOPE_COPY.conversation.keepsKey,
      SCOPE_COPY.conversation.confirmKey,
    ]) {
      expect(lookup(en, key), key).toBeTruthy();
    }
  });

  test("no screen wires a confirm sheet to it while the marker stands", () => {
    // The failure this prevents is specific and tempting: wiring the sheet to
    // `POST /v1/memories/scoped/conversation-deleted`, which exists. That call
    // marks the memories' provenance destroyed and deletes no conversation, so
    // the sheet would promise a deletion, return 200, and quietly corrupt the
    // provenance of memories she chose to keep.
    expect(CONVERSATION_DELETE_IS_UNBUILT.scope).toBe("conversation");

    const appSrc = path.join(__dirname, "..", "src");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry.name)) continue;
        const text = readFileSync(full, "utf-8");
        // `ConfirmDeleteSheet`'s own `scope` prop already EXCLUDES
        // `family_member` at the type level; this catches the conversation one,
        // which is a valid `DeletionScope` and would typecheck happily.
        if (/scope=\{?"conversation"/.test(text)) {
          offenders.push(path.relative(appSrc, full));
        }
      }
    };
    walk(appSrc);

    expect(
      offenders,
      "a screen renders the conversation confirm — if the endpoint now exists, " +
        "delete CONVERSATION_DELETE_IS_UNBUILT and this test with it",
    ).toEqual([]);
  });
});

/**
 * Sentences that CONTAIN a destructive verb because they deny it.
 *
 * "Nothing is deleted" is the strongest line on the memorial sheet and it is
 * built from the word the guard above forbids. Same shape as the CC-008
 * disclosure guard, which had to learn that "she is NOT a real person" is the
 * correct sentence rather than a violation.
 */
const NEGATED_DELETION: Record<string, string[]> = {
  en: ["nothing is deleted", "nothing else changes", "nothing was ever taken"],
  hi: ["कुछ भी नहीं मिटता", "और कुछ नहीं बदलता", "कुछ कभी लिया ही नहीं गया"],
  "hi-Latn": ["kuch bhi nahin mitta", "aur kuch nahin badalta", "kuch kabhi liya hi nahin gaya"],
};
