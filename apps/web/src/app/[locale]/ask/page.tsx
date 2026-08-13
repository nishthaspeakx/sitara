"use client";

/**
 * S18 Ask Tara — §29.1's `/ask`, wired to the §34.6 socket.
 *
 * This file is the wiring and nothing else: open the socket, feed its events
 * into the reducer, hand the state to `AskScreen`. Every rule lives somewhere
 * testable without a browser, the way `today/page.tsx` is arranged.
 *
 * **The handoff is a real transport change, not a message.** When the socket
 * gives up (§34.6's five minutes), the thread keeps working over
 * `POST /v1/chat/turn` — the same pipeline, the same `ChatTurn`. That is what
 * makes §32.11's "full transcript continuity" true rather than claimed, and it
 * is why the API serves one shape on both transports.
 */

import { useLocale } from "next-intl";
import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type { ChatTurn, MemoryChipOffer } from "@sitara/schemas";

import { AskScreen } from "@/components/ask/AskScreen";
import { useRouter } from "@/i18n/navigation";
import { apiCall } from "@/lib/api";
import { ChatSocket } from "@/lib/chat-socket";
import { EMPTY_THREAD, threadReducer } from "@/lib/chat-thread";
import { useVoiceNote } from "@/lib/use-voice-note";

/**
 * One conversation per browser session, so a reload continues the thread the
 * server already has. §6.4 types `messages.conversation_id` as an objectId, so
 * this is a 24-hex id rather than a readable slug — a friendlier one would be
 * rejected by the collection validator at the first write.
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

let counter = 0;
function clientMessageId(): string {
  counter += 1;
  return `m${counter}-${Date.now()}`;
}

export default function AskPage() {
  const router = useRouter();
  // `useLocale`, not a `params` prop: Next 15 made `params` a Promise, and this
  // is a client component that would have to unwrap it for no gain — the
  // locale is already in the provider every string on the screen reads from.
  const locale = useLocale();
  const [thread, dispatch] = useReducer(threadReducer, EMPTY_THREAD);
  const socket = useRef<ChatSocket | null>(null);
  const conversation = useMemo(
    () => (typeof window === "undefined" ? "" : conversationId()),
    [],
  );

  useEffect(() => {
    if (!conversation) return;
    const client = new ChatSocket(conversation, locale, {
      onEvent: (event) => dispatch({ type: "event", event, at: Date.now() }),
      // EVERY close, not only the last one. This used to fire on `!willRetry`,
      // which meant a socket that died with a question in flight left the
      // bubble on `sending` through five reconnect attempts — 36 seconds of a
      // message that looks like it is still going somewhere. `ask-socket.spec`
      // caught it, which is the whole reason that spec drops a real socket
      // rather than faking one.
      //
      // A reconnect does not rescue that turn either: the resume buffer holds
      // COMPLETED turns, and this one never completed. So the honest state is
      // failed-with-a-retry immediately, and a later `resume.offer` still
      // heals the bubble if the turn did land server-side after all.
      onClosed: () => dispatch({ type: "socket_lost", at: Date.now() }),
    });
    socket.current = client;
    void client.connect();
    return () => {
      client.close();
      socket.current = null;
    };
  }, [conversation, locale]);

  /** §32.11's handoff path: the same turn, over the plain door. */
  const sendOverHttp = useCallback(
    async (text: string, id: string, quotedId?: string) => {
      const result = await apiCall<ChatTurn>("/v1/chat/turn", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: conversation,
          text,
          locale,
          quoted_message_id: quotedId ?? null,
        }),
      });
      if (result.ok) {
        dispatch({ type: "handoff_reply", turn: result.data, replyTo: id, at: Date.now() });
      } else {
        dispatch({
          type: "handoff_failed",
          replyTo: id,
          error: { code: result.error.code, message_key: result.error.message_key },
        });
      }
    },
    [conversation, locale],
  );

  const send = useCallback(
    (text: string, quotedId?: string) => {
      const id = clientMessageId();
      dispatch({ type: "send", id, text, at: Date.now(), quotedId });
      const sentOnSocket = socket.current?.send(text, id, quotedId) ?? false;
      if (!sentOnSocket) void sendOverHttp(text, id, quotedId);
    },
    [sendOverHttp],
  );

  const retry = useCallback(
    (id: string) => {
      const message = thread.messages.find((m) => m.id === id);
      if (!message || message.kind !== "user") return;
      dispatch({ type: "send", id: `${id}r`, text: message.text, at: Date.now() });
      const sent = socket.current?.send(message.text, `${id}r`, message.quotedId) ?? false;
      if (!sent) void sendOverHttp(message.text, `${id}r`, message.quotedId);
    },
    [thread.messages, sendOverHttp],
  );

  /**
   * §25.4's voice note. The bubble is created HERE, at `speech_start`, so every
   * PCM frame already belongs to a message the thread is drawing — the
   * transcript then fills a bubble that exists instead of appearing from
   * nowhere seconds later on `captions.final`.
   */
  const voice = useVoiceNote({
    socket,
    mintId: clientMessageId,
    onSpeak: (id, durationMs, quoted) =>
      dispatch({ type: "speak", id, at: Date.now(), durationMs, quotedId: quoted }),
  });

  const acceptMemory = useCallback(
    (offer: MemoryChipOffer, summary: string) => {
      // §32.4: the chip IS the consent, and the record travels with the write —
      // `MemoryStore.create` has no path that stores content without one.
      void apiCall("/v1/memories", {
        method: "POST",
        body: JSON.stringify({
          type: offer.type,
          content: summary,
          locale,
          consent: { source: "chat_chip", reconfirmed: offer.requires_reconfirmation },
        }),
      });
    },
    [locale],
  );

  return (
    <AskScreen
      thread={thread}
      locale={locale}
      onSend={send}
      onRetry={retry}
      onSelectTab={(tab) => router.push(`/${tab}`)}
      onGetHelp={() => router.push("/you/help")}
      onAcceptMemory={acceptMemory}
      onDeclineMemory={() => {}}
      voice={voice}
    />
  );
}
