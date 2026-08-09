/**
 * In-memory hand-off between S03 (auth) and S04 (verify).
 *
 * A pending verification is not serialisable — the real one closes over a
 * Firebase `ConfirmationResult` — and nothing auth-related may touch client
 * storage at all (§34.5). A hard reload restarts from S03, which is correct:
 * the code was sent to a phone, and the phone still has it.
 *
 * The type is the `PendingVerification` from `auth-client`, not Firebase's, so
 * this module has no opinion about which implementation produced it.
 */
import type { PendingVerification } from "./auth-client";

type Pending = { phone: string; confirmation: PendingVerification };

let pendingPhone: Pending | null = null;

export function setPendingPhone(phone: string, confirmation: PendingVerification): void {
  pendingPhone = { phone, confirmation };
}

export function getPendingPhone(): Pending | null {
  return pendingPhone;
}

export function clearPendingAuth(): void {
  pendingPhone = null;
}
