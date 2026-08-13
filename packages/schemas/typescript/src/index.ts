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
export const ERROR_CODES = ["AUTH_INVALID_TOKEN", "AUTH_SESSION_EXPIRED", "AUTH_FORBIDDEN", "AUTH_UNDERAGE", "AUTH_OTP_THROTTLED", "AUTH_PROVIDER_CONFLICT", "ASTRO_INSUFFICIENT_BIRTH_DATA", "ASTRO_PLACE_UNRESOLVED", "ASTRO_ENGINE_UNAVAILABLE", "ASTRO_PROVIDER_DISPUTED", "ASTRO_NAME_UNCONFIRMED", "ASTRO_NAME_INVALID", "VOICE_PROVIDER_UNAVAILABLE", "VOICE_MINUTES_EXHAUSTED", "VOICE_SESSION_NOT_FOUND", "VOICE_NOTE_EXPIRED", "PAY_PAYMENT_REQUIRED", "PAY_WEBHOOK_DUPLICATE", "PAY_PROVIDER_ERROR", "SAFE_CONTENT_BLOCKED", "SAFE_REVIEW_PENDING", "SYS_VALIDATION", "SYS_RATE_LIMITED", "SYS_IDEMPOTENCY_CONFLICT", "SYS_INTERNAL", "SYS_UNAVAILABLE"] as const;
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
  VOICE_NOTE_EXPIRED: 410,
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
  VOICE_NOTE_EXPIRED: false,
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
  ack: number | null;
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
// SPEC §4.3 — Tara's twelve presence states.
// ONE source, because the client and the server each had their own twelve
// and five of them disagreed — by name and by position. See the JSON.
// ---------------------------------------------------------------------------
/** SPEC §4.3 — Tara's twelve presence states. CLOSED SET. Added in M8-P10 after the two languages turned out to hold DIFFERENT twelves: `sitara_api.chat_orchestration.types.PresenceState` numbered §4.3 exactly (1 welcome … 11 safety-still, 12 profile portrait) while `apps/web`'s `TARA_STATES` had invented `warm_neutral`/`smile`/`full_smile`/`reading`/`safety` and dropped `calm_guidance` and `encouragement` entirely. Five of the twelve disagreed, and they disagreed by POSITION as well as by name — index 11 was `safety_still` on the server and `reading` in the client. Nothing failed because no screen had ever consumed a served presence state; S18's chat header is the first, and §29.5 puts state 11 in exactly that header. The same story as the confidence states one milestone earlier, which is why this file exists rather than a third hand-written copy. */
export const PRESENCE_STATES = ["welcome", "listening", "speaking_soft", "thoughtful", "calm_guidance", "concern_kind", "encouragement", "celebration", "night", "festival", "safety_still", "profile_portrait"] as const;
export type PresenceState = (typeof PRESENCE_STATES)[number];

/** §4.3's own numbering. Documentation and a threshold operand — never the wire. */
export const PRESENCE_ORDINAL: Record<PresenceState, number> = {
  welcome: 1,
  listening: 2,
  speaking_soft: 3,
  thoughtful: 4,
  calm_guidance: 5,
  concern_kind: 6,
  encouragement: 7,
  celebration: 8,
  night: 9,
  festival: 10,
  safety_still: 11,
  profile_portrait: 12,
};

