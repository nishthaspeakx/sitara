/**
 * A stand-in for `sitara-api`, spoken to over HTTP exactly as the real one is.
 *
 * ── Why this exists ────────────────────────────────────────────────────────
 *
 * The flow suite used to install `page.route("**\/v1/onboarding", …)`, which
 * intercepts in the BROWSER. The request never left, so the Next server never
 * saw it — and neither did the locale middleware or the `/v1` rewrite. The
 * suite was checking that the client handles a response the test invented, and
 * had never once checked the URL that produces it.
 *
 * That is how every onboarding step could 404 in a real browser while the whole
 * flow suite was green: next-intl's middleware did not exclude `v1`, so it
 * 307'd `/v1/onboarding` to `/hi/v1/onboarding`, which matches no rewrite and
 * no page. A browser-level intercept can never see that, because the redirect
 * happens on the server the intercept prevented the request from reaching.
 *
 * So the requests now travel the real path:
 *
 *     browser → next start (:3100) → middleware → rewrite → this server
 *
 * Anything that breaks the prefix, the proxy, the origin or the locale handling
 * now fails a test instead of only failing a user.
 *
 * ── State ──────────────────────────────────────────────────────────────────
 *
 * Per-client, keyed by the `sitara_test_client` cookie the test sets on the app
 * origin — Next's rewrite forwards cookies, so the stub can tell parallel
 * workers apart. The control plane is `/__control/*`, called by the test
 * process directly on this port, never through the app.
 *
 * Dependency-free Node, like `serve-static.mjs`, so a CI run installs nothing.
 */

import { createServer } from "node:http";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const port = Number(process.argv[2] ?? 3101);

/**
 * ── `/v1/today` is REPLAYED, never authored here ───────────────────────────
 *
 * Everything this file serves for onboarding is a small state machine, because
 * §24.4's per-step persistence is what those tests are about. A morning brief
 * is the opposite: its content is the OUTPUT of §7.1's pipeline — the ranking
 * engine picking from the closed seventeen, the composer citing the snapshot
 * each slot came from, the degradation ladder choosing between four outcomes.
 * A hand-written brief in this file would be a brief nobody's engine produced,
 * and every §24.8 baseline taken from it would be a picture of fiction.
 *
 * So the payloads are RECORDED from the real service by
 * `services/api/scripts/record_today_fixtures.py` and committed under
 * `tests/__fixtures__/today/`. This server only picks the right one and hands
 * it over the wire, through the real request path. `tests/today-fixtures.spec.ts`
 * re-validates every recording against the generated schema, so one cannot
 * quietly drift into something the engine would never emit.
 */
const FIXTURE_DIR = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "tests",
  "__fixtures__",
  "today",
);

/** @type {Map<string, object>} keyed `${variant}.${locale}` */
const todayFixtures = new Map();
try {
  for (const file of readdirSync(FIXTURE_DIR)) {
    if (!file.endsWith(".json")) continue;
    todayFixtures.set(file.slice(0, -".json".length), JSON.parse(
      readFileSync(path.join(FIXTURE_DIR, file), "utf-8"),
    ));
  }
} catch {
  // Recorded fixtures are a build artefact of the API. A run before the first
  // recording should fail the Today specs loudly, not every other suite.
  console.warn(`[stub-api] no today fixtures at ${FIXTURE_DIR}`);
}

/**
 * §25.4's chat turns, recorded by `services/api/scripts/record_chat_fixtures.py`
 * for the same reason the briefs are: a turn carries CITATION SPANS the
 * grounding validator computed, and hand-written spans would render an
 * underline over words nobody verified.
 *
 * `stub-realtime.mjs` replays these over the socket; this file replays them
 * over `POST /v1/chat/turn`, which is §32.11's handoff path — the same
 * `ChatTurn` on both transports, which is the property worth having.
 */
const CHAT_FIXTURE_DIR = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "tests",
  "__fixtures__",
  "chat",
);

/** @type {Map<string, object>} keyed `${scenario}.${locale}` */
const chatFixtures = new Map();
try {
  for (const file of readdirSync(CHAT_FIXTURE_DIR)) {
    if (!file.endsWith(".json")) continue;
    chatFixtures.set(file.slice(0, -".json".length), JSON.parse(
      readFileSync(path.join(CHAT_FIXTURE_DIR, file), "utf-8"),
    ));
  }
} catch {
  console.warn(`[stub-api] no chat fixtures at ${CHAT_FIXTURE_DIR}`);
}

/** Where `POST /v1/chat/session` points the browser. Set by the runner. */
const REALTIME_WS_URL = process.env.STUB_REALTIME_WS_URL ?? "ws://127.0.0.1:3102/chat/session";

/**
 * Where `POST /v1/call/session` points the browser (§25.3, M9-P10b). A SEPARATE
 * path from the chat one, because the real config has two — §6.1 scales and
 * sticky-routes a minutes-long duplex call independently of bursts of text.
 */
const REALTIME_CALL_WS_URL =
  process.env.STUB_REALTIME_CALL_WS_URL ?? "ws://127.0.0.1:3102/call/session";

/** @type {Map<string, {state: object, scenario: string}>} */
const clients = new Map();

const PLACES = [
  { id: "bengaluru", label: "Bengaluru", lat: 12.97, lon: 77.59, tz: "Asia/Kolkata" },
  { id: "mumbai", label: "Mumbai", lat: 19.08, lon: 72.88, tz: "Asia/Kolkata" },
  { id: "london", label: "London", lat: 51.51, lon: -0.13, tz: "Europe/London" },
];

/**
 * Term names as the real composer renders them — `reading.compose` fills every
 * slot through `localised_term`. A stub answering "Rohini" in Hindi would bake
 * English-inside-Devanagari into the §24.8 baselines.
 */
const TERMS = {
  en: { nakshatra: "Rohini", graha: "Venus", paksha: "Shukla paksha" },
  hi: { nakshatra: "रोहिणी", graha: "शुक्र", paksha: "शुक्ल पक्ष" },
  "hi-Latn": { nakshatra: "Rohini", graha: "Shukra", paksha: "Shukla paksha" },
};

function emptyState(locale = "en") {
  return {
    locale,
    completed_steps: [],
    has_birth_details: false,
    time_accuracy: null,
    has_city: false,
    interest: null,
    priorities: [],
    display_name: null,
    brief_time: null,
    voice_enabled: true,
    // Set by `POST /auth/session` — the §34.5 exchange is what mints identity,
    // and nothing under /v1 is reachable before it.
    session_user_id: null,
  };
}

