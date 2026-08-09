"use client";

/**
 * The onboarding stack's client state and its API client (§24.4, §28.1).
 *
 * §24.4 requires "state persisted per step (resume on return)", and the server
 * is where that lives — each screen commits its own answer as it is completed.
 * This store is the IN-FLIGHT copy: what the user has typed on the screen they
 * are on, plus whatever the resume call told us. A reinstall loses the store
 * and loses nothing, which is the test of whether it is holding the right
 * things.
 *
 * What it deliberately never holds: the birth date, time or place after they
 * have been committed. Those go to the server through §13's facade and are not
 * read back (see `services/api/src/sitara_api/onboarding/service.py`); keeping
 * a second copy in a client store would recreate the generic read path the
 * server refuses to offer.
 */

import { create } from "zustand";

import type { ErrorEnvelope } from "@sitara/schemas";

/** §24.4's thirteen. S01 answers nothing, so the stack starts at S02. */
export const STEPS = {
  LANGUAGE: 2,
  AUTH: 3,
  VERIFY: 4,
  CONSENT: 5,
  BIRTH: 6,
  BIRTH_TIME: 7,
  CITY: 8,
  INTEREST: 9,
  NAME: 10,
  PRIORITIES: 11,
  VOICE: 12,
  READING: 13,
} as const;

/** In flow order — `start/layout.tsx` walks this for back and resume. */
export const STEP_ROUTES: Record<number, string> = {
  2: "/start/language",
  3: "/start/auth",
  4: "/start/verify",
  5: "/start/consent",
  6: "/start/birth",
  7: "/start/birth/time",
  8: "/start/city",
  9: "/start/interest",
  10: "/start/name",
  11: "/start/priorities",
  12: "/start/voice",
  13: "/start/reading",
};

export type TimeAccuracy = "exact" | "approximate" | "part_of_day" | "unknown";
export type PartOfDay = "morning" | "afternoon" | "evening" | "night";
export type Interest = "curious" | "balanced" | "devout";

export interface Place {
  id?: string;
  label: string;
  lat: number;
  lon: number;
  tz: string;
}

export interface OnboardingState {
  /** Server-known progress, refreshed by `resume()`. */
  completedSteps: number[];
  nextStep: number;
  hasBirthDetails: boolean;

  /** In-flight answers, cleared once committed where they must not persist. */
  birthDate: string;
  birthPlace: Place | null;
  timeAccuracy: TimeAccuracy | null;
  birthTime: string;
  partOfDay: PartOfDay | null;
  city: Place | null;
  interest: Interest | null;
  displayName: string;
  latinName: string;
  priorities: string[];
  briefTime: string;
  voiceEnabled: boolean;

  set(patch: Partial<OnboardingState>): void;
  markComplete(step: number): void;
  reset(): void;
}

export const useOnboarding = create<OnboardingState>((set) => ({
  completedSteps: [],
  nextStep: STEPS.LANGUAGE,
  hasBirthDetails: false,

  birthDate: "",
  birthPlace: null,
  timeAccuracy: null,
  birthTime: "",
  partOfDay: null,
  city: null,
  interest: null,
  displayName: "",
  latinName: "",
  priorities: [],
  briefTime: "07:00",
  voiceEnabled: true,

  set: (patch) => set(patch),
  markComplete: (step) =>
    set((s) =>
      s.completedSteps.includes(step)
        ? s
        : { completedSteps: [...s.completedSteps, step].sort((a, b) => a - b) },
    ),
  reset: () =>
    set({
      completedSteps: [],
      nextStep: STEPS.LANGUAGE,
      hasBirthDetails: false,
      birthDate: "",
      birthPlace: null,
      timeAccuracy: null,
      birthTime: "",
      partOfDay: null,
      city: null,
      interest: null,
      displayName: "",
      latinName: "",
      priorities: [],
      briefTime: "07:00",
      voiceEnabled: true,
    }),
}));

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

const FALLBACK: ErrorEnvelope = {
  code: "SYS_UNAVAILABLE",
  message_key: "errors.sys.unavailable",
  trace_id: "",
  retryable: true,
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ErrorEnvelope };

/**
 * Every call goes to the same-origin `/v1` proxy so §34.5's httpOnly session
 * cookie is first-party and actually rides along. A network failure becomes a
 * §34.4 envelope rather than a thrown exception, because every screen renders
 * an envelope and none of them should need a try/catch.
 */
async function call<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`/v1${path}`, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const body = response.status === 204 ? null : await response.json();
    if (response.ok) return { ok: true, data: body as T };
    return { ok: false, error: body as ErrorEnvelope };
  } catch {
    return { ok: false, error: FALLBACK };
  }
}

export interface ServerState {
  locale: string;
  completed_steps: number[];
  next_step: number;
  has_birth_details: boolean;
  time_accuracy: TimeAccuracy | null;
  has_city: boolean;
  interest: Interest | null;
  priorities: string[];
  display_name: string | null;
  brief_time: string | null;
  voice_enabled: boolean;
}

export function fetchState(signal?: AbortSignal) {
  return call<ServerState>("/onboarding", { signal });
}

export function patchState(patch: Record<string, unknown>) {
  return call<ServerState>("/onboarding", { method: "PATCH", body: JSON.stringify(patch) });
}

export function postConsents(types: string[]) {
  return call<ServerState>("/onboarding/consents", {
    method: "POST",
    body: JSON.stringify({ types }),
  });
}

export function putBirth(payload: {
  date: string;
  place: Place;
  time_accuracy: TimeAccuracy;
  time?: string | null;
  part_of_day?: PartOfDay | null;
}) {
  return call<ServerState>("/onboarding/birth", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function searchPlaces(query: string, signal?: AbortSignal) {
  return call<Place[]>(`/places?q=${encodeURIComponent(query)}`, { signal });
}

// ---------------------------------------------------------------------------
// S13
// ---------------------------------------------------------------------------

export type LineId = "moon_nakshatra" | "observation" | "panchang";
export type DegradeReason =
  | "timeout"
  | "insufficient_birth_data"
  | "engine_unavailable"
  | "panchang_unavailable";

export interface ReadingLine {
  id: LineId;
  values: Record<string, string>;
  fact_ids: string[];
  confidence: string;
  house: number | null;
}

export type SourceState = "default" | "single" | "disputed";

export interface Reading {
  status: "complete" | "partial" | "unavailable";
  confidence: string;
  /** §30.4 — what the source row may claim today. Never assumed by the client. */
  source_state: SourceState;
  lines: ReadingLine[];
  facts: unknown[];
  missing: string[];
  degrade_reason: DegradeReason | null;
}

export function fetchFirstReading(signal?: AbortSignal) {
  return call<Reading>("/readings/first", { method: "POST", signal });
}

/**
 * §24.4's "skeleton→content ≤400ms" cannot be met by waiting on an engine, and
 * a hung request is the failure S13 must never show. Six seconds is the product
 * default; the flow suite overrides it so the timeout path is testable in
 * seconds rather than in the six the user actually waits.
 */
export const CEREMONY_DEADLINE_MS = Number(
  process.env.NEXT_PUBLIC_CEREMONY_DEADLINE_MS ?? 6000,
);
