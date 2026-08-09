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
      today: {
        variant: body.variant ?? "normal_morning",
        locale: body.locale ?? "en",
        // §28.2's densities are recorded for `normal_morning` only — density
        // changes the ranking engine's output COUNT, never its facts, so one
        // recording per density is the property worth replaying.
        density: body.density ?? "med",
      },
    });
    return send(res, 200, { ok: true });
  }
  if (path === "/__control/state") {
    const id = url.searchParams.get("clientId") ?? "default";
    return send(res, 200, clients.get(id)?.state ?? null);
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
    return send(res, 200, { user_id: "6a70000000000000000000a1", is_new_user: true });
  }

  // ── §24.4 onboarding ─────────────────────────────────────────────────────
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

  // ── §28.2 Today ──────────────────────────────────────────────────────────
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

  console.error(`[stub-api] unhandled ${req.method} ${path}`);
  send(res, 404, envelope("SYS_VALIDATION", "errors.sys.validation", false));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`stub-api listening on http://127.0.0.1:${port}`);
});
