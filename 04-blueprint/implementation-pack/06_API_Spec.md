# API Specification (REST + SSE, /v1) — key endpoints
Auth: Firebase JWT bearer. Errors: RFC7807. Rate limits per plan. All timestamps ISO8601.

AUTH/PROFILE
POST /v1/auth/session {firebase_token} → {user, is_new}
GET/PATCH /v1/profile · PUT /v1/profile/birth-details {dob,tob?,place?} → triggers chart compute (async, webhook to client)
GET /v1/profile/chart → computed chart summary + engine version (traceable)

ONBOARDING
POST /v1/onboarding/answers {ring, key, value} · GET /v1/onboarding/state

CONVERSATION
POST /v1/conversations {mode?, no_memory?} → {id}
POST /v1/conversations/:id/messages {content|audio_uri} → SSE stream: tokens…, done{message_id, memory_suggestions[], safety_action?}
POST /v1/messages/:id/feedback {helpful: bool, note?}
POST /v1/voice/transcribe (multipart) → {text, confidence}

MEMORY
GET /v1/memories?type=&q= (paginated, plain-language render)
POST /v1/memories/:id/confirm | /decline (consent chips)
PATCH /v1/memories/:id {content|visibility|expires_at} · DELETE /v1/memories/:id
POST /v1/memories/export → job → email link · POST /v1/memory/pause {until}

DAY LOOP
GET /v1/briefings/today → {modules[], engine_refs[], rating?}
POST /v1/briefings/today/rating {1-5}
GET/POST /v1/reflections/today {answers} → {summary, tomorrow[]}
GET /v1/reports/weekly?week=

GOALS/MOOD
CRUD /v1/goals (max 3 active enforced 409) · POST /v1/moods {value, note?}

NOTIFICATIONS
GET/PATCH /v1/notification-prefs {brief_time, quiet_hours, daily_cap, types{}}

SUBSCRIPTION
GET /v1/subscription · POST /v1/subscription/checkout {plan, period, gateway} → url/intent
POST /v1/webhooks/stripe · /razorpay (signed) · POST /v1/subscription/cancel (immediate, no retention flow)

SAFETY/PRIVACY
GET /v1/privacy/summary → what's stored, counts, toggles
POST /v1/account/delete → 30-day grace purge job
(Internal) POST /v1/safety/events · GET /v1/admin/safety/queue

ADMIN (separate audience-scoped token): /v1/admin/users/:id (redacted), /v1/admin/prompts (versioned publish, eval-gate), /v1/admin/experiments, /v1/admin/costs