// ---------------------------------------------------------------------------
// SPEC §32.4 — the eleven memory types. Vault filters use exactly these.
// ---------------------------------------------------------------------------
/** SPEC §32.4 — the eleven memory types. CLOSED SET. §32.4 ends 'Vault filters use exactly these 11 labels, localized', and until M8-P10 two different elevens were in the repo: `sitara_api.memory.taxonomy.MemoryType` had §32.4's (person, significant_event, date_anniversary, …) and `packages/i18n` had an invented parallel set (life_fact, concern, belief_practice, conversation_thread, …) that seven of eleven labels disagreed with. Nothing rendered a typed memory yet, so nothing failed. S18's memory chip is the first thing that does. `taxonomy.py` still OWNS the rules — consent, gates, decay half-lives are §6.3 the memory module's business and stay there; this file is only the closed set of IDS, so the catalogs and the vault can be checked against it mechanically. `dynamic-keys.json` reads it through `valuesFrom`. */
export const MEMORY_TYPES = ["person", "significant_event", "date_anniversary", "preference", "goal_intention", "decision_context", "mood_pattern", "health_adjacent", "work_finance", "spiritual_practice", "pronunciation_identity"] as const;
export type MemoryType = (typeof MEMORY_TYPES)[number];

// ---------------------------------------------------------------------------
// SPEC §25.4 / §30.4 — one chat turn, as it crosses the wire.
// ---------------------------------------------------------------------------
/** §25.4's two authors. There is no third — group mechanics are deliberately dropped from the WhatsApp grammar, so there is no shape here that could carry a third party. */
export const CHAT_ROLES = ["user", "tara"] as const;
export type ChatRole = (typeof CHAT_ROLES)[number];

/** §9's L1–L5 ladder, as the client must see it. §22.9 and §29.1: L3+ takes the screen over. The threshold is DECLARED below rather than written as `>= 3` on each side. */
export const SAFETY_LEVELS = ["l1_clear", "l2_constrained", "l3_redirect", "l4_crisis", "l5_human_review"] as const;
export type SafetyLevel = (typeof SAFETY_LEVELS)[number];

/** §34.7's three VerifiedSourceRow states. Served, never inferred client-side: whether two almanacs corroborated a fact is something only §32.2's adjudication knows. */
export const SOURCE_STATES = ["default", "single", "disputed"] as const;
export type SourceState = (typeof SOURCE_STATES)[number];

/** §9's ladder as numbers, for the one comparison both sides make. */
export const SAFETY_LEVEL_ORDINAL: Record<SafetyLevel, number> = {
  l1_clear: 1,
  l2_constrained: 2,
  l3_redirect: 3,
  l4_crisis: 4,
  l5_human_review: 5,
};

/** §22.9 / §29.1 — 'safety takeover (/support/now, L3+)'. One number, read by the server when it decides and by the client when it renders, so the two can never disagree about what L3+ means. */
export const SAFETY_TAKEOVER_FROM_ORDINAL = 3 as const;

/** §30.4 — the citation marker sits INSIDE the sentence, before the final stop (the rule daily-guidance's composer already follows), and the grounding validator judges a sentence at a time. So the underlined span is the sentence, which is the unit that was actually verified. A narrower span would claim a precision nothing measured. */
export const CITATION_SPANS_ARE_SENTENCES = 1 as const;

/** §30.4's three layers, already rendered — the same shape and the same reason as TodayTrust. Fact IDs are absent BY SHAPE: there is no field one could travel in, which is the guarantee TrustSheet's props already give on the component side. */
export interface ChatTrust {
  plain: string;
  sources_line: string;
  details: string[];
}

/** §25.4's fact-citation underline. `span_start`/`span_end` index into the turn's `text` (Unicode code points, not UTF-16 units — Devanagari and emoji both make those differ). One citation per verified sentence. */
export interface ChatCitation {
  span_start: number;
  span_end: number;
  confidence: ConfidenceState;
  source_state: SourceState;
  trust: ChatTrust;
}

/** §32.4 — a SUGGESTION. Nothing is stored without the explicit chip, so this shape carries no memory id: there is no memory yet. `requires_reconfirmation` is types 7–9's 'always re-confirm wording before save'. */
export interface MemoryChipOffer {
  type: MemoryType;
  summary: string;
  requires_reconfirmation: boolean;
}

