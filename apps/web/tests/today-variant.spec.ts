import { expect, test } from "@playwright/test";

import type { TodayState } from "@sitara/schemas";

import { MAX_BANNERS, resolveChrome } from "../src/lib/today-variant";

/**
 * §32.1's precedence rule, exercised where it actually breaks: the crowded
 * mornings.
 *
 * No server and no browser — the rule is pure over `TodayState`, which is the
 * whole reason it was written as its own module. A rule you can only observe by
 * arranging for four things to be true at once in a running app is a rule
 * nobody checks the fourth case of.
 */

function state(overrides: Partial<TodayState> = {}): TodayState {
  return {
    first_session: false,
    first_morning: false,
    brief_time: "07:00",
    travel: { active: false, city: null },
    festival: null,
    birthday: false,
    birth_time_missing: false,
    trial_day: null,
    plan: "premium",
    story_ring_enabled: false,
    ...overrides,
  };
}

const FESTIVAL = { name: "Raksha Bandhan", tradition_label: "Amanta", date_label: "2026-08-12" };

const chrome = (s: TodayState, localTime = "08:30", extra = {}) =>
  resolveChrome({ state: s, localTime, status: "ranking_only", ...extra });

test.describe("§32.1 — the banner stack", () => {
  test("holds at most two banners", () => {
    const c = chrome(
      state({
        plan: "grace",
        travel: { active: true, city: "London" },
        festival: FESTIVAL,
      }),
    );
    expect(c.banners.length).toBeLessThanOrEqual(MAX_BANNERS);
  });

  test("orders them as §32.1 declares: grace, then travel, then festival", () => {
    const c = chrome(
      state({ plan: "grace", travel: { active: true, city: "London" }, festival: FESTIVAL }),
    );
    expect(c.banners).toEqual(["payment_grace", "travel"]);
  });

  test("a festival squeezed out becomes the core-card accent, never nothing", () => {
    // §32.1: "suppressed if 2 banners already shown — festival then renders as
    // the core-card accent instead". The day's most visible fact does not
    // silently vanish because two other things happened.
    const c = chrome(
      state({ plan: "grace", travel: { active: true, city: "London" }, festival: FESTIVAL }),
    );
    expect(c.banners).not.toContain("festival");
    expect(c.festivalAccent).toBe(true);
  });

  test("a festival with room keeps its banner and takes no accent", () => {
    const c = chrome(state({ festival: FESTIVAL }));
    expect(c.banners).toContain("festival");
    expect(c.festivalAccent).toBe(false);
  });

  test("safety never co-renders with anything", () => {
    // "never co-renders" is stronger than "is first", and the difference is the
    // whole point: an L3+ takeover beside a trial pill would be a screen asking
    // someone in difficulty to think about their subscription.
    const c = chrome(
      state({
        plan: "grace",
        travel: { active: true, city: "London" },
        festival: FESTIVAL,
        trial_day: 5,
        birth_time_missing: true,
      }),
      "08:30",
      { safety: true },
    );
    expect(c.banners).toEqual(["safety"]);
    expect(c.trialPill).toBeNull();
    expect(c.birthTimeChip).toBe(false);
  });
});

test.describe("§32.1 — the pill and the chip", () => {
  test("the birth-time chip yields to ANY banner, not just a full stack", () => {
    const alone = chrome(state({ birth_time_missing: true }));
    expect(alone.birthTimeChip).toBe(true);

    const withOne = chrome(
      state({ birth_time_missing: true, travel: { active: true, city: "London" } }),
    );
    expect(withOne.banners).toHaveLength(1);
    expect(withOne.birthTimeChip).toBe(false);
  });

  test("the trial pill rides alongside banners — it is a pill, not a banner", () => {
    const c = chrome(state({ trial_day: 4, travel: { active: true, city: "London" } }));
    expect(c.banners).toEqual(["travel"]);
    expect(c.trialPill).toBe(4);
  });

  test("§32.1's worst case: grace + travel + festival + trial", () => {
    const c = chrome(
      state({
        plan: "grace",
        travel: { active: true, city: "London" },
        festival: FESTIVAL,
        trial_day: 6,
      }),
    );
    expect(c.banners).toEqual(["payment_grace", "travel"]);
    expect(c.festivalAccent).toBe(true);
    expect(c.trialPill).toBe(6);
    // Two banners + one pill, exactly the ceiling §32.1 names.
    expect(c.banners.length + (c.trialPill === null ? 0 : 1)).toBe(3);
  });
});

test.describe("§28.2 — the night takeover", () => {
  test("fires at 20:00 and not at 19:59", () => {
    expect(chrome(state(), "19:59").night).toBe(false);
    expect(chrome(state(), "20:00").night).toBe(true);
  });

  test("replaces the whole stack — except payment-grace", () => {
    const c = chrome(
      state({
        plan: "grace",
        travel: { active: true, city: "London" },
        festival: FESTIVAL,
        trial_day: 5,
      }),
      "21:15",
    );
    expect(c.banners).toEqual(["payment_grace"]);
    expect(c.trialPill).toBeNull();
  });

  test("a night with nothing owing has no banners at all", () => {
    const c = chrome(state({ travel: { active: true, city: "London" } }), "21:15");
    expect(c.banners).toEqual([]);
  });
});

test.describe("§28.2 — which variant this morning is", () => {
  test("offline wins over everything — it describes the payload's age", () => {
    const c = chrome(state({ festival: FESTIVAL, birthday: true }), "08:30", {
      offline: true,
    });
    expect(c.variant).toBe("offline");
  });

  test("a degraded brief is named degraded, whatever else is true", () => {
    const c = resolveChrome({
      state: state({ birthday: true }),
      localTime: "08:30",
      status: "verified_core_cards",
    });
    expect(c.variant).toBe("provider_degraded");
  });

  test("free locks the personal cards, and locking overrides density", () => {
    const c = chrome(state({ plan: "free" }));
    expect(c.variant).toBe("free");
    expect(c.locked).toBe(true);
  });

  test("premium shows no commercial UI at all", () => {
    const c = chrome(state({ plan: "premium" }));
    expect(c.locked).toBe(false);
    expect(c.trialPill).toBeNull();
    expect(c.banners).toEqual([]);
  });

  test("the plain time-of-day variants", () => {
    expect(chrome(state(), "08:30").variant).toBe("premium");
    expect(chrome(state({ plan: "trial", trial_day: null }), "14:20").variant).toBe("afternoon");
    expect(chrome(state({ plan: "trial", trial_day: null }), "18:10").variant).toBe("evening");
    expect(chrome(state({ plan: "trial", trial_day: null }), "21:15").variant).toBe("night");
  });
});