/** The stack is linear (§28.1): next = the lowest step not yet done. */
function nextStep(completed) {
  for (let step = 2; step <= 13; step += 1) if (!completed.includes(step)) return step;
  return 13;
}

function reading(locale, scenario) {
  const terms = TERMS[locale] ?? TERMS.en;
  const lines = [
    {
      id: "moon_nakshatra",
      values: { nakshatra: terms.nakshatra },
      fact_ids: ["natal.graha.nakshatra:moon:v1"],
      confidence: "verified",
      house: null,
    },
    {
      id: "observation",
      house: 7,
      values: { graha: terms.graha },
      fact_ids: ["natal.house_assignment:venus:v1"],
      confidence: "verified",
    },
    {
      id: "panchang",
      values: { tithi: "5", paksha: terms.paksha },
      fact_ids: ["panchang.tithi:2026-08-12:bengaluru"],
      confidence: "verified",
      house: null,
    },
  ];
  const base = {
    status: "complete",
    confidence: "verified",
    source_state: "default",
    lines,
    facts: [],
    missing: [],
    degrade_reason: null,
  };

  switch (scenario) {
    case "reading_no_birth_time":
      return {
        ...base,
        status: "partial",
        confidence: "approximate",
        source_state: "single",
        missing: ["birth_time"],
        degrade_reason: "insufficient_birth_data",
        // §5.3: no lagna-sensitive claim survives a missing birth time.
        lines: lines.filter((l) => l.id !== "observation"),
      };
    case "reading_engine_down_then_panchang":
      return {
        ...base,
        status: "partial",
        confidence: "tradition_based_general",
        source_state: "single",
        missing: ["natal_chart"],
        degrade_reason: "engine_unavailable",
        lines: lines.filter((l) => l.id === "panchang"),
      };
    case "reading_no_panchang":
      return {
        ...base,
        status: "partial",
        confidence: "verified_limited_birth_data",
        source_state: "single",
        missing: ["panchang"],
        degrade_reason: "panchang_unavailable",
        lines: lines.filter((l) => l.id !== "panchang"),
      };
    default:
      return base;
  }
}

/**
 * ── M10's records: §30.5's Journal, §32.4's Vault, §32.15's family ─────────
 *
 * **Seeded, not recorded, and the line between the two is not arbitrary.**
 *
 * The briefs and the chat turns above are replayed from the real pipeline
 * because their CONTENT is an engine output — a hand-written brief is a brief
 * nobody's ranking engine produced, and every baseline taken from it is a
 * picture of fiction. A journal day, a vault row and a family member are the
 * opposite: they are the user's own records, and their content is whatever she
 * put there. Recording them would record a fixture author's imagination with
 * extra steps.
 *
 * What has to be right about them is their SHAPE and their RELATIONSHIPS, so
 * this is a state machine over linked records — the same thing the onboarding
 * stub is over steps, and for the same reason: §30.5's deletions are defined by
 * what they do to the links.
 *
 * The links are seeded deliberately, because they are what the §30.5 confirm
 * tests act on:
 *   · the `preference` memory was learned from the turn the saved-guidance
 *     entry points at, so that entry's checkbox has something real to delete;
 *   · the `anniversary` memory contains the mother's NAME, so §32.15's
 *     candidate list is a real name match rather than a hard-coded row;
 *   · the `practice` memory is sourced from nothing either deletion touches, so
 *     "took only what it said it would" is provable rather than assumed.
 *
 * **Ids are ObjectId-shaped (24 hex chars).** §6.4 requires objectId and the
 * real routers parse every path id through `ObjectId(...)`, refusing anything
 * else. An M5 in-memory store took string ids where the real one would not, so
 * every real write failed validation while the whole suite stayed green — the
 * root CLAUDE.md rule, in the place it was broken. A stub that accepted
 * `"m1"` here would be the same defect.
 */

const TODAY = "2026-08-15";

/**
 * §30.3's subscription states, one per S30/S34 baseline.
 *
 * Seeded rather than recorded, for the reason M10's records are: a
 * subscription is a state machine over the USER's own account, so what has to
 * be right is its SHAPE and the relationships between its dates — not an
 * engine's output. The dates are fixed relative to `TODAY` so a baseline never
 * depends on when the suite ran.
 *
 * The §22.13 dates are SERVER-COMPUTED in the real API (`lifecycle.project`),
 * so they are given here rather than derived by the screen — a stub that made
 * the screen compute them would let a client-side reimplementation of §22.13
 * pass every baseline.
 */
const SUB_PRICES = {
  india: [
    { plan: "monthly", region: "india", amount_minor: 49900, currency: "INR",
      total_with_tax_minor: 49900, term_days: 30, founding: false },
    { plan: "annual", region: "india", amount_minor: 399900, currency: "INR",
      total_with_tax_minor: 399900, term_days: 365, founding: false },
  ],
  international: [
    { plan: "monthly", region: "international", amount_minor: 1299, currency: "USD",
      total_with_tax_minor: 1299, term_days: 30, founding: false },
    { plan: "annual", region: "international", amount_minor: 9900, currency: "USD",
      total_with_tax_minor: 9900, term_days: 365, founding: false },
  ],
};

