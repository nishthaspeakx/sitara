# Analytics Event Taxonomy (PostHog)
Naming: object_action, snake_case. Common props: user_id(hash), plan, cohort_week, platform, app_version, locale. PII never in props; content never logged.

ACQUISITION/AUTH: app_installed · signup_started {method} · signup_completed {method} · session_started
ONBOARDING: onboarding_screen_viewed {ring, step} · onboarding_answer_saved {ring, key(non-sensitive only)} · onboarding_completed {ring, duration_s} · birth_details_added {has_tob} · first_value_reached {seconds_from_signup}
DAY LOOP: brief_generated {modules[]} · brief_push_sent · brief_opened {latency_ms} · brief_rated {1-5} · brief_module_toggled {module, on} · mood_logged {value} · reflection_started · reflection_completed {questions_answered} · weekly_report_viewed
CHAT: conversation_started {framework, entry_point, no_memory} · message_sent {role, has_audio} · framework_switched {from,to,reason} · response_rated {helpful} · voice_note_transcribed {confidence_band}
MEMORY: memory_created {type, consent_state} · memory_chip_viewed · memory_confirmed / memory_declined {type} · memory_edited / memory_deleted {type} · memory_centre_opened · memory_exported · memory_paused {duration} · no_memory_mode_used
GOALS: goal_created / goal_progress / goal_completed / goal_archived
SUBSCRIPTION: paywall_viewed {trigger} · trial_started · checkout_started {plan, period, gateway} · subscription_activated {plan, period} · subscription_cancelled {reason_optional} · subscription_renewed · refund_requested
NOTIFICATIONS: notif_scheduled/sent/opened {type} · notif_prefs_changed {field} · quiet_hours_set
SAFETY (restricted project, hashed ids): safety_flag_raised {severity, category} · crisis_flow_entered · crisis_resource_tapped · safety_review_completed {outcome} · wellbeing_nudge_shown {type}
CONTROLS (positive signals): pause_mode_used · wellbeing_panel_viewed · human_connection_nudge_shown/tapped
COST: llm_call {tokens_in/out, model, cached} (backend metric, not PostHog)
Dashboards map 1:1 to blueprint §18 thresholds; alerts on warning bands.
