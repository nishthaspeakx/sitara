/**
 * §23.5's preference centre and §23.6's push registration, client side.
 *
 * ── The matrix crosses the wire as triples ────────────────────────────────
 *
 * `{category, channel, enabled}`, not `{category: {channel: bool}}`. A nested
 * object makes a missing CHANNEL and a missing CATEGORY two different absences
 * for this file to handle, and S41 renders a grid where every cell exists. One
 * flat list has exactly one absence, and the server fills the rest from the
 * declared defaults.
 *
 * ── `available` is not `enabled`, and conflating them loses a preference ──
 *
 * §23.3's WhatsApp cell is DECLARED — the adapter is not built. Its column
 * still renders, still stores a choice, and is labelled unavailable. A client
 * that inferred availability from the toggle would silently discard the
 * preference of everyone who set it early, and they would find it off on the
 * day the channel finally arrived.
 *
 * ── Nothing here decides what §23 does ────────────────────────────────────
 *
 * No cap is counted here, no quiet-hours window is evaluated, no ladder is
 * built. §32.1's rule about the Today `variant` pointed the other way: the
 * variant is a display rule the client owns, and every rule in §23 is a
 * SENDING decision the server owns. A client that computed "would this send"
 * would be a second implementation of §23, disagreeing exactly on the morning
 * it mattered.
 */

import {
  NOTIFICATION_CATEGORIES,
  NOTIFICATION_CHANNELS,
  type NotificationCategory,
  type NotificationChannel,
} from "@sitara/schemas";

import { apiCall, type ApiResult } from "./api";

export {
  NOTIFICATION_CATEGORIES,
  NOTIFICATION_CHANNELS,
  type NotificationCategory,
  type NotificationChannel,
};

export interface MatrixCell {
  category: NotificationCategory;
  channel: NotificationChannel;
  enabled: boolean;
}

export interface ChannelView {
  channel: NotificationChannel;
  /** §23.3's capability matrix — not the user's choice. */
  available: boolean;
  /** A message key (§2.4), never a sentence. */
  reason_key: string | null;
}

export interface NotificationPreferences {
  matrix: MatrixCell[];
  channels: ChannelView[];
  categories: NotificationCategory[];
  quiet_hours_start: string;
  quiet_hours_end: string;
  brief_time: string;
  paused_until: string | null;
  pause_days: number;
  follow_timezone: boolean;
  home_timezone: string;
  /**
   * §32.6 — set when her brief lands inside her quiet hours AND she has not
   * acknowledged THIS overlap. Non-null again if she later creates a different
   * one, which is what "once" has to mean for a setting that can change.
   */
  overlap_to_flag: string | null;
}

export function loadPreferences(): Promise<ApiResult<NotificationPreferences>> {
  return apiCall<NotificationPreferences>("/v1/notifications/preferences");
}

export function savePreferences(
  update: Partial<{
    matrix: MatrixCell[];
    quiet_hours_start: string;
    quiet_hours_end: string;
    brief_time: string;
    follow_timezone: boolean;
    home_timezone: string;
  }>,
): Promise<ApiResult<NotificationPreferences>> {
  return apiCall<NotificationPreferences>("/v1/notifications/preferences", {
    method: "PUT",
    body: JSON.stringify(update),
  });
}

export function pauseEverything(): Promise<ApiResult<NotificationPreferences>> {
  return apiCall<NotificationPreferences>("/v1/notifications/preferences/pause", {
    method: "POST",
  });
}

/** §29.2: one tap, no confirmation, no minimum. */
export function resumeEverything(): Promise<ApiResult<NotificationPreferences>> {
  return apiCall<NotificationPreferences>("/v1/notifications/preferences/pause", {
    method: "DELETE",
  });
}

/** §32.6's "once" being spent. */
export function acknowledgeOverlap(): Promise<ApiResult<NotificationPreferences>> {
  return apiCall<NotificationPreferences>("/v1/notifications/preferences/overlap-ack", {
    method: "POST",
  });
}

/** Read a cell out of the served triples. Missing reads as OFF, as the server does. */
export function cellEnabled(
  preferences: NotificationPreferences,
  category: NotificationCategory,
  channel: NotificationChannel,
): boolean {
  return (
    preferences.matrix.find((c) => c.category === category && c.channel === channel)
      ?.enabled ?? false
  );
}

