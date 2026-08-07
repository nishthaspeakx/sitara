-- Sitara/Tara core schema (Postgres 16 + pgvector) - Phase 1 + Phase 2 stubs
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TYPE sensitivity AS ENUM ('normal','sensitive','restricted');
CREATE TYPE visibility AS ENUM ('private','selected','family','never_stored');
CREATE TYPE mem_type AS ENUM ('profile','preference','relationship','goal','event','emotional_pattern','conversation_summary','family','media','sensitive','temporary');
CREATE TYPE plan_t AS ENUM ('free','premium','family','concierge');
CREATE TYPE safety_sev AS ENUM ('L1','L2','L3','L4','L5');

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_provider TEXT NOT NULL, auth_id TEXT UNIQUE NOT NULL,
  locale TEXT DEFAULT 'en-US', tz TEXT NOT NULL,
  status TEXT DEFAULT 'active', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE profiles (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT, preferred_name TEXT, gender TEXT,
  language TEXT DEFAULT 'en', interaction_style TEXT DEFAULT 'brief',
  astro_depth TEXT DEFAULT 'light' CHECK (astro_depth IN ('off','light','rich')),
  numerology_on BOOLEAN DEFAULT true,
  relationship_status TEXT, city TEXT, join_reason TEXT
);
CREATE TABLE birth_details (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type TEXT NOT NULL CHECK (subject_type IN ('user','family_member')),
  subject_id UUID NOT NULL,
  dob DATE NOT NULL, tob TIME, birth_place TEXT, lat NUMERIC, lon NUMERIC,
  tob_confidence TEXT DEFAULT 'unknown', UNIQUE(subject_type, subject_id)
);
CREATE TABLE family_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  linked_user_id UUID REFERENCES users(id),          -- Phase 2: real account
  relation TEXT NOT NULL, name TEXT NOT NULL,
  is_minor BOOLEAN DEFAULT false, managed_by UUID REFERENCES users(id),
  visibility visibility DEFAULT 'private',
  health_notes_mem UUID, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  a_member UUID REFERENCES family_members(id), b_member UUID REFERENCES family_members(id),
  rel_type TEXT, context_mem UUID
);
CREATE TABLE preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  key TEXT NOT NULL, value JSONB NOT NULL, source TEXT,
  sensitivity sensitivity DEFAULT 'normal', updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, key)
);
CREATE TABLE goals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  title TEXT, why TEXT, status TEXT DEFAULT 'active',
  target_date DATE, progress JSONB DEFAULT '[]', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ DEFAULT now(), mode TEXT DEFAULT 'chat',
  framework TEXT, no_memory BOOLEAN DEFAULT false
);
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('user','tara','system')),
  content TEXT, audio_uri TEXT, tokens INT,
  safety_labels JSONB DEFAULT '[]', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  type mem_type NOT NULL, content TEXT NOT NULL,
  source_message UUID REFERENCES messages(id),
  sensitivity sensitivity DEFAULT 'normal', visibility visibility DEFAULT 'private',
  consent_state TEXT DEFAULT 'noticed' CHECK (consent_state IN ('noticed','confirmed','declined')),
  importance REAL DEFAULT 0.5, expires_at TIMESTAMPTZ,
  embedding vector(1024), created_at TIMESTAMPTZ DEFAULT now(), edited_at TIMESTAMPTZ
);
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON memories (user_id, type) WHERE expires_at IS NULL OR expires_at > now();
CREATE TABLE journal_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  entry_date DATE, content TEXT, generated BOOLEAN DEFAULT false,
  mood_id UUID
);
CREATE TABLE mood_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ DEFAULT now(), value SMALLINT CHECK (value BETWEEN 1 AND 5), note TEXT
);
CREATE TABLE daily_briefings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  brief_date DATE, modules JSONB, engine_refs JSONB,   -- traceability: astro claims -> engine output ids
  opened_at TIMESTAMPTZ, rating SMALLINT, UNIQUE(user_id, brief_date)
);
CREATE TABLE night_reflections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  reflect_date DATE, answers JSONB, summary TEXT, tomorrow JSONB,
  UNIQUE(user_id, reflect_date)
);
CREATE TABLE recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID, ts TIMESTAMPTZ DEFAULT now(), rtype TEXT, content JSONB, acted BOOLEAN
);
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID, ntype TEXT, scheduled_at TIMESTAMPTZ, sent_at TIMESTAMPTZ,
  opened_at TIMESTAMPTZ, payload JSONB
);
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID UNIQUE REFERENCES users(id), plan plan_t DEFAULT 'free',
  store TEXT, status TEXT, trial_ends TIMESTAMPTZ, renews_at TIMESTAMPTZ,
  price_cents INT, currency TEXT
);
CREATE TABLE payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id UUID REFERENCES subscriptions(id), amount_cents INT, currency TEXT,
  gateway TEXT, gateway_ref TEXT, status TEXT, ts TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID, etype TEXT, title TEXT, event_date DATE,
  recurrence TEXT, tz_rule TEXT, panchang_rule JSONB    -- tithi-based recurrence
);
CREATE TABLE celebrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id), plan JSONB, reminders JSONB
);
CREATE TABLE safety_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID, trigger_label TEXT, severity safety_sev,
  message_id UUID, action_taken TEXT, reviewer UUID, review_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), resolved_at TIMESTAMPTZ
);
CREATE TABLE consent_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID, scope TEXT, policy_version TEXT,
  granted_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ
);
CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY, actor TEXT, action TEXT, entity TEXT, entity_id UUID,
  ts TIMESTAMPTZ DEFAULT now(), detail JSONB, prev_hash TEXT, hash TEXT
);
-- Phase 4 stubs: experts, appointments; Phase 3: media_assets, albums (omitted here)
