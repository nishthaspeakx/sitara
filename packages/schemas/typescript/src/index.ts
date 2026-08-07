// GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

// ---------------------------------------------------------------------------
// SPEC §7.1 / §34.3 — the canonical 17 morning modules (closed set).
// The ranking engine emits ONLY these IDs.
// ---------------------------------------------------------------------------
export const MORNING_MODULES = ["energy_of_day", "personal_chart_theme", "moon_nakshatra_note", "colour", "number", "favourable_window", "caution_window", "priorities", "what_to_avoid", "food_and_drink", "work", "relationship", "family_reminder", "festival_observance", "goal_check", "spiritual_practice", "tomorrow_prep_teaser"] as const;
export type MorningModule = (typeof MORNING_MODULES)[number];

// ---------------------------------------------------------------------------
// SPEC §6.3 / §34.4 — namespaced error codes + the ONE canonical envelope.
// ---------------------------------------------------------------------------
export const ERROR_CODES = ["AUTH_INVALID_TOKEN", "AUTH_SESSION_EXPIRED", "AUTH_FORBIDDEN", "AUTH_UNDERAGE", "AUTH_OTP_THROTTLED", "AUTH_PROVIDER_CONFLICT", "ASTRO_INSUFFICIENT_BIRTH_DATA", "ASTRO_PLACE_UNRESOLVED", "ASTRO_ENGINE_UNAVAILABLE", "ASTRO_PROVIDER_DISPUTED", "VOICE_PROVIDER_UNAVAILABLE", "VOICE_MINUTES_EXHAUSTED", "VOICE_SESSION_NOT_FOUND", "PAY_PAYMENT_REQUIRED", "PAY_WEBHOOK_DUPLICATE", "PAY_PROVIDER_ERROR", "SAFE_CONTENT_BLOCKED", "SAFE_REVIEW_PENDING", "SYS_VALIDATION", "SYS_RATE_LIMITED", "SYS_IDEMPOTENCY_CONFLICT", "SYS_INTERNAL", "SYS_UNAVAILABLE"] as const;
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