function subscriptionFor(scenario) {
  const base = {
    status: null, plan: null, region: "india",
    renewal_failed_at: null, grace_ends_at: null, downgrades_at: null,
    period_start: null, period_end: null,
    price_minor: null, currency: null,
    mandate_retry_required: false, founding: false, retains_history: true,
    // Every S30 baseline shows the prototype disclosure, because every one of
    // them IS the prototype. A stub that hid it would baseline a screen the
    // build cannot produce.
    simulated: true, region_switch_offered: false,
    prices: SUB_PRICES.india, purchasable: true,
  };
  const active = {
    ...base, status: "active", plan: "annual",
    period_start: "2026-08-01T00:00:00Z", period_end: "2027-08-01T00:00:00Z",
    price_minor: 399900, currency: "INR",
  };
  switch (scenario) {
    case "sub_none":
      return base;
    case "sub_unavailable":
      // §30.3's gap: no rail serves this region. No CTA renders at all.
      return { ...base, purchasable: false };
    case "sub_trialing":
      return { ...active, status: "trialing", plan: "trial",
               period_end: "2026-08-22T00:00:00Z", price_minor: null, currency: null };
    case "sub_grace":
      // §22.13 day 2 of 7. FULL access throughout — the copy says so.
      // `period_end` EQUALS `renewal_failed_at`: a renewal is attempted at the
      // end of the period it renews, and `lifecycle.fail_renewal` leaves
      // `period_end` alone. Dating them apart produced a screen saying
      // "renews on 1 August 2027" above "this month's payment didn't go
      // through" — a state the real service cannot produce.
      return { ...active, status: "grace",
               period_start: "2025-08-13T00:00:00Z",
               period_end: "2026-08-13T00:00:00Z",
               renewal_failed_at: "2026-08-13T00:00:00Z",
               grace_ends_at: "2026-08-20T00:00:00Z",
               downgrades_at: "2026-09-10T00:00:00Z" };
    case "sub_read_only":
      return { ...active, status: "read_only",
               period_start: "2025-08-01T00:00:00Z",
               period_end: "2026-08-01T00:00:00Z",
               renewal_failed_at: "2026-08-01T00:00:00Z",
               grace_ends_at: "2026-08-08T00:00:00Z",
               downgrades_at: "2026-08-29T00:00:00Z" };
    case "sub_downgraded":
      return { ...active, status: "downgraded",
               period_start: "2025-07-01T00:00:00Z",
               period_end: "2026-07-01T00:00:00Z",
               renewal_failed_at: "2026-07-01T00:00:00Z",
               grace_ends_at: "2026-07-08T00:00:00Z",
               downgrades_at: "2026-07-29T00:00:00Z" };
    case "sub_cancelled":
      return { ...active, status: "cancelled" };
    case "sub_mandate":
      // §30.3 — active on the paid period; only the standing instruction failed.
      return { ...active, mandate_retry_required: true };
    case "sub_region_switch":
      // §30.3's migration, offered AT renewal. The subscription is still ₹.
      return { ...active, region_switch_offered: true };
    case "sub_founding":
      return { ...active, founding: true, price_minor: 299900 };
    case "pay_pending":
      // §30.3's hold: the purchase is in flight and nothing is granted yet.
      // The default arm returns an ACTIVE subscription, which paired a
      // "waiting for your bank" screen with an account that already had
      // everything — a combination the real service cannot produce, and one
      // that made S34's pending baseline offer a way back it should not have.
      return { ...base, status: "pending", plan: "annual",
               period_start: "2026-08-15T00:00:00Z", period_end: "2026-08-15T00:00:00Z",
               price_minor: 399900, currency: "INR" };
    case "sub_international":
      return { ...active, region: "international", price_minor: 9900,
               currency: "USD", prices: SUB_PRICES.international };
    default:
      return active;
  }
}


/**
 * Record content per locale.
 *
 * A journal preview and a memory are things a Hindi user reads in Hindi. A stub
 * serving English here would put English inside every Devanagari baseline and
 * §2.4's "no silent English fallback" would be violated by the fixture rather
 * than by the app — which is worse, because it looks like data.
 */
const RECORDS_TEXT = {
  en: {
    brief: "Work themes rise today — the Moon moves through your tenth house.",
    reflection: "You wrote about the week finally settling.",
    guidance: "Keep the difficult conversation for Thursday morning.",
    call: "Six minutes about the move, and what your mother would have said.",
    milestone: "Your first reading with Tara.",
    anniversary: "Sudha's birthday is 11 March",
    mother_name: "Sudha",
    son_name: "Arjun",
    preference: "Prefers her brief at 6:30, before the house wakes",
    practice: "Fasts on Tuesdays",
  },
  hi: {
    brief: "आज कार्य के विषय उभरते हैं — चंद्रमा आपके दशम भाव से गुजर रहे हैं।",
    reflection: "आपने लिखा कि सप्ताह आख़िरकार ठहर रहा है।",
    guidance: "वह कठिन बातचीत गुरुवार सुबह के लिए रखें।",
    call: "छह मिनट, उस बदलाव के बारे में — और उस पर जो आपकी माँ कहतीं।",
    milestone: "तारा के साथ आपका पहला पाठ।",
    anniversary: "सुधा का जन्मदिन 11 मार्च है",
    mother_name: "सुधा",
    son_name: "अर्जुन",
    preference: "सुबह 6:30 पर ब्रीफ़ पसंद है, घर के जागने से पहले",
    practice: "मंगलवार को व्रत रखती हैं",
  },
  "hi-Latn": {
    brief: "Aaj kaam ke vishay ubharte hain — Chandrama aapke dasham bhaav se guzar rahe hain.",
    reflection: "Aapne likha ki hafta aakhirkar thehar raha hai.",
    guidance: "Woh mushkil baatcheet Guruvaar subah ke liye rakhein.",
    call: "Chhah minute, us badlaav ke baare mein — aur us par jo aapki maa kehtin.",
    milestone: "Tara ke saath aapka pehla paath.",
    anniversary: "Sudha ka janmdin 11 March hai",
    mother_name: "Sudha",
    son_name: "Arjun",
    preference: "Subah 6:30 par brief pasand hai, ghar ke jaagne se pehle",
    practice: "Mangalvaar ko vrat rakhti hain",
  },
};