export function channelAvailable(
  preferences: NotificationPreferences,
  channel: NotificationChannel,
): boolean {
  return preferences.channels.find((c) => c.channel === channel)?.available ?? false;
}

// ---------------------------------------------------------------------------
// §23.6 / §6.2 — the browser's own Push API
// ---------------------------------------------------------------------------

/**
 * Subscribe this browser, or report honestly why not.
 *
 * Three things it deliberately does NOT do:
 *
 * **It never prompts on load.** `Notification.requestPermission()` must be
 * called from a user gesture — S41's own toggle — because a permission prompt
 * on arrival is denied by reflex and a denial is sticky. iOS additionally
 * requires an INSTALLED PWA (§6.2, ≥16.4), so `PushManager` is simply absent
 * in Safari until then; that is a state to explain, not an error.
 *
 * **It re-subscribes silently when it can.** §23.6's "silent re-subscribe
 * attempt on next app open" — if permission is already granted, this needs no
 * prompt at all, and the endpoint it gets back is the same one, which is why
 * the server upserts on it.
 *
 * **It sends nothing until the server has a key.** The VAPID public key is
 * fetched first; a null one means push is unconfigured in this deployment and
 * §23.3's ladder is already carrying the messages elsewhere.
 */
export type PushSubscribeOutcome =
  | { kind: "subscribed" }
  | { kind: "unsupported" }
  | { kind: "unconfigured" }
  | { kind: "denied" }
  | { kind: "failed" };

export async function subscribeToPush(): Promise<PushSubscribeOutcome> {
  if (
    typeof window === "undefined" ||
    !("serviceWorker" in navigator) ||
    !("PushManager" in window)
  ) {
    return { kind: "unsupported" };
  }

  const key = await apiCall<{ public_key: string | null }>("/v1/notifications/push/key");
  if (!key.ok || !key.data.public_key) return { kind: "unconfigured" };

  const permission =
    Notification.permission === "granted"
      ? "granted"
      : await Notification.requestPermission();
  if (permission !== "granted") return { kind: "denied" };

  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      // Required by every browser: a push with no payload visible to the user
      // is one the UA may drop, and Chrome refuses the subscription outright.
      userVisibleOnly: true,
      applicationServerKey: base64UrlToUint8Array(key.data.public_key),
    });
    const json = subscription.toJSON();
    const result = await apiCall("/v1/notifications/push", {
      method: "POST",
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        p256dh: json.keys?.p256dh,
        auth: json.keys?.auth,
        user_agent: navigator.userAgent.slice(0, 400),
      }),
    });
    return result.ok ? { kind: "subscribed" } : { kind: "failed" };
  } catch {
    return { kind: "failed" };
  }
}

/**
 * §23.6's explicit unsubscribe — the browser telling us it is going away.
 *
 * Deliberately different from the server concluding a subscription is dead: a
 * dead row drives a re-subscribe prompt and a removed one does not, and
 * offering to re-enable push to somebody who just switched it off is exactly
 * the nagging §29.2 forbids.
 */
export async function unsubscribeFromPush(): Promise<boolean> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return false;
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return false;
  await apiCall("/v1/notifications/push", {
    method: "DELETE",
    body: JSON.stringify({ endpoint: subscription.endpoint }),
  });
  await subscription.unsubscribe();
  return true;
}

/**
 * `applicationServerKey` wants raw bytes, and the server serves base64url.
 *
 * Written out rather than `atob`-and-hope: base64url uses `-`/`_` where base64
 * uses `+`/`/`, and `atob` on an unconverted key produces 65 wrong bytes rather
 * than an error. The subscription then succeeds, every push is signed with a
 * key the browser does not recognise, and the push service returns 403 — which
 * `webpush.py` correctly classifies as REJECTED rather than a dead token, so
 * nothing self-heals and nothing is logged as broken.
 */
function base64UrlToUint8Array(value: string): ArrayBuffer {
  const padded = value.padEnd(value.length + ((4 - (value.length % 4)) % 4), "=");
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  // The BUFFER, not the view. `applicationServerKey` is typed `BufferSource`
  // and TS 5.7 narrowed `Uint8Array` to carry its buffer type — a plain
  // `Uint8Array` is `ArrayBufferLike`, which admits `SharedArrayBuffer` and is
  // therefore not assignable. Both are accepted at runtime.
  return bytes.buffer;
}
