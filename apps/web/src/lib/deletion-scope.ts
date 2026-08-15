/**
 * §30.5's deletion scopes, as the copy each confirm step must show.
 *
 * **The confirm copy is the feature.** §30.5 does not merely say deletions have
 * different consequences — it says the scope is "stated at confirm". A sheet
 * that promises the wrong blast radius is a defect a user finds only after it
 * is too late to undo, and it is invisible to every other kind of test: the
 * deletion works, the API returns 200, the row is gone, and the sentence she
 * read before tapping was false.
 *
 * So the four scopes live here as data, `tests/deletion-scope.spec.ts` asserts
 * what each one promises, and no screen writes its own version.
 *
 * Each scope names three things, because those are the three questions a person
 * actually has at that moment:
 *   · what goes      — `deletesKey`
 *   · what stays     — `keepsKey`
 *   · what she chooses — `checkboxKey`, where §30.5 offers one
 */

export const DELETION_SCOPES = [
  "memory",
  "journal_entry",
  "conversation",
  "family_member",
] as const;

export type DeletionScope = (typeof DELETION_SCOPES)[number];

export interface ScopeCopy {
  /** The sheet's title. */
  titleKey: string;
  /** What this deletion removes. Always present — every scope destroys something. */
  deletesKey: string;
  /**
   * What survives it. Always present too, and that is deliberate: §30.5's
   * scopes are distinguished by what they DO NOT touch, and a confirm sheet
   * that lists only the damage teaches a user that deletion is total.
   */
  keepsKey: string;
  /**
   * §30.5's checkbox, where one exists. Unticked by default at every call
   * site — the default IS the promise, and a default that drifts is a user
   * losing memories she chose to keep.
   */
  checkboxKey?: string;
  /** The destructive button. */
  confirmKey: string;
  /**
   * True where the deletion cannot be undone by any path in the product.
   * Drives the confirm's tone, never a countdown or a guilt line (§29.2).
   */
  irreversible: boolean;
}

export const SCOPE_COPY: Record<DeletionScope, ScopeCopy> = {
  /**
   * §30.5: "delete a memory → Tara stops knowing it (past journal text
   * unchanged, stated at confirm)". Both halves are in the copy, because the
   * second half is the one she cannot guess.
   */
  memory: {
    titleKey: "vault.delete.title",
    deletesKey: "vault.delete.deletes",
    keepsKey: "vault.delete.keeps",
    confirmKey: "vault.delete.confirm",
    irreversible: true,
  },

  /**
   * §30.5: "delete a journal entry → artefact removed (memories sourced from
   * it survive unless also deleted — offered as a checkbox)".
   */
  journal_entry: {
    titleKey: "journal.delete.title",
    deletesKey: "journal.delete.deletes",
    keepsKey: "journal.delete.keeps",
    checkboxKey: "journal.delete.also_memories",
    confirmKey: "journal.delete.confirm",
    irreversible: true,
  },

  /**
   * §30.5: "delete a conversation → §27 chat rules + dependent memory sources
   * marked 'source removed'". The memories SURVIVE, and saying so is the
   * whole point — this is the scope a user is most likely to assume is
   * total.
   */
  conversation: {
    titleKey: "chat.delete.title",
    deletesKey: "chat.delete.deletes",
    keepsKey: "chat.delete.keeps",
    confirmKey: "chat.delete.confirm",
    irreversible: true,
  },

  /**
   * §32.15. The widest radius and the only one whose checkbox comes with a
   * LIST — "about them" is a name match, so the candidates are shown and she
   * ticks what she means.
   */
  family_member: {
    titleKey: "family.delete.title",
    deletesKey: "family.delete.deletes",
    keepsKey: "family.delete.keeps",
    checkboxKey: "family.delete.also_memories",
    confirmKey: "family.delete.confirm",
    irreversible: true,
  },
};

/**
 * ── §45's alternative, on the same sheet (CC-012) ──────────────────────────
 *
 * §32.15 offers "in memory of" as the alternative to deletion, and §45.3 puts
 * both on ONE sheet with the non-destructive one first. So the memorial copy
 * lives beside the scopes rather than in a screen: it is read at the same
 * moment, by the same person, and the two promises have to be told apart.
 *
 * **The discipline here is inverted, and that is the whole point.** For a
 * deletion, the dangerous drift is a sheet that promises less damage than it
 * does. For this one it is the opposite: a conversion that quietly removed
 * something would be a bereaved user losing her mother's chart because she
 * chose the gentle option. So this copy states what SURVIVES first, states the
 * one thing that changes explicitly (§45.2's reminders — a sheet that said
 * "nothing changes" would be lying by a different route), and says it is
 * reversible, because §45.2 makes it so and a wrong tap that week must not be
 * another loss.
 */