/** One of Tara's turns, after every §9 validator has passed. There is no shape for an unvalidated one, anywhere, in either language — which is what makes 'a fabricated claim never reaches a bubble' a property of the contract rather than a rule someone has to keep. */
export interface ChatTurn {
  message_id: string;
  text: string;
  locale: string;
  confidence: ConfidenceState;
  safety_level: SafetyLevel;
  presence_state: PresenceState;
  intent: string;
  trace_id: string;
  citations: ChatCitation[];
  memory_chips: MemoryChipOffer[];
  review_queued: boolean;
  message_key: string | null;
  budget_notice_key: string | null;
}

// ---------------------------------------------------------------------------
// SPEC §33.1 / §6.4 / §25.4 — the vocabulary of a voice note.
// `playback_policy` is what makes §25.4's promise checkable: replay plays the
// user's ORIGINAL recording, and `synthesised` — the one member under which
// audio is a reconstruction — is never valid on a user message.
// ---------------------------------------------------------------------------
/** §6.4's `messages.transcript_status`, one of §33.1's six explicit fields. `not_applicable` is a TYPED message — the field is required on every message row, so text needs a member that says 'this was never spoken' rather than a null that reads as 'transcription is still coming'. §28.3's failure row is `failed`: 'transcribe-fail → send as text? original audio preserved' — the audio survives a failed transcript, which is why this is a status and not a delete trigger. */
export const TRANSCRIPT_STATUSES = ["not_applicable", "pending", "ready", "failed"] as const;
export type TranscriptStatus = (typeof TRANSCRIPT_STATUSES)[number];

/** §6.4's `messages.playback_policy`, and the field §25.4's central promise rests on: 'replay plays the user's ORIGINAL recording per the §33.1 storage policy, never a TTS reconstruction'. That sentence is only enforceable if a bubble can tell the three cases apart, which is what this enum is for. `synthesised` is the ONLY member under which audio is a reconstruction, and §25.4 makes it illegal on a user message — a rule the store enforces structurally rather than by review. */
export const PLAYBACK_POLICIES = ["text_only", "original_audio", "transcript_only", "synthesised"] as const;
export type PlaybackPolicy = (typeof PLAYBACK_POLICIES)[number];

/** §34.6's `vad.state` payload. In M9 this brackets a HELD recording rather than reporting server-side voice activity detection — §25.4's grammar is hold-to-record or tap-lock, so the client knows when speech starts and stops because the user's finger says so. M10's live calls add the server-VAD sense of the same member (§25.3's barge-in ducking); the members below are chosen so that addition is a widening, not a rename. */
export const VAD_STATES = ["speech_start", "speech_end", "cancelled"] as const;
export type VadState = (typeof VAD_STATES)[number];

/** §33.1 — 'the original recording is stored encrypted for 30 days BY DEFAULT'. Default, so a user setting may shorten it; the expiry job reads the per-note `source_audio_expires_at` rather than this constant, which exists so both sides can render the same promise in the same words. */
export const SOURCE_AUDIO_RETENTION_DAYS = 30 as const;

/** A cap, not a spec value. §34.6's frame is 16kHz mono s16le = 32 kB/s, so two minutes is ~3.8 MB — comfortably inside MongoDB's 16 MB document limit, which is where §33.1's CSFLE key class puts the bytes. The client stops recording here rather than letting a pocket-dial write a document that cannot be stored. */
export const MAX_NOTE_DURATION_MS = 120000 as const;

// ---------------------------------------------------------------------------
// SPEC §34.6 — control-event payloads: the text chat (S18) and voice notes
// (M9). `barge_in` and `entitlement.warning` stay untyped — they belong to
// live calls, which §33.5 gates and M10 owns.
// ---------------------------------------------------------------------------
/** Client → server. The ticket is single-use and 60-second; §34.5's session cookies are httpOnly and first-party, and a WebSocket handshake to another origin does not carry them. */
export interface SessionStartPayload {
  ticket: string;
  conversation_id: string;
  locale: string;
  resume_token: string | null;
}