function seedRecords(locale) {
  const text = RECORDS_TEXT[locale] ?? RECORDS_TEXT.en;
  const mother = "6f10000000000000000000f1";
  const son = "6f10000000000000000000f2";
  const msg = {
    anniversary: "6c10000000000000000000b1",
    preference: "6c10000000000000000000b2",
    practice: "6c10000000000000000000b3",
  };

  return {
    /** §32.4's vault rows. No embedding — that is derived data (§32.5). */
    memories: [
      {
        memory_id: "6b10000000000000000000a1",
        type: "date_anniversary",
        content: text.anniversary,
        consent_granted_at: "2026-06-02T09:14:00Z",
        wording_reconfirmed: false,
        muted: false,
        source_state: "present",
        decay_score: 1,
        created_at: "2026-06-02T09:14:00Z",
        source_message_id: msg.anniversary,
      },
      {
        memory_id: "6b10000000000000000000a2",
        type: "preference",
        content: text.preference,
        consent_granted_at: "2026-07-19T04:02:00Z",
        wording_reconfirmed: false,
        muted: false,
        source_state: "present",
        decay_score: 0.72,
        created_at: "2026-07-19T04:02:00Z",
        source_message_id: msg.preference,
      },
      {
        memory_id: "6b10000000000000000000a3",
        type: "spiritual_practice",
        content: text.practice,
        consent_granted_at: "2026-05-11T16:40:00Z",
        wording_reconfirmed: false,
        muted: false,
        source_state: "present",
        decay_score: 1,
        created_at: "2026-05-11T16:40:00Z",
        source_message_id: msg.practice,
      },
    ],

    /**
     * §30.5's timeline. A DAY is the unit and an entry points at an artefact
     * that lives elsewhere — the Journal keeps no copy (§44.2), so `preview` is
     * rendered from the source and `null` where the source is gone.
     */
    journal: [
      {
        local_date: TODAY,
        entries: [
          {
            artefact_type: "brief",
            ref: `brief:${TODAY}`,
            local_date: TODAY,
            saved: false,
            save_id: null,
            note: null,
            preview: text.brief,
            message_id: null,
            conversation_id: null,
            confidence: "verified",
            occurred_at: `${TODAY}T01:30:00Z`,
          },
        ],
      },
      {
        local_date: "2026-08-14",
        entries: [
          {
            artefact_type: "reflection",
            ref: "reflection:2026-08-14",
            local_date: "2026-08-14",
            saved: false,
            save_id: null,
            note: null,
            preview: text.reflection,
            message_id: null,
            conversation_id: null,
            confidence: null,
            occurred_at: "2026-08-14T16:05:00Z",
          },
          {
            artefact_type: "guidance",
            ref: "guidance:6d10000000000000000000c1",
            local_date: "2026-08-14",
            saved: true,
            save_id: "6d10000000000000000000c1",
            note: null,
            preview: text.guidance,
            message_id: msg.preference,
            conversation_id: "6a90000000000000000000e1",
            confidence: "verified",
            occurred_at: "2026-08-14T11:22:00Z",
          },
        ],
      },
      {
        local_date: "2026-08-12",
        entries: [
          {
            artefact_type: "call",
            ref: "call:6e10000000000000000000d1",
            local_date: "2026-08-12",
            saved: false,
            save_id: null,
            note: null,
            preview: text.call,
            message_id: null,
            conversation_id: "6a90000000000000000000e1",
            confidence: null,
            occurred_at: "2026-08-12T13:40:00Z",
          },
          {
            artefact_type: "milestone",
            ref: "milestone:first_reading",
            local_date: "2026-08-12",
            saved: false,
            save_id: null,
            note: null,
            preview: text.milestone,
            message_id: null,
            conversation_id: null,
            confidence: null,
            occurred_at: "2026-08-12T06:02:00Z",
          },
        ],
      },
    ],

    family: [
      {
        member_id: mother,
        relation: "mother",
        name: text.mother_name,
        language_tag: "hi",
        has_birth_details: true,
        attested: true,
        memorial_state: "living",
        created_at: "2026-05-30T10:00:00Z",
      },
      {
        member_id: son,
        relation: "son",
        name: text.son_name,
        language_tag: "en",
        has_birth_details: false,
        attested: false,
        memorial_state: "living",
        created_at: "2026-06-14T10:00:00Z",
      },
    ],

    /**
     * The collections §32.15 hard-deletes, counted. Not served by any product
     * route — they exist so a test can assert a chart is GONE rather than
     * merely unreachable, and so the memorial conversion can be proved to have
     * touched neither.
     */
    birth_details: { [mother]: 1, [son]: 0 },
    charts: { [mother]: 3, [son]: 0 },
    /**
     * §32.15's DPDP clause: the attestation is REVOKED, never deleted. The
     * consent is a fact about the account-holder; the birth details were a fact
     * about someone else.
     */
    attestations: { [mother]: "granted", [son]: "none" },

    /** §27 binds a reflection to the user's local calendar day at creation. */
    reflections: {},
  };
}

/** The same client with nothing in it — §24.6's designed empty states. */
function emptyRecords() {
  return {
    memories: [],
    journal: [],
    family: [],
    birth_details: {},
    charts: {},
    attestations: {},
    reflections: {},
  };
}

/**
 * ── The views, and what they deliberately do NOT carry ────────────────────
 *
 * Each of these mirrors a Pydantic view model in `sitara_api`, and the fields
 * they drop matter more than the ones they keep:
 *
 * · `memoryView` drops `source_message_id`. The real `MemoryView` has no such
 *   field — §32.5's embedding and the provenance pointer are both internal —
 *   so a client that used it would be built on data the real API never sends.
 * · `entryView` drops nothing the real `EntryView` has, and adds nothing. In
 *   particular there is no `message_ids` array: the real one carries a single
 *   `message_id`, and §30.5's checkbox is the CLIENT deriving the source turns
 *   from it. A stub that handed over a ready-made list would let a screen ship
 *   that could never work against `sitara_api`.
 */
function memoryView(memory) {
  return {
    memory_id: memory.memory_id,
    type: memory.type,
    content: memory.content,
    consent_granted_at: memory.consent_granted_at,
    wording_reconfirmed: memory.wording_reconfirmed,
    muted: memory.muted,
    source_state: memory.source_state,
    decay_score: memory.decay_score,
    created_at: memory.created_at,
  };
}

function entryView(entry) {
  return {
    artefact_type: entry.artefact_type,
    ref: entry.ref,
    local_date: entry.local_date,
    saved: entry.saved,
    save_id: entry.save_id,
    note: entry.note,
    preview: entry.preview,
    message_id: entry.message_id,
    conversation_id: entry.conversation_id,
    confidence: entry.confidence,
    occurred_at: entry.occurred_at,
  };
}

function dayView(day) {
  return { local_date: day.local_date, entries: day.entries.map(entryView) };
}

function memberView(member) {
  return {
    member_id: member.member_id,
    relation: member.relation,
    name: member.name,
    language_tag: member.language_tag,
    has_birth_details: member.has_birth_details,
    // §13's attestation TIMESTAMP stays server-side; the client needs to know
    // only whether the gate is open.
    attested: member.attested,
    memorial_state: member.memorial_state,
    created_at: member.created_at,
  };
}

/** §10-17's three, in §27's order — served rather than hard-coded client-side. */
const PROMPT_ORDER = ["gratitude", "weight", "tomorrow"];

function emptyReflection(date, locale) {
  return {
    date,
    locale,
    entries: [],
    mood: null,
    memory_chips: [],
    prompt_order: PROMPT_ORDER,
    started: false,
  };
}

/**
 * One natal chart, as `astrology/router.py` serves it.
 *
 * Every placement is by GRAHA IDENTITY — that is the M6 lesson and the reason
 * `astrology/kundli.py` exists in the shape it does. The lagna is Simha, so
 * house 1 holds Simha and the rashis walk forward from there; the grahas are
 * spread so a positional client-side read would draw a visibly different chart
 * rather than a subtly wrong one.
 */
const RASHIS = [
  "mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
  "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena",
];

/**
 * House → grahas. Rahu in 3 and Ketu in 9, because they are always opposite —
 * a chart that lost that is wrong in a way every reader of a paper chart
 * notices instantly, and it is the sort of thing a generated fixture gets
 * wrong silently.
 */