export interface MemorialCopy {
  /** The shared sheet's title. Neutral — §45.3 will not let it presume the
   *  destructive branch, which is the one presented SECOND. */
  sheetTitleKey: string;
  /** The non-destructive block's heading. */
  titleKey: string;
  /** What the conversion does. */
  bodyKey: string;
  /** What survives it: everything. Stated, never implied. */
  keepsKey: string;
  /** §45.2's single behavioural change — the reminders soften. */
  remindersKey: string;
  confirmKey: string;
  /** §45.2: reversible, and the sheet says so. */
  reversibleKey: string;
  /** The list/detail marker for a member already `in_memory`. */
  badgeKey: string;
  /** The same sheet, seen by someone undoing it. */
  revertTitleKey: string;
  revertBodyKey: string;
  revertKey: string;
  /** The bridge to §32.15's destructive half, below it (§45.3). */
  orDeleteKey: string;
  /**
   * True, and asserted against every scope's `irreversible`. The pair is the
   * property: one of these four sheets is a door that does not open again and
   * this one is not, and a screen must never present them as the same weight.
   */
  reversible: boolean;
}

export const MEMORIAL_COPY: MemorialCopy = {
  sheetTitleKey: "family.memorial.sheet_title",
  titleKey: "family.memorial.title",
  bodyKey: "family.memorial.body",
  keepsKey: "family.memorial.keeps",
  remindersKey: "family.memorial.reminders",
  confirmKey: "family.memorial.confirm",
  reversibleKey: "family.memorial.reversible",
  badgeKey: "family.memorial.badge",
  revertTitleKey: "family.memorial.revert_title",
  revertBodyKey: "family.memorial.revert_body",
  revertKey: "family.memorial.revert",
  orDeleteKey: "family.memorial.or",
  reversible: true,
};

/**
 * §45.3: "The two are offered together on one sheet, and the non-destructive
 * one is presented first." An ORDER rather than a comment, so the sheet reads
 * it instead of a reviewer remembering it.
 */
export const FAMILY_SHEET_ORDER = ["memorial", "delete"] as const;
export type FamilySheetSection = (typeof FAMILY_SHEET_ORDER)[number];

/**
 * The memorial keys that make a PROMISE about what survives.
 *
 * Separated from `orDeleteKey`, which bridges to §32.15's destructive half and
 * therefore says "remove" on purpose. Everything in this list is a sentence
 * about the gentle option, and `tests/deletion-scope.spec.ts` asserts no
 * destructive verb appears in any of them in any locale — the failure being
 * someone drafting this block by editing a copy of `family.delete.*`.
 */
export const MEMORIAL_PROMISE_KEYS: readonly (keyof MemorialCopy)[] = [
  "bodyKey",
  "keepsKey",
  "remindersKey",
  "confirmKey",
  "reversibleKey",
  "revertBodyKey",
];

/**
 * ── §30.5's conversation deletion is NOT BUILT, and this is the record ─────
 *
 * Three of the four scopes above have a screen in M10. The conversation scope
 * does not, and the reason is not that it was skipped:
 *
 * **The API has the CONSEQUENCE and not the ACT.**
 * `POST /v1/memories/scoped/conversation-deleted` exists and does exactly what
 * §30.5 requires — marks dependent memory sources "source removed", leaves the
 * memories themselves alone. There is no endpoint anywhere in `sitara_api` that
 * deletes a conversation. `chat_orchestration/router.py` serves `/turn`,
 * `/session`, `/ws/redeem`, `/ws/turn` and `/ws/voice-note`; nothing else.
 *
 * So a confirm sheet for it could only have been wired to an endpoint that does
 * not exist, or to the scoped-effects call alone — which would mark the
 * memories' provenance destroyed while the conversation it named stayed exactly
 * where it was. That is worse than the gap: the sheet would promise a deletion,
 * return 200, and silently corrupt the provenance of memories she kept.
 *
 * The copy is written, asserted and correct (see `tests/deletion-scope.spec.ts`)
 * — §28.3's one-history also makes this an account-level act rather than a
 * per-thread one, so its eventual home is S36 `/you/privacy`, not a chat
 * overflow menu.
 *
 * This marker is the shape `MEMORIAL_STATE_IS_UNBUILT` used before CC-012 built
 * it: a declared falsehood-free record, with a test that fails on the commit
 * that makes it obsolete.
 */
export const CONVERSATION_DELETE_IS_UNBUILT = {
  scope: "conversation" as const,
  /** What is missing, named precisely enough to close. */
  missing: "an endpoint that deletes a conversation",
  /** What DOES exist, so nobody re-derives this from scratch. */
  present: "POST /v1/memories/scoped/conversation-deleted (the consequence only)",
  /** Where it belongs when it is built. */
  home: "S36 /you/privacy (§28.3: one history, so this is an account-level act)",
} as const;

/**
 * Which scopes offer §30.5's checkbox. Derived rather than listed, so adding
 * a `checkboxKey` cannot leave a screen that never renders one.
 */
export function offersMemoryCheckbox(scope: DeletionScope): boolean {
  return SCOPE_COPY[scope].checkboxKey !== undefined;
}

/**
 * The checkbox's default, stated as a function rather than a literal at each
 * call site.
 *
 * §30.5 and §32.15 both make KEEPING the default. It is false everywhere and
 * always, and the one place it is decided is here.
 */
export function memoryCheckboxDefault(): boolean {
  return false;
}