/** Server → client. `resume_token` is what a reconnect inside `resume_window_s` presents (§32.11). */
export interface SessionReadyPayload {
  resume_token: string;
  resume_window_s: number;
  conversation_id: string;
}

/** Client → server on `captions.final` when typed; server → client on the same member when the turn was SPOKEN and STT has finalised it. One shape for both because §34.6's whole premise is that a typed message and a transcribed one are the same event — the difference is which of the three §33.1 fields below are populated, not which member carries it. On a typed message they are `not_applicable` / `text_only` / null, which is exactly what the store already writes. */
export interface UserTurnPayload {
  role: ChatRole;
  text: string;
  client_message_id: string;
  quoted_message_id: string | null;
  transcript_status: TranscriptStatus;
  playback_policy: PlaybackPolicy;
  source_audio_asset_id: string | null;
  duration_ms: number | null;
  source_audio_expires_at: string | null;
}

/** Server → client, on `captions.partial`. `role` is the CONSTANT "user" and not a ChatRole, which is the whole point of the shape: §9 runs grounding, language-quality and safety-post after generation, so a partial caption of TARA's words would be pre-validation text racing three validators to the screen. Through M8 that was guaranteed by nobody writing the frame. Now the frame exists, for the user's own speech, and the guarantee is that there is no value of `role` here that could carry hers. */
export interface PartialCaptionPayload {
  role: "user";
  text: string;
  client_message_id: string;
}

/** Client → server, on `vad.state`. Brackets a held recording. `client_message_id` is minted before the first PCM byte leaves, so every binary frame in the bracket already belongs to a bubble the thread is drawing — the transcript lands in a message that exists rather than appearing from nowhere when STT returns. */
export interface VadStatePayload {
  state: VadState;
  client_message_id: string;
  quoted_message_id: string | null;
}

/** Server → client, on `tts.start`. §25.4: 'Tara's replies arrive as voice-note bubbles rendered from her TTS with transcript toggle'. Emitted after her `captions.final`, so the transcript the toggle shows is on screen before any audio plays — and is the same validated text the audio was rendered from, not a second generation. */
export interface TtsStartPayload {
  client_message_id: string;
  tts_audio_asset_id: string;
  sample_rate_hz: number;
  voice_id: string | null;
}

/** Server → client, on `tts.chunk_meta`. §13 — shapes, never content. There is deliberately no text field: the words already crossed on `captions.final`, and a second copy travelling beside the audio is a second thing to keep in step with the validators. */
export interface TtsChunkMetaPayload {
  client_message_id: string;
  seq: number;
  byte_length: number;
}

/** Server → client, on `tts.end`. Total duration for the bubble's scrubber, and the signal that no further chunk meta is coming. */
export interface TtsEndPayload {
  client_message_id: string;
  duration_ms: number;
}

/** Server → client, on `captions.final`. Carries the whole validated turn and nothing else — there is no field here for text that has not been through §9's validators. */
export interface TaraTurnPayload {
  role: ChatRole;
  client_message_id: string;
  turn: ChatTurn;
}

/** Server → client. The client switches on `state` alone. `stage` is §9's pipeline step, carried for traces and analytics — a shape, not content (§13) — and deliberately not something the UI branches on: the presence state is the designed vocabulary (§4.3) and the stage list is an implementation detail that may grow. */
export interface PresenceStatePayload {
  state: PresenceState;
  stage: string | null;
}

/** Server → client. `reason` is why the socket gave up, so the thread can say something true rather than 'something went wrong'. */
export interface HandoffToTextPayload {
  conversation_id: string;
  reason: string;
}

/** Server → client (§32.11). `pending_turn` is the turn that COMPLETED while the socket was down — buffered rather than re-run, because re-running a turn charges a user twice for one question. */
export interface ResumeOfferPayload {
  conversation_id: string;
  pending_turn: ChatTurn | null;
  pending_client_message_id: string | null;
}

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
