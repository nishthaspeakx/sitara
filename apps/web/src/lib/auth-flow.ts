/**
 * In-memory hand-off between S03 (auth) and S04 (verify) — a Firebase
 * ConfirmationResult is not serialisable, and nothing auth-related may touch
 * client storage (§34.5). A hard reload simply restarts from S03 (§24.4
 * resume-from-step behaviour arrives with the full onboarding state machine).
 */
import type { ConfirmationResult } from "firebase/auth";

type PendingPhone = { phone: string; confirmation: ConfirmationResult };

let pendingPhone: PendingPhone | null = null;

export function setPendingPhone(phone: string, confirmation: ConfirmationResult): void {
  pendingPhone = { phone, confirmation };
}

export function getPendingPhone(): PendingPhone | null {
  return pendingPhone;
}

export function clearPendingAuth(): void {
  pendingPhone = null;
}
