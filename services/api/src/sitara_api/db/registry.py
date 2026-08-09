"""The SPEC §6.4 collection table, as data.

Everything that touches the database shape reads this module: the creator
(schema.py), the verifier (verify.py), the CSFLE codec (csfle.py) and the
migration runner. One declaration, so "what the database should look like"
cannot drift between the thing that builds it and the thing that checks it.

Three rules govern what may appear here:

1. **Every collection carries a citation.** §6.4 rows cite `§6.4`; collections
   the table does not list cite the section that mandates them (`sessions` from
   §22.5, `stories` from §25.7, and so on). A collection with no citation is
   invention, and the verifier fails on any live collection missing from here.

2. **Every index not in the §6.4 cell carries a `cite`.** The table's index
   list is the baseline; anything beyond it is a deliberate, sourced addition,
   and `tests/db/test_registry_matches_spec.py` enforces that by parsing the
   table itself.

3. **TTL indexes exist only where the table says "TTL".** §6.4 writes
   `TTL 90 days` for three collections and prose retention ("24mo", "8 years
   (tax)", "7 years, append-only") for the rest. Prose retention is a job's
   problem, not the storage engine's — a TTL index on `payments` would delete
   the tax record the table says to keep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pymongo import ASCENDING, DESCENDING

# ---------------------------------------------------------------------------
# bson type aliases — kept short so the declarations below read like the table
STR = "string"
DT = "date"
OBJ = "object"
ARR = "array"
BOOL = "bool"
NUM = ["double", "int", "long"]
INT = ["int", "long"]
OID = "objectId"
BIN = "binData"

#: Carried by every document in every collection (§6.4 preamble).
BASE_FIELDS: Mapping[str, Any] = {
    "created_at": DT,
    "updated_at": DT,
    "schema_v": INT,
}
BASE_REQUIRED: tuple[str, ...] = ("created_at", "updated_at", "schema_v")

DAY = 24 * 3600


@dataclass(frozen=True)
class IndexSpec:
    """One btree index.

    `cite` is set when the index is NOT in the §6.4 "Indexes" cell — it names
    the section that asks for it. `extends` marks an index whose key list adds
    to a §6.4 index rather than replacing it (see transit_cache).
    """

    keys: Sequence[tuple[str, int]]
    unique: bool = False
    name: str | None = None
    partial: Mapping[str, Any] | None = None
    ttl_seconds: int | None = None
    cite: str | None = None
    extends: tuple[str, ...] | None = None
    #: The key names as §6.4 spells them, where the stored field differs
    #: (the table writes `subject`, the document stores `subject_id`).
    spec_keys: tuple[str, ...] | None = None

    @property
    def key_names(self) -> tuple[str, ...]:
        return tuple(k for k, _ in self.keys)


@dataclass(frozen=True)
class VectorIndexSpec:
    """An Atlas Search vector index (§32.5). Not creatable on Community mongo —
    the verifier reports it unavailable there rather than failing the dev box."""

    field: str
    dimensions: int
    similarity: str
    name: str
    filters: Sequence[str] = ()


@dataclass(frozen=True)
class EncryptedField:
    """A field marked in §6.4's Encryption column.

    `deterministic` only where the field must stay equality-queryable — the
    contact replicas §33.2 reconciles by. Everything else is randomized, which
    is stronger and is the default.

    `key_class` selects the data key. §33.1 requires voice-note audio to sit
    under its own key class, separate from message content.
    """

    path: str
    deterministic: bool = False
    key_class: str = "default"


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    spec_ref: str
    purpose: str
    retention: str
    shard_key: str | None = None
    fields: Mapping[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    indexes: tuple[IndexSpec, ...] = ()
    encrypted: tuple[EncryptedField, ...] = ()
    vector_index: VectorIndexSpec | None = None
    #: Built but unread — §25.7's dark launch. Never means "optional".
    dark: bool = False
    #: Fields that must NEVER appear. Enforced by the validator, not by comment.
    forbidden: tuple[str, ...] = ()
    #: Reject UNDECLARED fields outright (`additionalProperties: false`).
    #: For append-only legal records, where a field nobody declared is a field
    #: nobody reviewed — §37.2's age-gate row is why this exists.
    strict: bool = False
    notes: str = ""

    @property
    def all_fields(self) -> dict[str, Any]:
        return {**BASE_FIELDS, **self.fields}

    @property
    def all_required(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(BASE_REQUIRED + self.required))

    @property
    def encrypted_paths(self) -> frozenset[str]:
        return frozenset(e.path for e in self.encrypted)


def _asc(*names: str) -> list[tuple[str, int]]:
    return [(n, ASCENDING) for n in names]


# ===========================================================================
# §6.4 rows, in table order
# ===========================================================================

SPECS: tuple[CollectionSpec, ...] = (
    CollectionSpec(
        name="users",
        spec_ref="§6.4",
        purpose="Product identity. Mongo _id is immutable and is the product id (§33.2).",
        retention="account life; 30-day soft-delete grace",
        shard_key="hashed(_id)",
        fields={
            "firebase_uid": STR,
            "locale": STR,
            "script_pref": STR,
            "timezone": STR,
            "status": STR,
            # §33.2: contact REPLICAS only — maintained by Firebase webhook and
            # nightly reconciliation, never used to authenticate.
            "email": [STR, BIN],
            "phone": [STR, BIN],
            "deleted_at": [DT, "null"],
        },
        required=("firebase_uid", "locale", "status"),
        indexes=(
            IndexSpec(_asc("firebase_uid"), unique=True),
            # Sparse by construction: phone-only users have no email, and a
            # plain unique index would collide all of them on null.
            IndexSpec(
                _asc("email"),
                unique=True,
                partial={"email": {"$exists": True}},
            ),
            IndexSpec(_asc("locale", "status")),
            IndexSpec(
                _asc("phone"),
                partial={"phone": {"$exists": True}},
                cite="§33.2 — the nightly contact-replica reconciliation looks users up by phone",
            ),
        ),
        # Deterministic is not only about §33.2's lookup — it is what makes
        # §6.4's `uniq email` survive encryption. Randomized ciphertext differs
        # for every write, so the unique index above would still exist and
        # enforce nothing. Changing either of these to randomized silently
        # removes an invariant; a test in test_registry_matches_spec.py refuses
        # a unique index over a randomized field for exactly that reason.
        encrypted=(
            EncryptedField("email", deterministic=True, key_class="contact"),
            EncryptedField("phone", deterministic=True, key_class="contact"),
        ),
    ),
    CollectionSpec(
        name="auth_identities",
        spec_ref="§6.4",
        purpose="Maps many login methods to one user (§33.2).",
        retention="with user",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "provider": STR,
            "provider_uid": STR,
            "verified_at": [DT, "null"],
            "linked_at": [DT, "null"],
        },
        required=("user_id", "provider", "provider_uid"),
        indexes=(
            IndexSpec(_asc("provider", "provider_uid"), unique=True),
            IndexSpec(_asc("user_id")),
        ),
    ),
    CollectionSpec(
        name="profiles",
        spec_ref="§6.4",
        purpose="1:1 with user — persona, priorities, honorific and pronunciation prefs.",
        retention="with user",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "persona": OBJ,
            "priorities": ARR,
            "honorific_prefs": OBJ,
            "name_pronunciation": OBJ,
            # --- the §23.5 preference centre, and what §7.1 schedules from ---
            # §6.4 gives no `preferences` row, and these are 1:1 with the user
            # exactly as `persona` is. `brief_time` is "HH:MM" LOCAL, zero
            # padded, so the string sorts as the clock does and the index below
            # answers the §7.1 lead-window range query without a second field
            # to drift against it.
            "brief_time": STR,
            # §7.1's panchang facts are computed FOR a place, and §30.2 makes
            # that place explicit rather than inferred: the coordinate the
            # user's morning timings are computed at, which Travel Mode moves
            # and `follow_timezone` decides whether to move.
            "brief_place": [OBJ, "null"],
            "density": STR,
            "quiet_hours": OBJ,
            "notification_prefs": OBJ,
            "follow_timezone": BOOL,
        },
        required=("user_id",),
        indexes=(
            IndexSpec(_asc("user_id"), unique=True),
            IndexSpec(
                _asc("brief_time"),
                cite=(
                    "§7.1 — the 15-minute tick selects users whose local brief_time "
                    "falls 90–30 minutes ahead; without this the wave scans every profile"
                ),
            ),
        ),
    ),
    CollectionSpec(
        name="birth_details",
        spec_ref="§6.4",
        purpose=(
            "The crown jewels (§13). CSFLE on the FULL payload; reachable only "
            "through the astrology facade, never a generic query path."
        ),
        retention="with user",
        shard_key="hashed(user_id)",
        fields={
            "user_id": [OID, "null"],
            "family_member_id": [OID, "null"],
            # §6.4 marks the full doc payload encrypted, so each of these is a
            # ciphertext blob at rest and the validator accepts either form.
            "date": [STR, BIN],
            "time": [STR, BIN, "null"],
            "time_accuracy": [STR, BIN],
            "place": [OBJ, BIN],
            "tz_snapshot": [OBJ, BIN],
            "rectification_notes": [STR, BIN, "null"],
        },
        required=("time_accuracy",),
        indexes=(
            IndexSpec(_asc("user_id")),
            IndexSpec(_asc("family_member_id")),
        ),
        encrypted=(
            EncryptedField("date", key_class="birth"),
            EncryptedField("time", key_class="birth"),
            EncryptedField("time_accuracy", key_class="birth"),
            EncryptedField("place", key_class="birth"),
            EncryptedField("tz_snapshot", key_class="birth"),
            EncryptedField("rectification_notes", key_class="birth"),
        ),
    ),
    CollectionSpec(
        name="family_members",
        spec_ref="§6.4",
        purpose="Context only in Phase 1 — no family accounts (§10-19).",
        retention="with owner",
        shard_key="hashed(owner_user_id)",
        fields={
            "owner_user_id": OID,
            "relation": STR,
            "name": [STR, BIN],
            "language_tag": STR,
            "has_birth_details": BOOL,
            # §13: adding a family member's birth details requires attestation.
            "attested_at": [DT, "null"],
        },
        required=("owner_user_id", "relation"),
        indexes=(IndexSpec(_asc("owner_user_id")),),
        encrypted=(EncryptedField("name", key_class="birth"),),
    ),
    CollectionSpec(
        name="charts",
        spec_ref="§6.4",
        purpose="Computed facts embedded (bounded ~40KB); keep last 3 engine versions.",
        retention="recompute on engine bump; keep last 3 versions",
        shard_key="hashed(subject_id)",
        fields={
            "subject_id": OID,
            "engine_version": STR,
            "ayanamsa": STR,
            "facts": [OBJ, ARR, BIN],
            # §34.2: logical keys, NOT foreign keys — there is no facts collection.
            "fact_ids": ARR,
            "parity_status": STR,
        },
        required=("subject_id", "engine_version", "ayanamsa", "parity_status"),
        indexes=(IndexSpec(_asc("subject_id", "engine_version")),),
        encrypted=(EncryptedField("facts", key_class="birth"),),
    ),
    CollectionSpec(
        name="panchang_cache",
        spec_ref="§6.4",
        purpose=(
            "Global, location-keyed calendar cache (§7.2). One row serves every "
            "user in a city on a date — the §7.1 morning burst depends on it."
        ),
        retention="TTL 90 days",
        shard_key="date",
        fields={
            "kind": STR,
            "date": STR,
            "geo": STR,
            "tradition": STR,
            "provider": STR,
            "place_label": STR,
            "place_tz": STR,
            "payload": OBJ,
            "disputed": BOOL,
            "disputed_at": [DT, "null"],
            "adjudication_id": [OID, "null"],
            "cached_at": DT,
            "expires_at": DT,
        },
        required=("kind", "date", "geo", "tradition", "provider", "payload", "expires_at"),
        indexes=(
            # §35.5: muhurat and festival rows share the collection under other
            # §7.2 key grammars, so §6.4's constraint is scoped to the panchang
            # days it was written about.
            IndexSpec(
                _asc("date", "geo", "tradition"),
                unique=True,
                partial={"kind": "panchang"},
                name="uniq_date_geo_tradition_panchang",
            ),
            IndexSpec(_asc("provider")),
            IndexSpec(
                _asc("disputed"),
                cite="§32.2 — the §12 admin dashboard lists disputed rows",
            ),
            IndexSpec(_asc("expires_at"), ttl_seconds=0),
        ),
        notes="M3 built this; M4 extends it with a validator only.",
    ),
    CollectionSpec(
        name="transit_cache",
        spec_ref="§6.4",
        purpose="Global planetary facts per date + latitude band (§7.2).",
        retention="TTL 400 days",
        shard_key="date",
        fields={
            "date": STR,
            "band": STR,
            "engine_semver": STR,
            "payload": [OBJ, ARR],
            "cached_at": DT,
            "expires_at": DT,
        },
        required=("date", "band", "engine_semver", "expires_at"),
        indexes=(
            IndexSpec(
                _asc("date", "band", "engine_semver"),
                unique=True,
                name="uniq_date_band_engine",
                extends=("date", "band"),
                cite=(
                    "§36.1 — extends §6.4's uniq (date,band) with engine_semver because "
                    "§7.2's key grammar is transits:{date}:{lat_band}:{engine_v}; without "
                    "it the second engine version to cache a date+band is rejected and "
                    "every engine bump breaks writes"
                ),
            ),
            IndexSpec(_asc("expires_at"), ttl_seconds=0),
        ),
    ),
    CollectionSpec(
        name="fact_adjudications",
        spec_ref="§6.4 (added by §35.1)",
        purpose=(
            "Layer-D queue (§5.2, §32.2). No user reference — the unit of "
            "comparison is date+place+tradition (§34.2)."
        ),
        retention=(
            "24mo (matches guidance_logs — the audit trail must outlive the guidance "
            "built on the fact)"
        ),
        shard_key=None,
        fields={
            "fact_class": STR,
            "fact_key": STR,
            "served_source": STR,
            "delta_seconds": NUM,
            "tolerance_seconds": NUM,
            # §35.1: readings are EMBEDDED, not referenced — a vendor's answer
            # can change under us and a reviewer must see what we actually got.
            "readings": OBJ,
            "status": STR,
            "kind": STR,
            "place_label": STR,
            "local_date": STR,
        },
        required=("fact_class", "fact_key", "served_source", "readings", "status", "kind"),
        indexes=(
            IndexSpec(_asc("status", "created_at")),
            IndexSpec(_asc("fact_key")),
        ),
    ),
    CollectionSpec(
        name="numerology_profiles",
        spec_ref="§6.4",
        purpose="Chaldean/Pythagorean values per subject.",
        retention="with user",
        shard_key="hashed(subject_id)",
        fields={
            "subject_id": OID,
            "system": STR,
            "values": OBJ,
            "fact_ids": ARR,
        },
        required=("subject_id", "system"),
        indexes=(
            IndexSpec(
                _asc("subject_id", "system"),
                unique=True,
                spec_keys=("subject", "system"),
            ),
        ),
        notes=(
            "§6.4 writes the index as `uniq subject+system`; the stored field is "
            "`subject_id`, matching every other subject reference in the table."
        ),
    ),
    CollectionSpec(
        name="conversations",
        spec_ref="§6.4",
        purpose="Rolling summary + token stats; archived cold after 12mo idle.",
        retention="archive to cold after 12mo idle",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "mode": STR,
            "locale": STR,
            "started_at": DT,
            "summary": [STR, OBJ, "null"],
            "token_stats": OBJ,
        },
        required=("user_id", "mode", "locale", "started_at"),
        indexes=(IndexSpec(_asc("user_id", "started_at")),),
    ),
    CollectionSpec(
        name="messages",
        spec_ref="§6.4",
        purpose=(
            "Transcript store. The six §33.1 audio fields are the explicit field "
            "model that makes voice-note replay honest."
        ),
        retention="raw 24mo then summarised+pruned (user-configurable)",
        shard_key="hashed(conversation_id)",
        fields={
            "conversation_id": OID,
            "role": STR,
            "type": STR,
            "content": [STR, OBJ, BIN],
            "locale": STR,
            # §34.2: logical keys. Snapshots travel with the artefact.
            "fact_ids": ARR,
            "fact_snapshots": ARR,
            "safety_labels": ARR,
            # --- the six §33.1 fields, exactly ---------------------------
            "source_audio_asset_id": [STR, "null"],
            "tts_audio_asset_id": [STR, "null"],
            "transcript_status": STR,
            "source_audio_expires_at": [DT, "null"],
            "source_audio_deleted_at": [DT, "null"],
            "playback_policy": STR,
        },
        required=(
            "conversation_id",
            "role",
            "type",
            "locale",
            "transcript_status",
            "playback_policy",
        ),
        indexes=(IndexSpec(_asc("conversation_id", "created_at")),),
        encrypted=(EncryptedField("content", key_class="message"),),
    ),
    CollectionSpec(
        name="memories",
        spec_ref="§6.4",
        purpose="The 11 types (§32.4) with consent record, visibility gates and decay.",
        retention="until user deletes; consolidation decays",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "type": STR,
            "content": [STR, OBJ, BIN],
            "embedding": [ARR, BIN, "null"],
            # §32.5: a vector is only comparable to vectors from the same
            # model, so the space it came from travels with it. Written since
            # M5-P6b; declared here so the registry stops lagging the writer.
            "embedding_model": [STR, "null"],
            "consent": OBJ,
            "visibility": OBJ,
            "source_message_id": [OID, "null"],
            "decay_score": NUM,
            # Diagram 8's "nightly consolidation: dedupe · decay stale · theme
            # extraction". Decay writes `decay_score` above; the other two write
            # here. Metadata only — cluster id, size, run stamp, and the id of
            # the memory a duplicate was folded into. Nothing derived from
            # content sits in this object, because it is NOT encrypted.
            "consolidation": [OBJ, "null"],
            # The one content-derived output of theme extraction, and therefore
            # top-level and encrypted like `content` itself: a theme name is a
            # summary of what the user told Tara. Nested fields are not reached
            # by the explicit codec (§36.3), which is why this cannot live
            # inside `consolidation`.
            "theme_label": [STR, BIN, "null"],
        },
        required=("user_id", "type", "consent"),
        indexes=(
            IndexSpec(_asc("user_id", "type")),
            IndexSpec(
                [("user_id", ASCENDING), ("decay_score", DESCENDING)],
                spec_keys=("user_id", "decay"),
            ),
        ),
        # §6.4 marks `content` and only `content`. The embedding stays in the
        # clear deliberately: Atlas Vector Search cannot search ciphertext, so
        # encrypting it would silently disable §32.5 retrieval.
        encrypted=(
            EncryptedField("content", key_class="memory"),
            EncryptedField("theme_label", key_class="memory"),
        ),
        vector_index=VectorIndexSpec(
            field="embedding",
            dimensions=1024,  # §32.5 — Cohere embed-multilingual-v3
            similarity="cosine",
            name="memories_vector",
            filters=("user_id", "type"),
        ),
    ),
    CollectionSpec(
        name="daily_briefings",
        spec_ref="§6.4",
        purpose="Modules embedded and bounded; one per user per local date (§32.13).",
        retention="18mo then archive",
        shard_key="date",
        fields={
            "user_id": OID,
            "date": STR,
            "locale": STR,
            "modules": ARR,
            "fact_ids": ARR,
            "confidence": [STR, "null"],
            "audio_ref": [STR, "null"],
            "opened_at": [DT, "null"],
            "status": STR,
            # §32.13: "idempotency key = user + local-date + locale". The
            # UNIQUE index stays (user_id, date) — §32.13 also says one brief
            # per user-local date — so a locale change does not mint a second
            # row for the day. It rewrites this one, and this field is what
            # tells the generator the stored row is for the wrong locale
            # (§32.7: the old-locale brief is discarded, not delivered).
            "idempotency_key": STR,
            # §28.2: density changes the ranking engine's output COUNT, never
            # its facts. Stored so a brief can be explained after the fact.
            "density": STR,
            "tier": STR,
            "generated_at": [DT, "null"],
            #: Set only when §7.1's degrade ran. Null on a normal brief.
            "degrade_reason": [STR, "null"],
        },
        required=("user_id", "date", "locale", "status", "idempotency_key"),
        indexes=(
            IndexSpec(_asc("user_id", "date"), unique=True),
            IndexSpec(_asc("date", "status")),
        ),
    ),
    CollectionSpec(
        name="guidance_logs",
        spec_ref="§6.4",
        purpose=(
            "The audit trail behind every Trust Sheet. The why-payload embeds "
            "full fact snapshots (§34.2), never recomputations."
        ),
        retention="24mo (audit)",
        shard_key="date",
        fields={
            "user_id": OID,
            "date": STR,
            "briefing_id": [OID, "null"],
            "message_id": [OID, "null"],
            "fact_ids": ARR,
            "fact_snapshots": ARR,
            "template_ids": ARR,
            "confidence": STR,
            "why": OBJ,
        },
        required=("user_id", "date", "confidence"),
        indexes=(IndexSpec(_asc("user_id", "date")),),
    ),
    CollectionSpec(
        name="night_reflections",
        spec_ref="§6.4",
        purpose="3 prompts + day summary. No streaks, no guilt (§10-17).",
        retention="with user",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "date": STR,
            "mood": [STR, OBJ, BIN, "null"],
            "entries": [ARR, BIN],
            "memory_chips": ARR,
            "locale": STR,
        },
        required=("user_id", "date", "locale"),
        indexes=(IndexSpec(_asc("user_id", "date"), unique=True),),
        encrypted=(
            EncryptedField("entries", key_class="reflection"),
            EncryptedField("mood", key_class="reflection"),
        ),
    ),
    CollectionSpec(
        name="goals",
        spec_ref="§6.4",
        purpose="User-set intentions with a review date.",
        retention="with user",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "text": STR,
            "status": STR,
            "review_at": [DT, "null"],
        },
        required=("user_id", "text", "status"),
        indexes=(IndexSpec(_asc("user_id", "status")),),
    ),
    CollectionSpec(
        name="notifications",
        spec_ref="§6.4",
        purpose="Max 3/day, quiet hours, localized templates (§23).",
        retention="TTL 180 days",
        shard_key="scheduled_at",
        fields={
            "user_id": OID,
            "channel": STR,
            "template_id": STR,
            "locale": STR,
            "scheduled_at": DT,
            "sent_at": [DT, "null"],
            "opened": BOOL,
            "status": STR,
            "expires_at": DT,
            # §23.7: "the notification worker writes a single source-of-truth
            # `notifications` doc per message (status … provider ids, trigger
            # id, class, locale, template version)". These are those.
            "message_id": STR,
            "message_class": STR,
            "template_version": [STR, "null"],
            "trigger_id": [STR, "null"],
            "provider_message_id": [STR, "null"],
            # §23.4: "Collapse keys ensure a re-generated brief replaces, never
            # duplicates, its push."
            "collapse_key": [STR, "null"],
        },
        required=(
            "user_id",
            "channel",
            "template_id",
            "locale",
            "scheduled_at",
            "expires_at",
            "message_id",
            "message_class",
        ),
        indexes=(
            IndexSpec(_asc("user_id", "scheduled_at")),
            IndexSpec(_asc("status", "scheduled_at")),
            IndexSpec(_asc("expires_at"), ttl_seconds=0),
            IndexSpec(
                _asc("user_id", "message_id"),
                unique=True,
                cite=(
                    "§23.4 — \"delivery is idempotent on `user+message_id` end-to-end\"; "
                    "a duplicate delivery is a release-blocking defect (§23.9)"
                ),
            ),
            IndexSpec(
                _asc("user_id", "collapse_key"),
                partial={"collapse_key": {"$type": "string"}},
                cite=(
                    "§23.4 — the collapse key is looked up to REPLACE a queued push "
                    "when its brief is regenerated (§7.1, §32.7)"
                ),
            ),
        ),
    ),
    CollectionSpec(
        name="voice_sessions",
        spec_ref="§6.4",
        purpose=(
            "Minute metering and latency stats. §13/§33.1: call audio is NEVER "
            "stored — the validator forbids an audio field structurally."
        ),
        retention="metadata 12mo; audio never stored post-transcription (§13)",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "conversation_id": [OID, "null"],
            "minutes": NUM,
            "provider_mix": OBJ,
            "latency_stats": OBJ,
        },
        required=("user_id", "minutes"),
        indexes=(IndexSpec(_asc("user_id", "created_at")),),
        forbidden=("audio_asset_id", "audio_ref", "audio_url", "audio_blob", "recording_ref"),
    ),
    CollectionSpec(
        name="subscriptions",
        spec_ref="§6.4",
        purpose="Plan, region, provider, gift links.",
        retention="financial: 8 years",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "plan": STR,
            "region": STR,
            "provider": STR,
            "status": STR,
            "provider_sub_id": [STR, "null"],
            "gift_links": ARR,
        },
        required=("user_id", "plan", "region", "provider", "status"),
        indexes=(
            # §6.4's `uniq user_id+status active` — one ACTIVE subscription per
            # user; historical cancelled rows are unconstrained.
            IndexSpec(
                _asc("user_id", "status"),
                unique=True,
                partial={"status": "active"},
            ),
            IndexSpec(_asc("provider_sub_id")),
        ),
    ),
    CollectionSpec(
        name="payments",
        spec_ref="§6.4",
        purpose="Provider events. PCI SAQ-A — card data never touches us (§13).",
        retention="8 years (tax)",
        shard_key="created_at",
        fields={
            "user_id": OID,
            "provider": STR,
            "provider_event_id": STR,
            "amount": NUM,
            "currency": STR,
            "invoice_ref": [STR, "null"],
            "instrument_ref": [STR, BIN, "null"],
        },
        required=("user_id", "provider", "provider_event_id", "amount", "currency"),
        indexes=(
            IndexSpec(_asc("user_id", "created_at")),
            IndexSpec(_asc("provider_event_id"), unique=True),
        ),
        encrypted=(EncryptedField("instrument_ref", key_class="payment"),),
    ),
    CollectionSpec(
        name="consents",
        spec_ref="§6.4",
        purpose="The consent ledger — permanent, legal (§13).",
        retention="permanent (legal)",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "type": STR,
            "granted_at": [DT, "null"],
            "revoked_at": [DT, "null"],
            "surface": STR,
        },
        required=("user_id", "type", "surface"),
        indexes=(IndexSpec(_asc("user_id", "type")),),
    ),
    CollectionSpec(
        name="safety_events",
        spec_ref="§6.4",
        purpose="L1–L5 ladder outcomes against a pseudonymised user ref (§9).",
        retention="5 years",
        shard_key="created_at",
        fields={
            "user_ref": STR,
            "level": STR,
            "classifier_scores": [OBJ, BIN],
            "action": STR,
            "review_status": STR,
        },
        required=("user_ref", "level", "action", "review_status"),
        indexes=(
            IndexSpec(_asc("level", "created_at")),
            IndexSpec(_asc("review_status")),
        ),
        encrypted=(EncryptedField("classifier_scores", key_class="safety"),),
    ),
    CollectionSpec(
        name="audit_logs",
        spec_ref="§6.4",
        purpose="Human sensitive actions, append-only (§12).",
        retention="7 years, append-only",
        shard_key="ts",
        # STRICT. An append-only legal log keeps rows for seven years; a field
        # nobody declared is a field nobody reviewed for §13 content, and
        # `age=` reached this collection exactly that way (§37.2).
        strict=True,
        fields={
            "actor": STR,
            "action": STR,
            "target": STR,
            "before_hash": [STR, "null"],
            "after_hash": [STR, "null"],
            "ip": [STR, "null"],
            "ts": DT,
            # §37.2: the corroborated zone set behind an age-gate decision.
            # Zones and provenance only — nothing derived from a birth date.
            "zone_decision": [OBJ, "null"],
            # §13: set by db.redact_age_targets when a legacy `age=` target was
            # rewritten. The row is amended in place, never deleted.
            "redacted_reason": [STR, "null"],
        },
        required=("actor", "action", "target", "ts"),
        indexes=(
            IndexSpec(_asc("actor", "ts")),
            IndexSpec(_asc("target", "ts")),
        ),
    ),
    CollectionSpec(
        name="localized_content",
        spec_ref="§6.4",
        purpose="UI/template/notification/help strings, versioned with sign-off (§2.4).",
        retention="permanent, versioned",
        shard_key=None,
        fields={
            "key": STR,
            "locale": STR,
            "type": STR,
            "value": STR,
            "version": INT,
            "status": STR,
            "sign_off": OBJ,
        },
        required=("key", "locale", "type", "value", "version", "status"),
        indexes=(
            IndexSpec(_asc("key", "locale", "version"), unique=True),
            IndexSpec(_asc("status")),
        ),
    ),
    CollectionSpec(
        name="pronunciation_dictionaries",
        spec_ref="§6.4",
        purpose="Per-locale term → phonetic, with an audio preview (§10-11).",
        retention="permanent",
        shard_key=None,
        fields={
            "locale": STR,
            "term": STR,
            "phonetic": STR,
            "audio_preview_ref": [STR, "null"],
            "status": STR,
        },
        required=("locale", "term", "phonetic", "status"),
        indexes=(IndexSpec(_asc("locale", "term"), unique=True),),
    ),
    # §6.4's final row names two collections: `feature_flags / experiments`.
    CollectionSpec(
        name="feature_flags",
        spec_ref="§6.4",
        purpose="Flag rules per locale and cohort.",
        retention="permanent",
        shard_key=None,
        fields={"key": STR, "rules": [OBJ, ARR], "locales": ARR, "cohorts": ARR},
        required=("key",),
        indexes=(IndexSpec(_asc("key"), unique=True),),
    ),
    CollectionSpec(
        name="experiments",
        spec_ref="§6.4",
        purpose="Experiment definitions — the other half of §6.4's final row.",
        retention="permanent",
        shard_key=None,
        fields={"key": STR, "rules": [OBJ, ARR], "locales": ARR, "cohorts": ARR},
        required=("key",),
        indexes=(IndexSpec(_asc("key"), unique=True),),
    ),
    # =======================================================================
    # Collections the §6.4 table does not list. Each cites what mandates it.
    # =======================================================================
    CollectionSpec(
        name="sessions",
        spec_ref="§22.5 / §34.5",
        purpose="Refresh-token records behind the httpOnly session cookies.",
        retention="with user; expired rows pruned by the refresh path",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "device_name": STR,
            "refresh_hash": STR,
            "prior_refresh_hashes": ARR,
            "refresh_expires_at": DT,
            "revoked_at": [DT, "null"],
            "last_active_at": DT,
        },
        required=("user_id", "refresh_hash"),
        indexes=(
            IndexSpec(_asc("refresh_hash")),
            IndexSpec(_asc("user_id")),
        ),
        notes="Built by M1.",
    ),
    CollectionSpec(
        name="link_conflicts",
        spec_ref="§32.12",
        purpose="One pending account-link choose-flow per user at a time.",
        retention="with user",
        shard_key="hashed(user_id)",
        fields={"user_id": OID, "status": STR},
        required=("user_id", "status"),
        indexes=(IndexSpec(_asc("user_id", "status")),),
        notes="Built by M1.",
    ),
    CollectionSpec(
        name="call_sessions",
        spec_ref="§25.7",
        purpose=(
            "Live-call state machine + summary. §25.7 has it superseding bare "
            "voice_sessions metadata; §13 still forbids storing call audio, so "
            "the validator forbids an audio field here too."
        ),
        retention="metadata 12mo; audio never stored (§13)",
        shard_key="hashed(user_id)",
        fields={
            "user_id": OID,
            "conversation_id": [OID, "null"],
            "voice_session_id": [OID, "null"],
            "state": STR,
            "started_at": DT,
            "ended_at": [DT, "null"],
            "summary": [STR, OBJ, "null"],
            "degrade_reason": [STR, "null"],
        },
        required=("user_id", "state", "started_at"),
        indexes=(
            IndexSpec(
                _asc("user_id", "started_at"),
                cite="§25.7 — per-user call history for the journal and metering",
            ),
            IndexSpec(
                _asc("state"),
                cite="§25.7 — the session state machine reaps stale live sessions",
            ),
        ),
        forbidden=("audio_asset_id", "audio_ref", "audio_url", "audio_blob", "recording_ref"),
    ),
    CollectionSpec(
        name="stories",
        spec_ref="§25.7 / §30.6",
        purpose="Locale-shared programmed cards. P1 gated experiment — dark in P0.",
        retention="with the editorial calendar",
        shard_key=None,
        dark=True,
        fields={
            "template_id": STR,
            "locale": STR,
            "card_type": STR,
            "publish_at": DT,
            "expires_at": DT,
            "approval_state": STR,
            "media_refs": ARR,
            "fact_ids": ARR,
        },
        required=("template_id", "locale", "card_type", "publish_at", "approval_state"),
        indexes=(
            IndexSpec(
                _asc("locale", "publish_at"),
                cite="§25.7 — the scheduler publishes per-locale sets at 05:00 local-region",
            ),
            IndexSpec(
                _asc("approval_state"),
                cite="§25.7 — the §12 Stories module queues cards for Jyotish/ethics approval",
            ),
        ),
    ),
    CollectionSpec(
        name="story_views",
        spec_ref="§25.7",
        purpose="Per-user card views. P1 gated experiment — dark in P0.",
        retention="TTL 90 days",
        shard_key=None,
        dark=True,
        fields={
            "user_id": OID,
            "story_id": OID,
            "completed_at": [DT, "null"],
            "expires_at": DT,
        },
        required=("user_id", "story_id", "expires_at"),
        indexes=(
            IndexSpec(
                _asc("user_id", "story_id"),
                unique=True,
                cite="§25.7 — one view row per user per card",
            ),
            IndexSpec(
                _asc("expires_at"),
                ttl_seconds=0,
                cite="§25.7 — views TTL 90d",
            ),
        ),
    ),
    CollectionSpec(
        name="schema_migrations",
        spec_ref="§14-deploy",
        purpose="expand→migrate→contract ledger and the runner's advisory lock.",
        retention="permanent (deploy history)",
        shard_key=None,
        fields={
            "migration_id": [STR, "null"],
            "phase": [STR, "null"],
            "applied_at": [DT, "null"],
            "checksum": [STR, "null"],
            # the advisory lock row (_id == "lock") uses these two
            "holder": [STR, "null"],
            "acquired_at": [DT, "null"],
        },
        required=(),
        indexes=(
            IndexSpec(
                _asc("applied_at"),
                cite="§14-deploy — the runner reads the ledger in application order",
            ),
        ),
        notes="_id is the migration id (or the literal 'lock' for the run lock).",
    ),
)

BY_NAME: dict[str, CollectionSpec] = {s.name: s for s in SPECS}

#: The key vault lives outside the registry's validator/index machinery —
#: pymongo owns its shape. Named here so verify.py does not call it drift.
KEY_VAULT_NAMESPACE = "__keyvault.datakeys"

#: Collections that exist but are not ours to shape.
EXEMPT_COLLECTIONS: frozenset[str] = frozenset({KEY_VAULT_NAMESPACE.split(".", 1)[1]})


def spec_for(name: str) -> CollectionSpec:
    try:
        return BY_NAME[name]
    except KeyError:  # pragma: no cover - programming error
        raise KeyError(f"{name!r} is not a declared collection (§6.4 registry)") from None


def encrypted_specs() -> tuple[CollectionSpec, ...]:
    return tuple(s for s in SPECS if s.encrypted)


def key_classes() -> tuple[str, ...]:
    """Every distinct CSFLE data-key class the registry asks for.

    §33.1 requires voice-note audio under its own class; it is registered here
    even though no collection field carries it yet, because the asset store
    that will use it is built against these keys.
    """
    classes = {e.key_class for s in SPECS for e in s.encrypted}
    classes.add("voice_audio")  # §33.1 — dedicated key class for original recordings
    return tuple(sorted(classes))
