# Memory Architecture (full spec)

| Type | Format | Consent | Visibility default | Retention | Edit/Delete | Sharing | Sensitivity | Retrieval | AI usage |
|---|---|---|---|---|---|---|---|---|---|
| Profile | structured fields | explicit (forms) | private | until edited | yes/yes | never auto | normal | rule-injected | personalisation |
| Preference | key-value | implicit + notice chip | private | until edited | yes/yes | family opt-in per key | normal | rule-injected | briefs, suggestions |
| Relationship | person graph | explicit | private | until edited | yes/yes | owner-controlled | normal | context-matched | family context |
| Goal | structured | explicit | private | archive on done | yes/yes | opt-in | normal | rule-injected | briefs, check-ins |
| Event | dates+recurrence(+panchang rule) | explicit | family-visible option | recurring | yes/yes | family | normal | calendar | reminders |
| Emotional pattern | derived aggregates only | opt-in | private | 12-mo rolling | view/delete | never | sensitive | weekly jobs only | tone adaptation, wellbeing notes |
| Conversation summary | nightly LLM summary | notice + editable | private | 24 mo default | yes/yes | never | inherits max of sources | pgvector semantic | continuity |
| Family | per-member records | member-owner explicit | per-member level | until edited | owner | levels: private/selected/family | varies | visibility-gated | family features |
| Media (P3) | asset+caption | per-item | per-item | user-set | yes/yes | per-item; child=guardians | varies | album context | captions, albums |
| Sensitive | tagged content | ASK-before-store | private, never family | user-set, suggest 12 mo | yes/yes | never | restricted; field-encrypted | context-matched only; never in notifications | support conversations only |
| Temporary | session context | none needed | n/a | 24h TTL | auto | never | n/a | session only | in-session continuity |

Retrieval logic: (a) rule-injection for structured types; (b) hybrid semantic (embedding cosine × recency decay × importance) top-k=8 over summaries/preferences; (c) sensitivity gate: restricted memories require context-classifier match; (d) family gate: visibility resolution BEFORE embedding search (separate indexes per member).
"What Tara remembers" screen: list+search, per-item source/date, edit/delete/private/expiry, per-type toggles, export, pause, global off. Deletion SLA: index ≤5 min, primary ≤24h, backups ≤30 days (documented in policy).
