// GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

// ---------------------------------------------------------------------------
// SPEC §7.1 / §34.3 — the canonical 17 morning modules (closed set).
// The ranking engine emits ONLY these IDs.
// ---------------------------------------------------------------------------
export const MORNING_MODULES = ["energy_of_day", "personal_chart_theme", "moon_nakshatra_note", "colour", "number", "favourable_window", "caution_window", "priorities", "what_to_avoid", "food_and_drink", "work", "relationship", "family_reminder", "festival_observance", "goal_check", "spiritual_practice", "tomorrow_prep_teaser"] as const;
export type MorningModule = (typeof MORNING_MODULES)[number];

// ---------------------------------------------------------------------------
// SPEC §5.4 / §34.7 — the five user-visible confidence states (closed set).
// These IDs are the WIRE format: sitara-api serves them verbatim and
// ConfidenceChip renders them. The two drifted once (M8) — hence one source.
// ---------------------------------------------------------------------------
export const CONFIDENCE_STATES = ["verified", "verified_limited_birth_data", "approximate", "tradition_based_general", "cannot_calculate"] as const;
export type ConfidenceState = (typeof CONFIDENCE_STATES)[number];

// ---------------------------------------------------------------------------
// SPEC §6.3 / §34.4 — namespaced error codes + the ONE canonical envelope.
// ---------------------------------------------------------------------------
export const ERROR_CODES = ["AUTH_INVALID_TOKEN", "AUTH_SESSION_EXPIRED", "AUTH_FORBIDDEN", "AUTH_UNDERAGE", "AUTH_OTP_THROTTLED", "AUTH_PROVIDER_CONFLICT", "ASTRO_INSUFFICIENT_BIRTH_DATA", "ASTRO_PLACE_UNRESOLVED", "ASTRO_ENGINE_UNAVAILABLE", "ASTRO_PROVIDER_DISPUTED", "ASTRO_NAME_UNCONFIRMED", "ASTRO_NAME_INVALID", "VOICE_PROVIDER_UNAVAILABLE", "VOICE_MINUTES_EXHAUSTED", "VOICE_SESSION_NOT_FOUND", "PAY_PAYMENT_REQUIRED", "PAY_WEBHOOK_DUPLICATE", "PAY_PROVIDER_ERROR", "SAFE_CONTENT_BLOCKED", "SAFE_REVIEW_PENDING", "SYS_VALIDATION", "SYS_RATE_LIMITED", "SYS_IDEMPOTENCY_CONFLICT", "SYS_INTERNAL", "SYS_UNAVAILABLE"] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export const ERROR_HTTP_STATUS: Record<ErrorCode, number> = {
  AUTH_INVALID_TOKEN: 401,
  AUTH_SESSION_EXPIRED: 401,
  AUTH_FORBIDDEN: 403,
  AUTH_UNDERAGE: 422,
  AUTH_OTP_THROTTLED: 429,
  AUTH_PROVIDER_CONFLICT: 409,
  ASTRO_INSUFFICIENT_BIRTH_DATA: 422,
  ASTRO_PLACE_UNRESOLVED: 422,
  ASTRO_ENGINE_UNAVAILABLE: 503,
  ASTRO_PROVIDER_DISPUTED: 409,
  ASTRO_NAME_UNCONFIRMED: 422,
  ASTRO_NAME_INVALID: 400,
  VOICE_PROVIDER_UNAVAILABLE: 503,
  VOICE_MINUTES_EXHAUSTED: 402,
  VOICE_SESSION_NOT_FOUND: 404,
  PAY_PAYMENT_REQUIRED: 402,
  PAY_WEBHOOK_DUPLICATE: 409,
  PAY_PROVIDER_ERROR: 502,
  SAFE_CONTENT_BLOCKED: 422,
  SAFE_REVIEW_PENDING: 422,
  SYS_VALIDATION: 400,
  SYS_RATE_LIMITED: 429,
  SYS_IDEMPOTENCY_CONFLICT: 409,
  SYS_INTERNAL: 500,
  SYS_UNAVAILABLE: 503,
};

