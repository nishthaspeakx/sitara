/**
 * Firebase client SDK (§34.5): the ONLY job of Firebase on the client is to
 * produce an ID token for the one-time /auth/session exchange. Persistence is
 * in-memory — the Firebase token is never stored client-side (§34.5).
 */
import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  inMemoryPersistence,
  RecaptchaVerifier,
  setPersistence,
  type Auth,
} from "firebase/auth";

function app(): FirebaseApp {
  const existing = getApps()[0];
  if (existing) return existing;
  return initializeApp({
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  });
}

let authInstance: Auth | null = null;

// Firebase/reCAPTCHA reject unknown language codes with auth/argument-error,
// and "hi-Latn" is not in their set — Hinglish gets Latin-script English for
// provider UI/SMS only. App copy stays fully hi-Latn via the catalogs (§2.4).
const FIREBASE_LANGUAGE: Record<string, string> = { "hi-Latn": "en" };

export function firebaseAuth(locale: string): Auth {
  if (!authInstance) {
    authInstance = getAuth(app());
    void setPersistence(authInstance, inMemoryPersistence);
  }
  authInstance.languageCode = FIREBASE_LANGUAGE[locale] ?? locale;
  return authInstance;
}

/**
 * A RecaptchaVerifier can only ever render once into a given element, so each
 * attempt gets a fresh slot inside the host div (retries/resends otherwise
 * throw "reCAPTCHA has already been rendered in this element").
 */
export function invisibleRecaptcha(auth: Auth, host: HTMLElement): RecaptchaVerifier {
  host.replaceChildren();
  const slot = document.createElement("div");
  host.appendChild(slot);
  return new RecaptchaVerifier(auth, slot, { size: "invisible" });
}

/** §26.1 decision log: Apple sign-in deferred to M+2 — config-flagged slot. */
export const APPLE_SIGNIN_ENABLED =
  process.env.NEXT_PUBLIC_APPLE_SIGNIN_ENABLED === "true";
