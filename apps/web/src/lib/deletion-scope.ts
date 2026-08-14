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