export const ERROR_DEFAULT_RETRYABLE: Record<ErrorCode, boolean> = {
  AUTH_INVALID_TOKEN: false,
  AUTH_SESSION_EXPIRED: false,
  AUTH_FORBIDDEN: false,
  AUTH_UNDERAGE: false,
  AUTH_OTP_THROTTLED: true,
  AUTH_PROVIDER_CONFLICT: false,
  ASTRO_INSUFFICIENT_BIRTH_DATA: false,
  ASTRO_PLACE_UNRESOLVED: false,
  ASTRO_ENGINE_UNAVAILABLE: true,
  ASTRO_PROVIDER_DISPUTED: false,
  ASTRO_NAME_UNCONFIRMED: false,
  ASTRO_NAME_INVALID: false,
  VOICE_PROVIDER_UNAVAILABLE: true,
  VOICE_MINUTES_EXHAUSTED: false,
  VOICE_SESSION_NOT_FOUND: false,
  PAY_PAYMENT_REQUIRED: false,
  PAY_WEBHOOK_DUPLICATE: false,
  PAY_PROVIDER_ERROR: true,
  SAFE_CONTENT_BLOCKED: false,
  SAFE_REVIEW_PENDING: false,
  SYS_VALIDATION: false,
  SYS_RATE_LIMITED: true,
  SYS_IDEMPOTENCY_CONFLICT: false,
  SYS_INTERNAL: true,
  SYS_UNAVAILABLE: true,
};

/** SPEC §34.4 — the ONE canonical error envelope. No module invents its own. */
export interface ErrorEnvelope {
  code: ErrorCode;
  message_key: string;
  trace_id: string;
  retryable: boolean;
}

// ---------------------------------------------------------------------------
// SPEC §34.6 — voice/call WebSocket wire protocol (closed control-event set).
// Binary frames: 16kHz mono PCM, 8-byte header (4-byte seq + 4-byte flags).
// ---------------------------------------------------------------------------
export const CONTROL_EVENT_TYPES = ["session.start", "session.ready", "session.end", "vad.state", "barge_in", "tts.start", "tts.chunk_meta", "tts.end", "presence.state", "captions.partial", "captions.final", "entitlement.warning", "error", "handoff.to_text", "resume.offer"] as const;
export type ControlEventType = (typeof CONTROL_EVENT_TYPES)[number];

/** SPEC §34.6 — JSON text-frame control event. Server acks by seq. */
export interface ControlEvent {
  type: ControlEventType;
  seq: number;
  ts: number;
  payload: Record<string, unknown>;
}

export const BINARY_AUDIO_FORMAT = "pcm_s16le" as const;
export const BINARY_SAMPLE_RATE_HZ = 16000 as const;
export const BINARY_CHANNELS = 1 as const;
export const BINARY_HEADER_BYTES = 8 as const;
export const BINARY_HEADER_SEQ_BYTES = 4 as const;
export const BINARY_HEADER_FLAGS_BYTES = 4 as const;

export const HEARTBEAT_INTERVAL_S = 10 as const;
export const REAP_AFTER_SILENCE_S = 30 as const;
export const RESUME_WINDOW_S = 300 as const;

// ---------------------------------------------------------------------------
// SPEC §28.2 — the Today payload and the closed sets it carries.
// `variant` is deliberately absent: §32.1's precedence is a RULE over this
// state, evaluated in apps/web/src/lib/today-variant.ts, not a server value.
// ---------------------------------------------------------------------------
export const DENSITIES = ["low", "med", "high"] as const;
export type Density = (typeof DENSITIES)[number];
export const TIERS = ["paying", "trial", "dormant"] as const;
export type Tier = (typeof TIERS)[number];
export const BRIEF_STATUSES = ["pending", "polished", "ranking_only", "verified_core_cards", "failed"] as const;
export type BriefStatus = (typeof BRIEF_STATUSES)[number];
export const BRIEF_DEGRADE_REASONS = ["grounding_failed", "llm_unavailable", "panchang_unavailable", "chart_unavailable", "language_quality_failed"] as const;
export type BriefDegradeReason = (typeof BRIEF_DEGRADE_REASONS)[number];
export const PLAN_STATES = ["premium", "trial", "free", "grace"] as const;
export type PlanState = (typeof PLAN_STATES)[number];
export const TIMING_QUALITIES = ["auspicious", "neutral", "inauspicious"] as const;
export type TimingQuality = (typeof TIMING_QUALITIES)[number];
export const TIME_BANDS = ["morning", "afternoon", "evening", "night"] as const;
export type TimeBand = (typeof TIME_BANDS)[number];