const CHART_PLACEMENTS = {
  1: ["sun", "mercury"],
  3: ["rahu"],
  4: ["moon"],
  7: ["venus", "mars"],
  9: ["jupiter", "ketu"],
  10: ["saturn"],
};

const CHART = {
  houses: Array.from({ length: 12 }, (_, i) => ({
    house: i + 1,
    // Lagna in Simha (index 4), wrapping past the end of the zodiac.
    rashi: RASHIS[(4 + i) % 12],
    grahas: CHART_PLACEMENTS[i + 1] ?? [],
    is_lagna: i === 0,
  })),
  lagna_rashi: "simha",
  confidence: "verified",
  moon_chart: false,
  unplaced: [],
};

/** §34.4 — the only error shape that may leave a Sitara service. */
function envelope(code, messageKey, retryable) {
  return { code, message_key: messageKey, trace_id: "trace-stub", retryable };
}

function clientFor(req) {
  const cookie = req.headers.cookie ?? "";
  const match = /(?:^|;\s*)sitara_test_client=([^;]+)/.exec(cookie);
  const id = match ? decodeURIComponent(match[1]) : "default";
  if (!clients.has(id)) {
    clients.set(id, {
      state: emptyState(),
      scenario: "ok",
      today: { variant: "normal_morning", locale: "en" },
      records: seedRecords("en"),
    });
  }
  return clients.get(id);
}

