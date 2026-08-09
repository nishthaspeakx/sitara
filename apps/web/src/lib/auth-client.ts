/**
 * The auth surface S03 and S04 actually depend on (§34.5, §37.2 phone-first).
 *
 * Introduced in M8 for a reason worth stating plainly: the onboarding flow tests
 * must drive the REAL screens — the real form, the real error rendering, the
 * real navigation — and `signInWithPhoneNumber` cannot run in CI. It needs a
 * live Firebase project, a reCAPTCHA that talks to Google, and an SMS. Mocking
 * `firebase/auth`'s module surface inside a browser test would mean the test
 * knew more about Firebase than the screens do.
 *
 * So the screens talk to this interface, and the interface has two
 * implementations: the real one (Firebase, always used in dev, staging and
 * production) and a fake one selected ONLY by an explicit build-time flag. The
 * live-path acceptance run uses the real one with the real test number.
 *
 * What does NOT change between them: the ID token is produced once, exchanged
 * once at `/auth/session`, and never stored client-side (§34.5). The fake mints
 * a token the API will reject; a flow test stubs the exchange, and a real run
 * never loads the fake at all.
 */
import { FirebaseError } from "firebase/app";
import {
  GoogleAuthProvider,
  signInWithPhoneNumber,
  signInWithPopup,
  type ConfirmationResult,
} from "firebase/auth";

import { firebaseAuth, invisibleRecaptcha } from "./firebase";

/** What S04 holds between "code sent" and "code entered". */
export interface PendingVerification {
  phone: string;
  /** Resolves to a Firebase ID token; rejects with a FirebaseError-shaped code. */
  confirm(code: string): Promise<string>;
}

export interface AuthClient {
  startPhoneSignIn(phone: string, host: HTMLElement, locale: string): Promise<PendingVerification>;
  signInWithGoogle(locale: string): Promise<string>;
  /** The token for a session already established in this tab, or null. */
  currentIdToken(locale: string): Promise<string | null>;
}

// ---------------------------------------------------------------------------
// Real — Firebase
// ---------------------------------------------------------------------------

function wrap(phone: string, confirmation: ConfirmationResult): PendingVerification {
  return {
    phone,
    async confirm(code) {
      const credential = await confirmation.confirm(code.trim());
      return credential.user.getIdToken();
    },
  };
}

const firebaseClient: AuthClient = {
  async startPhoneSignIn(phone, host, locale) {
    const auth = firebaseAuth(locale);
    const verifier = invisibleRecaptcha(auth, host);
    return wrap(phone, await signInWithPhoneNumber(auth, phone, verifier));
  },
  async signInWithGoogle(locale) {
    const credential = await signInWithPopup(firebaseAuth(locale), new GoogleAuthProvider());
    return credential.user.getIdToken();
  },
  async currentIdToken(locale) {
    const user = firebaseAuth(locale).currentUser;
    return user ? user.getIdToken() : null;
  },
};

// ---------------------------------------------------------------------------
// Fake — flow tests only
// ---------------------------------------------------------------------------

/** The dev/test OTP. Matches the Firebase test number's fixed code. */
const TEST_OTP = "123456";

const fakeClient: AuthClient = {
  async startPhoneSignIn(phone) {
    return {
      phone,
      async confirm(code) {
        if (code.trim() !== TEST_OTP) {
          // The same code path a wrong OTP takes for real, so the test
          // exercises S04's real error rendering rather than a bespoke one.
          throw new FirebaseError("auth/invalid-verification-code", "wrong code");
        }
        return "fake-id-token";
      },
    };
  },
  async signInWithGoogle() {
    return "fake-id-token";
  },
  async currentIdToken() {
    return "fake-id-token";
  },
};

/**
 * `fake` requires an explicit opt-in at build time. There is no runtime toggle
 * and no automatic "if no Firebase key, fake it": a production build with a
 * missing key must fail loudly at sign-in, not quietly accept everybody.
 */
export const authClient: AuthClient =
  process.env.NEXT_PUBLIC_AUTH_ADAPTER === "fake" ? fakeClient : firebaseClient;

export const AUTH_IS_FAKE = process.env.NEXT_PUBLIC_AUTH_ADAPTER === "fake";