/** §28.2's four time-of-day bands, as START minutes local. The thresholds are DECLARED here because both sides need them and they are spec rules, not preferences: the API composes Tara's line for the band, and the client renders the night takeover — '>20:00 the whole tab transforms'. Two hand-written copies of 20:00 is how a screen goes to dusk an hour after the sentence on it did. */
export const TIME_BAND_STARTS: ReadonlyArray<readonly [TimeBand, string]> = [
  ["night", "20:00"],
  ["evening", "17:00"],
  ["afternoon", "12:00"],
  ["morning", "00:00"],
];

/** §28.2's band for a zero-padded local "HH:MM". Never a UTC time. */
export function timeBand(localTime: string): TimeBand {
  for (const [band, startsAt] of TIME_BAND_STARTS) {
    if (localTime >= startsAt) return band;
  }
  return "morning";
}

/** §30.4's three layers, already rendered. Fact IDs are absent BY SHAPE — there is no field one could travel in, which is the same guarantee TrustSheet's props give on the component side. */
export interface TodayTrust {
  plain: string;
  sources_line: string;
  details: string[];
}

/** One of §34.3's seventeen, composed and grounded. `text` is engine output — §5.3 forbids the LLM computing it and the composer put the citation inside the sentence before stripping it for the wire. */
export interface TodayModule {
  module: MorningModule;
  text: string;
  confidence: ConfidenceState;
  trust: TodayTrust;
}

/** §28.2 item (2) — 'one warm sentence for this moment', the emotional anchor, always present. NOT one of the seventeen and never rendered as a card. */
export interface TodayTarasLine {
  text: string;
  confidence: ConfidenceState;
}

/** §28.2 item (6), shaped for the §24.3 PanchangStrip. `label_key` is an i18n key; `value` is a localised term the API resolved. */
export interface TodayPanchangEntry {
  label_key: string;
  value: string;
}

/** §28.2's festival variant — the ONLY surface allowed above the core card, and suppressed to a core-card accent when two banners already show (§32.1). */
export interface TodayFestival {
  name: string;
  tradition_label: string;
  date_label: string;
}

/** §30.2 Travel Mode. `city` is the place timings were recomputed for. */
export interface TodayTravel {
  active: boolean;
  city: string | null;
}

/** Everything §32.1's precedence rule reads, and nothing it does not. The rule itself lives on the client so there is exactly one implementation of it. */
export interface TodayState {
  first_session: boolean;
  first_morning: boolean;
  brief_time: string;
  travel: TodayTravel;
  festival: TodayFestival | null;
  birthday: boolean;
  birth_time_missing: boolean;
  trial_day: number | null;
  plan: PlanState;
  story_ring_enabled: boolean;
}

/** One day-timing window for S16 (§28.2 item 6 → /today/timings). Minutes-from-midnight because that is `TimingBar`'s axis unit; `range` is pre-formatted in the FACT's own zone (§5.3) so no client re-derives a clock from a timestamp and lands in the wrong one. */
export interface TodayTiming {
  name: string;
  starts_minute: number;
  ends_minute: number;
  range: string;
  quality: TimingQuality;
}

/** What GET /v1/today serves. `local_time` is DATA, not ambient: §28.2's night takeover fires after 20:00 LOCAL, and a screen that read the browser clock would render a different variant than the brief was generated for — and would make every §24.8 baseline depend on when CI ran. */
export interface TodayPayload {
  local_date: string;
  local_time: string;
  timezone: string;
  density: Density;
  tier: Tier;
  status: BriefStatus;
  degrade_reason: BriefDegradeReason | null;
  confidence: ConfidenceState | null;
  taras_line: TodayTarasLine | null;
  modules: TodayModule[];
  panchang: TodayPanchangEntry[];
  state: TodayState;
  timings: TodayTiming[];
  place_label: string | null;
}