function send(res, status, body) {
  const payload = body === null ? "" : JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (chunks.length === 0) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf-8"));
  } catch {
    return {};
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  const path = url.pathname;

  // ── control plane (test process → here, never through the app) ───────────
  if (path === "/__control/reset") {
    const body = await readJson(req);
    const id = body.clientId ?? "default";
    clients.set(id, {
      state: { ...emptyState(body.locale ?? "en"), ...(body.state ?? {}) },
      scenario: body.scenario ?? "ok",
      // Which recorded brief `/v1/today` replays for this client.
      id,
      // Which recorded turn `/v1/chat/turn` replays for this client.
      chat: {
        turn: body.chatTurn ?? "grounded",
        locale: body.locale ?? "en",
      },
      today: {
        variant: body.variant ?? "normal_morning",
        locale: body.locale ?? "en",
        // §28.2's densities are recorded for `normal_morning` only — density
        // changes the ranking engine's output COUNT, never its facts, so one
        // recording per density is the property worth replaying.
        density: body.density ?? "med",
      },
      // §30.5/§32.4/§32.15's records. `records_empty` is how §24.6's designed
      // empty states are reached — the same client with nothing in it, rather
      // than a second fixture that could drift from this one.
      records:
        (body.scenario ?? "ok") === "records_empty"
          ? emptyRecords()
          : seedRecords(body.locale ?? "en"),
    });
    return send(res, 200, { ok: true });
  }
  if (path === "/__control/state") {
    const id = url.searchParams.get("clientId") ?? "default";
    return send(res, 200, clients.get(id)?.state ?? null);
  }
  /**
   * The record state, for asserting what SURVIVED a deletion.
   *
   * This is not a product route and never will be: `birth_details`, `charts`
   * and `attestations` are counts of collections §32.15 acts on that no screen
   * may read. A §30.5 test that asserted only the DOM would pass against a
   * screen that hid a row it never deleted, and one that asserted only the
   * product API could not tell a revoked attestation from a deleted one — which
   * is the exact distinction §32.15's DPDP clause turns on.
   */
  if (path === "/__control/records") {
    const id = url.searchParams.get("clientId") ?? "default";
    return send(res, 200, clients.get(id)?.records ?? null);
  }
  if (path === "/healthz") return send(res, 200, { status: "ok", service: "stub-api" });

  const client = clientFor(req);
  const { scenario } = client;

  // A locale-prefixed API path is the defect this whole file exists to catch.
  // The real API would 404 it too; saying so loudly beats a silent 404.
  if (/^\/(en|hi|hi-Latn)\//.test(path)) {
    console.error(`[stub-api] locale-prefixed API path reached the server: ${path}`);
    return send(res, 404, envelope("SYS_VALIDATION", "errors.sys.validation", false));
  }

  // ── §34.5 ────────────────────────────────────────────────────────────────
  if (path === "/auth/session" && req.method === "POST") {
    const body = await readJson(req);
    if (body.locale) client.state.locale = body.locale;
    if (scenario === "auth_fails") {
      return send(res, 401, envelope("AUTH_INVALID_TOKEN", "errors.auth.invalid_token", false));
    }
    client.state.session_user_id = "6a70000000000000000000a1";
    return send(res, 200, {
      user_id: client.state.session_user_id,
      // The real router returns the locale it stored, and S02's choice arrives
      // HERE — it is the first authenticated moment in the stack.
      locale: client.state.locale,
      is_new_user: true,
    });
  }

  // ── §24.4 onboarding ─────────────────────────────────────────────────────
  //
  // **Every route below is behind a session, because the real one is.**
  //
  // `/v1/onboarding` sits behind `CurrentSession` in `sitara_api.onboarding`
  // (§33.2's product identity comes from the §34.5 cookie). This stub used to
  // answer 200 to anyone, and that single act of generosity hid a screen that
  // could not work: S02 runs BEFORE auth, so in a real browser every language
  // tap 401'd and onboarding was sealed at its first screen — while the whole
  // flow suite stayed green, because here the write always succeeded.
  //
  // That is the root CLAUDE.md rule, in the place it was broken: "a fake that
  // accepts what the real system rejects is a defect in the fake."
  const authed = client.state.session_user_id !== null;

  // ── §34.5's rotating refresh ──────────────────────────────────────────────
  //
  // The real API serves this and, until M10's live run, no client code called
  // it: the 15-minute access cookie expired and every screen rendered a fatal
  // error. `session_expires_once` is the scenario that proves the client now
  // recovers — the FIRST authenticated read 401s with AUTH_SESSION_EXPIRED, and
  // only a real POST here (with the refresh cookie, over the real request path)
  // clears it.
  if (path === "/auth/session/refresh" && req.method === "POST") {
    if (!authed) {
      return send(res, 401, envelope("AUTH_SESSION_EXPIRED", "errors.auth.session_expired", false));
    }
    client.accessSpent = false;
    return send(res, 200, { ok: true });
  }

  if (
    scenario === "session_expires_once" &&
    client.accessSpent !== false &&
    path.startsWith("/v1/")
  ) {
    // Spent exactly once: the retry after a successful refresh must succeed,
    // or the test would pass on a client that simply gave up quietly.
    client.accessSpent = false;
    return send(res, 401, envelope("AUTH_SESSION_EXPIRED", "errors.auth.session_expired", false));
  }

  const needsSession = path.startsWith("/v1/onboarding") || path === "/v1/readings/first";
  if (needsSession && !authed) {
    return send(res, 401, envelope("AUTH_INVALID_TOKEN", "errors.auth.invalid_token", false));
  }

  const withNext = () => ({ ...client.state, next_step: nextStep(client.state.completed_steps) });

  /** `fail_writes` makes every step's persist fail — §34.4 envelope, retryable. */
  const writeFails =
    scenario === "fail_writes" && req.method !== "GET" && path.startsWith("/v1/onboarding");
  if (writeFails) {
    return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
  }

  if (path === "/v1/onboarding" && req.method === "GET") return send(res, 200, withNext());

  if (path === "/v1/onboarding" && req.method === "PATCH") {
    const body = await readJson(req);
    const s = client.state;
    if (body.locale) s.locale = body.locale;
    if (body.interest) s.interest = body.interest;
    if (body.priorities) s.priorities = body.priorities;
    if (body.display_name) s.display_name = body.display_name;
    if (body.city) s.has_city = true;
    if (body.brief_time) s.brief_time = body.brief_time;
    if (typeof body.voice_enabled === "boolean") s.voice_enabled = body.voice_enabled;
    if (body.completed_step && !s.completed_steps.includes(body.completed_step)) {
      s.completed_steps.push(body.completed_step);
    }
    return send(res, 200, withNext());
  }

  if (path === "/v1/onboarding/consents" && req.method === "POST") {
    if (!client.state.completed_steps.includes(5)) client.state.completed_steps.push(5);
    return send(res, 200, withNext());
  }

  if (path === "/v1/onboarding/birth" && req.method === "PUT") {
    const body = await readJson(req);
    client.state.has_birth_details = true;
    client.state.time_accuracy = body.time_accuracy ?? null;
    if (!client.state.completed_steps.includes(7)) client.state.completed_steps.push(7);
    return send(res, 200, withNext());
  }

  if (path === "/v1/places") {
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    return send(res, 200, PLACES.filter((p) => p.label.toLowerCase().startsWith(q)));
  }

  // ── §25.4 / §34.6 chat ───────────────────────────────────────────────────
  if (path === "/v1/chat/session" && req.method === "POST") {
    if (scenario === "chat_unavailable") {
      return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
    }
    // The ticket is opaque to the browser and single-use at the far end. What
    // matters here is that `ws_url` is SERVED — the client compiles no socket
    // origin of its own, so the test can point it at a real stub process.
    const clientId = client.id ?? "default";
    return send(res, 200, {
      ticket: `ticket-${clientId}`,
      ws_url: `${REALTIME_WS_URL}?client=${encodeURIComponent(clientId)}`,
      resume_window_s: 300,
    });
  }

  // ── §25.3 / §34.6 call (M9-P10b) ─────────────────────────────────────────────
  if (path === "/v1/call/session" && req.method === "POST") {
    // Every reason a call must not happen is evaluated HERE, exactly as the
    // real API evaluates it — §33.5's flag, CC-010's locale ruling, §7.3's
    // pool. A stub that granted every call would be a fake that accepts what
    // the real system rejects, which is the root CLAUDE.md rule.
    if (scenario === "calls_disabled") {
      return send(
        res,
        503,
        envelope("VOICE_PROVIDER_UNAVAILABLE", "errors.voice.calls_not_enabled", false),
      );
    }
    const callBody = await readJson(req);
    if (callBody.locale && callBody.locale !== "en") {
      // CC-010: `hi`/`hi-Latn` streaming has no recogniser, and an English one
      // fed Hindi audio produces fluent nonsense rather than failing.
      return send(
        res,
        503,
        envelope(
          "VOICE_PROVIDER_UNAVAILABLE",
          "errors.voice.call_language_unavailable",
          false,
        ),
      );
    }
    if (scenario === "call_minutes_exhausted") {
      return send(
        res,
        402,
        envelope("VOICE_MINUTES_EXHAUSTED", "errors.voice.minutes_exhausted", false),
      );
    }
    const callClientId = client.id ?? "default";
    return send(res, 200, {
      ticket: `call-ticket-${callClientId}`,
      ws_url: `${REALTIME_CALL_WS_URL}?client=${encodeURIComponent(callClientId)}`,
      resume_window_s: 300,
      entitlement:
        scenario === "call_unlimited"
          ? { plan: "premium", unlimited: true, minutes_left: null, minutes_quota: null }
          : { plan: "monthly", unlimited: false, minutes_left: 6, minutes_quota: 300 },
      captions_default_on: scenario !== "call_returning",
    });
  }

  if (path === "/v1/chat/turn" && req.method === "POST") {
    // §32.11's handoff path. Deliberately the SAME recorded turn the socket
    // would have delivered: the whole point of one `ChatTurn` on both
    // transports is that a handoff is invisible in the thread's content.
    if (scenario === "chat_unavailable") {
      return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
    }
    const chat = client.chat ?? { turn: "grounded", locale: "en" };
    const fixture = chatFixtures.get(`${chat.turn}.${chat.locale}`);
    if (!fixture) {
      console.error(`[stub-api] no recorded turn for ${chat.turn}.${chat.locale}`);
      return send(res, 404, envelope("SYS_VALIDATION", "errors.sys.validation", false));
    }
    return send(res, 200, fixture);
  }

  // ── §28.2 Today ──────────────────────────────────────────────────────────
  // §30.3's S30/S31 payload. One GET; the mutations below return the state
  // the scenario already describes, because what these baselines test is how a
  // STATE renders — the transitions themselves are `tests/payments` in the API,
  // against the real §6.4 validators.
  if (path === "/v1/subscription" && req.method === "GET") {
    return send(res, 200, subscriptionFor(scenario));
  }
  if (path.startsWith("/v1/subscription/") && req.method === "POST") {
    if (path.endsWith("/purchase") || path.endsWith("/retry")) {
      if (scenario === "pay_pending") {
        return send(res, 200, {
          pending: true, checkout_url: null, failure_reason: null,
          provider_ref: "sim_pi_000001",
        });
      }
      if (scenario === "pay_failed") {
        return send(res, 200, {
          pending: false, checkout_url: null,
          failure_reason: "insufficient_funds", provider_ref: "sim_pi_000002",
        });
      }
      return send(res, 200, {
        pending: false, checkout_url: null, failure_reason: null,
        provider_ref: "sim_pi_000003",
      });
    }
    return send(res, 200, subscriptionFor(scenario));
  }

  if (path === "/v1/today" && req.method === "GET") {
    if (scenario === "today_unavailable") {
      // What the OFFLINE variant actually runs into. The screen falls back to
      // its cached payload; nothing here pretends to be a cache.
      return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
    }
    const { variant, locale, density } = client.today ?? {
      variant: "normal_morning",
      locale: "en",
      density: "med",
    };
    const name = density && density !== "med" ? `${variant}_${density}` : variant;
    const fixture = todayFixtures.get(`${name}.${locale}`);
    if (!fixture) {
      console.error(`[stub-api] no recorded brief for ${name}.${locale}`);
      return send(res, 404, envelope("SYS_VALIDATION", "errors.sys.validation", false));
    }
    return send(res, 200, fixture);
  }

  if (path === "/v1/readings/first" && req.method === "POST") {
    if (scenario === "reading_unavailable") {
      return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
    }
    if (scenario === "reading_engine_down_then_panchang" && !client.retried) {
      client.retried = true;
      return send(
        res,
        503,
        envelope("ASTRO_ENGINE_UNAVAILABLE", "errors.astro.engine_unavailable", true),
      );
    }
    if (scenario === "reading_slow") {
      await new Promise((r) => setTimeout(r, 700));
    }
    if (scenario === "reading_hangs") {
      return; // never responds — the case a server-side deadline cannot rescue
    }
    return send(res, 200, reading(client.state.locale, scenario));
  }

  // ── M10: §30.5 Journal · §32.4 Vault · §32.15 family · §27 reflection ────
  //
  // Every route below is behind the §34.5 session, because every one of them is
  // in the real API (`CurrentSession` on each router). A stub that served a
  // stranger's vault would be a fake accepting what the real system rejects.
  if (path.startsWith("/v1/journal") || path.startsWith("/v1/memories") ||
      path.startsWith("/v1/family") || path.startsWith("/v1/reflection") ||
      path === "/v1/chart") {
    if (!authed) {
      return send(res, 401, envelope("AUTH_INVALID_TOKEN", "errors.auth.invalid_token", false));
    }
    if (scenario === "records_unavailable") {
      return send(res, 503, envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true));
    }
  }

  const records = client.records ?? (client.records = seedRecords(client.state.locale ?? "en"));

  /**
   * The real routers parse every path id through `ObjectId(...)` and raise
   * SYS_VALIDATION on anything else. Refusing the same thing here is what stops
   * a screen from shipping a route that builds a malformed id and only fails in
   * production — the M5 lesson, applied to ids rather than to writes.
   */
  const objectId = (value) => /^[0-9a-f]{24}$/i.test(value);

  // ── §30.5 Journal (S21–S23) ──────────────────────────────────────────────

  if (path === "/v1/journal" && req.method === "GET") {
    const since = url.searchParams.get("since");
    const until = url.searchParams.get("until");
    const days = records.journal
      .filter((d) => (!since || d.local_date >= since) && (!until || d.local_date <= until))
      .sort((a, b) => b.local_date.localeCompare(a.local_date));
    return send(res, 200, days.map(dayView));
  }

  // BEFORE `/v1/journal/{date}`, exactly as the real router declares it. A
  // dynamic segment that swallowed `search` would make S23 a 400 on a date
  // parse — and the app router has the same trap one layer up.
  if (path === "/v1/journal/search" && req.method === "GET") {
    const q = (url.searchParams.get("q") ?? "").trim();
    if (!q) return send(res, 422, envelope("SYS_VALIDATION", "errors.sys.validation", false));
    const types = url.searchParams.getAll("type");
    const needle = q.toLowerCase();
    const hits = records.journal
      .slice()
      // §30.5's P0 contract is keyword + filters, NEWEST FIRST — deliberately
      // not a relevance score, because that is the contract an exact scan
      // satisfies exactly and the Atlas half is not built.
      .sort((a, b) => b.local_date.localeCompare(a.local_date))
      .flatMap((d) => d.entries)
      .filter((e) => (types.length === 0 || types.includes(e.artefact_type)))
      .filter((e) => (e.preview ?? "").toLowerCase().includes(needle))
      .map((e) => ({
        artefact_type: e.artefact_type,
        ref: e.ref,
        local_date: e.local_date,
        preview: e.preview,
        message_id: e.message_id,
        conversation_id: e.conversation_id,
      }));
    return send(res, 200, hits);
  }

  if (path.startsWith("/v1/journal/") && req.method === "GET") {
    const date = path.slice("/v1/journal/".length);
    const found = records.journal.find((d) => d.local_date === date);
    // §24.6: an empty day is a DAY, never a 404. The Journal opens onto dates
    // nothing happened on and a dead end there would blame the user for a
    // quiet Tuesday.
    return send(res, 200, dayView(found ?? { local_date: date, entries: [] }));
  }

  if (path === "/v1/journal/delete" && req.method === "POST") {
    const body = await readJson(req);
    let deleted = 0;
    for (const d of records.journal) {
      const before = d.entries.length;
      d.entries = d.entries.filter((e) => e.ref !== body.artefact_ref);
      deleted += before - d.entries.length;
    }
    // §30.5's checkbox. `delete_memories` absent means FALSE means keep, which
    // is the promise the sheet made — the default is not a convenience.
    let memoriesDeleted = 0;
    if (body.delete_memories) {
      const ids = new Set(body.message_ids ?? []);
      const before = records.memories.length;
      records.memories = records.memories.filter((m) => !ids.has(m.source_message_id));
      memoriesDeleted = before - records.memories.length;
    }
    return send(res, 200, { deleted, memories_deleted: memoriesDeleted });
  }

  // ── §32.4 Vault (S25, S26) ───────────────────────────────────────────────

  if (path === "/v1/memories" && req.method === "GET") {
    const types = url.searchParams.getAll("type");
    const rows = records.memories.filter((m) => types.length === 0 || types.includes(m.type));
    return send(res, 200, rows.map(memoryView));
  }

  if (path.startsWith("/v1/memories/") && path.endsWith("/mute") && req.method === "POST") {
    const id = path.slice("/v1/memories/".length, -"/mute".length);
    const memory = records.memories.find((m) => m.memory_id === id);
    if (!memory) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.memory.not_found", false));
    }
    const body = await readJson(req);
    memory.muted = Boolean(body.muted);
    return send(res, 200, memoryView(memory));
  }

  if (path.startsWith("/v1/memories/") && req.method === "DELETE") {
    const id = path.slice("/v1/memories/".length);
    if (!objectId(id)) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.sys.validation", false));
    }
    const before = records.memories.length;
    records.memories = records.memories.filter((m) => m.memory_id !== id);
    if (records.memories.length === before) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.memory.not_found", false));
    }
    // §30.5's whole promise: the journal is not touched. There is deliberately
    // no line here that could touch it.
    return send(res, 204, null);
  }

  // ── §32.15 family (S27, S28) ─────────────────────────────────────────────

  if (path === "/v1/family" && req.method === "GET") {
    return send(res, 200, records.family.map(memberView));
  }

  if (path.startsWith("/v1/family/") && path.endsWith("/memories") && req.method === "GET") {
    const id = path.slice("/v1/family/".length, -"/memories".length);
    const member = records.family.find((m) => m.member_id === id);
    if (!member) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.family.not_found", false));
    }
    // §32.15's "listed": "about them" is a NAME MATCH and nothing more, which
    // is exactly why the candidates are shown rather than acted on silently.
    //
    // **The match is script-sensitive, and the seed is coherent about it.** A
    // member's name and her memories are both things the user typed, so in a
    // Hindi account both are Devanagari. Seeding a Latin "Sudha" beside a
    // Devanagari memory made every Hindi candidate list empty — which the
    // hi baseline showed as a §32.15 sheet offering a single generic checkbox
    // where English offered a listed note. That was a defect in the fixture,
    // but the underlying sensitivity is real: a name stored in one script does
    // not match content written in another, and §32.15's answer is precisely
    // that the user sees and ticks the list rather than trusting the match.
    const needle = member.name.toLowerCase();
    return send(
      res,
      200,
      records.memories
        .filter((m) => m.content.toLowerCase().includes(needle))
        .map((m) => ({ memory_id: m.memory_id, type: m.type, content: m.content })),
    );
  }

  if (path.startsWith("/v1/family/") && path.endsWith("/memorial") && req.method === "POST") {
    const id = path.slice("/v1/family/".length, -"/memorial".length);
    const member = records.family.find((m) => m.member_id === id);
    if (!member) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.family.not_found", false));
    }
    const body = await readJson(req);
    if (!["living", "in_memory"].includes(body.memorial_state)) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.sys.validation", false));
    }
    // §45.2: ONE field. There is deliberately no other statement in this
    // branch — not a cleanup, not a cascade, not a helpful tidy-up of the
    // reminders. A conversion that quietly pruned would be a deletion wearing
    // a gentler word, and this is the code that would have to grow to do it.
    member.memorial_state = body.memorial_state;
    return send(res, 200, memberView(member));
  }

  if (path.startsWith("/v1/family/") && path.endsWith("/delete") && req.method === "POST") {
    const id = path.slice("/v1/family/".length, -"/delete".length);
    const member = records.family.find((m) => m.member_id === id);
    if (!member) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.family.not_found", false));
    }
    const body = await readJson(req);
    const ticked = new Set(body.delete_memory_ids ?? []);

    // §32.15's ORDER, mirrored from `sitara_api.family.service`: birth details
    // and charts before the member row, so a failure mid-way leaves a member
    // pointing at nothing rather than orphaned crown jewels pointing at nobody.
    const birthDetails = records.birth_details[id] ?? 0;
    const charts = records.charts[id] ?? 0;
    records.birth_details[id] = 0;
    records.charts[id] = 0;

    const beforeMemories = records.memories.length;
    records.memories = records.memories.filter((m) => !ticked.has(m.memory_id));
    const memoriesDeleted = beforeMemories - records.memories.length;

    records.family = records.family.filter((m) => m.member_id !== id);
    // §32.15's DPDP clause. The attestation is REVOKED and never deleted: the
    // consent is a fact about the account-holder, the birth details were a fact
    // about someone else. A well-meaning "delete everything" gets this exactly
    // backwards.
    records.attestations[id] = "revoked";

    return send(res, 200, {
      birth_details: birthDetails,
      charts,
      memories: memoriesDeleted,
      member_removed: true,
      attestation_retained: true,
    });
  }

  if (path.startsWith("/v1/family/") && req.method === "GET") {
    const id = path.slice("/v1/family/".length);
    const member = records.family.find((m) => m.member_id === id);
    if (!member) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.family.not_found", false));
    }
    return send(res, 200, memberView(member));
  }

  // ── §27 night reflection (S24) ───────────────────────────────────────────

  if (path.startsWith("/v1/reflection/") && req.method === "GET") {
    const date = path.slice("/v1/reflection/".length);
    const locale = url.searchParams.get("locale") ?? client.state.locale ?? "en";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return send(res, 422, envelope("SYS_VALIDATION", "errors.reflection.bad_date", false));
    }
    // §24.6 again: a night not yet written is an EMPTY reflection, not a 404.
    // The night takeover opens straight onto this surface, and a 404 on the
    // first tap would be the app telling her she had not done something.
    return send(res, 200, records.reflections[date] ?? emptyReflection(date, locale));
  }

  if (path.startsWith("/v1/reflection/") && req.method === "PUT") {
    const date = path.slice("/v1/reflection/".length);
    const body = await readJson(req);
    const entries = Object.entries(body.entries ?? {}).map(([prompt, text]) => ({ prompt, text }));
    const saved = {
      date,
      locale: body.locale ?? "en",
      entries,
      mood: body.mood ?? null,
      memory_chips: body.memory_chips ?? [],
      prompt_order: PROMPT_ORDER,
      started: entries.length > 0 || Boolean(body.mood),
    };
    records.reflections[date] = saved;
    return send(res, 200, saved);
  }

  // ── S28's chart (CC-007's diagram, drawn) ────────────────────────────────

  if (path === "/v1/chart" && req.method === "GET") {
    const subject = url.searchParams.get("subject_id");
    if (subject) {
      const member = records.family.find((m) => m.member_id === subject);
      if (!member) {
        return send(res, 422, envelope("SYS_VALIDATION", "errors.family.not_found", false));
      }
      if (!member.has_birth_details) {
        // §5.3: the engine declines rather than guessing, and so does this.
        // §28.2 has a designed variant for it; a chart nobody can compute is
        // that variant's business, not a 500.
        return send(
          res,
          422,
          envelope("ASTRO_INSUFFICIENT_BIRTH_DATA", "errors.astro.insufficient_birth_data", false),
        );
      }
    }
    return send(res, 200, CHART);
  }

  console.error(`[stub-api] unhandled ${req.method} ${path}`);
  send(res, 404, envelope("SYS_VALIDATION", "errors.sys.validation", false));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`stub-api listening on http://127.0.0.1:${port}`);
});
