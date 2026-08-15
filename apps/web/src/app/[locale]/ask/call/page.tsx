"use client";

/**
 * §25.3's screen 17, wired to the §34.6 call socket.
 *
 * Wiring and nothing else, the way `ask/page.tsx` and `today/page.tsx` are
 * arranged: open the socket, feed its events into the reducer, hand the state
 * to `CallScreen`. Every rule that could be wrong lives in `lib/call-state.ts`,
 * where it is checkable with no browser.
 *
 * **The handoff is a real navigation, not a message.** §25.3's degrade ladder
 * ends in "switching to chat with full transcript continuity", and the
 * continuity is real for a structural reason rather than a copywriting one:
 * the API commits every spoken turn to `messages` as it happens, so `/ask` is
 * already showing the whole call by the time this screen offers the link. There
 * is nothing to carry across.
 *
 * The conversation id is SHARED with `/ask` through the same session key, which
 * is what makes that true — a call in its own conversation would produce a
 * thread the user could not find.
 */

import { useLocale } from "next-intl";
import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import { CallScreen } from "@/components/call/CallScreen";
import { ErrorState } from "@/components/ui/ErrorState";
import { useRouter } from "@/i18n/navigation";
import { CallSocket } from "@/lib/call-socket";
import { IDLE_CALL, callReducer } from "@/lib/call-state";

/**
 * The same key `ask/page.tsx` uses, deliberately. §29's channel table puts a
 * call in the SAME thread ("call block in same thread: 📞 12 min · summary +
 * expandable transcript"), so a call and the chat before it are one
 * conversation or the promise of continuity is not one.
 */
function conversationId(): string {
  const key = "sitara.conversation_id";
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  const id = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  window.sessionStorage.setItem(key, id);
  return id;
}

export default function CallPage() {
  const router = useRouter();
  const locale = useLocale();
  const [model, dispatch] = useReducer(callReducer, IDLE_CALL);
  const socket = useRef<CallSocket | null>(null);
  const conversation = useMemo(
    () => (typeof window === "undefined" ? "" : conversationId()),
    [],
  );

  useEffect(() => {
    if (!conversation) return;
    const client = new CallSocket(conversation, locale, {
      onEvent: (event) => dispatch({ type: "event", event, at: Date.now() }),
      onGrant: (grant) =>
        dispatch({
          type: "grant",
          plan: {
            plan: grant.entitlement.plan,
            unlimited: grant.entitlement.unlimited,
            minutesLeft: grant.entitlement.minutes_left,
            minutesQuota: grant.entitlement.minutes_quota,
          },
          // §25.3: live captions on for a first call. The SERVER decides —
          // it knows whether this account has ever metered a minute, and a
          // client-side "have I called before?" would reset with storage.
          captionsOn: grant.captions_default_on,
        }),
      onClosed: () => dispatch({ type: "socket_lost", at: Date.now() }),
      onRefused: (error) =>
        dispatch({
          type: "event",
          at: Date.now(),
          event: { type: "error", seq: 0, ts: Date.now(), ack: null, payload: { ...error } },
        }),
    });
    socket.current = client;
    void client.connect();
    return () => {
      client.close();
      socket.current = null;
    };
  }, [conversation, locale]);

  // `toggle` must not close over `model`: a callback rebuilt on every render
  // would churn the socket effect above. A ref carries the one value it needs.
  const mutedRef = useRef(model.muted);
  mutedRef.current = model.muted;

  const toggle = useCallback((control: "muted" | "speakerOn" | "captionsOn") => {
    dispatch({ type: "toggle", control });
    // Mute is client-hard (§25.3): the socket stops SENDING frames rather than
    // flagging them, so there is no server-side mute that could fail to hold.
    if (control === "muted") socket.current?.setMuted(!mutedRef.current);
  }, []);

  const end = useCallback(() => {
    socket.current?.close();
    dispatch({ type: "end", at: Date.now() });
    router.push("/ask");
  }, [router]);

  if (model.error && model.state === "connecting") {
    // §33.5's flag, CC-010's locale ruling and an exhausted §7.3 pool all land
    // here. Each is a reason with its own in-locale sentence, and none of them
    // is retryable — `ErrorState` renders no retry control for those, which is
    // exactly right: pressing it again would not make Hindi calls exist.
    return (
      <ErrorState
        error={{
          code: model.error.code,
          message_key: model.error.message_key,
          trace_id: "",
          retryable: false,
        }}
      />
    );
  }

  return (
    <CallScreen
      model={model}
      onToggle={toggle}
      onEnd={end}
      onMinimise={() => router.push("/ask")}
      onOpenThread={() => router.push("/ask")}
      onDismissWarning={() => dispatch({ type: "dismiss_warning" })}
      onResume={() => void socket.current?.connect()}
    />
  );
}
