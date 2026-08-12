"use client";

/**
 * S18 Ask Tara (§29.1) — §25.4's chat, on the §34.6 socket.
 *
 * Composition only. Every rule worth testing lives somewhere it can be tested
 * without a browser: the thread's behaviour in `lib/chat-thread.ts`, the
 * protocol in `lib/chat-socket.ts`, §30.4's three layers on the server.
 *
 * Two decisions this file does make, and both are §-driven:
 *
 * **L3+ replaces the screen** (§22.9, §29.1). Not a banner over the thread —
 * a takeover. The comparison is the schema's declared
 * `SAFETY_TAKEOVER_FROM_ORDINAL`, so client and server cannot disagree about
 * what L3+ means. While it is up, the TabBar is not rendered: §29.1 says the
 * takeover "exits only to Ask Tara or Help", and a tab bar is four other exits.
 *
 * **The wallpaper is a token surface with no text on it.** `sky.ts` documents
 * the six contrast failures behind that rule; the constellation is a background
 * layer and every word sits on `bg-canvas` or on a bubble.
 */

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChatCitation, MemoryChipOffer, PresenceState } from "@sitara/schemas";
import { SAFETY_LEVEL_ORDINAL, SAFETY_TAKEOVER_FROM_ORDINAL } from "@sitara/schemas";

import { Card, ErrorState, TabBar, TrustSheet } from "@/components/ui";
import type { Message, ThreadState } from "@/lib/chat-thread";

import { ChatHeader } from "./ChatHeader";
import { Composer } from "./Composer";
import { MemoryChipHost, type ChipDecision } from "./MemoryChipHost";
import { MessageList } from "./MessageList";
import { SafetyTakeover } from "./SafetyTakeover";
import { Wallpaper } from "./Wallpaper";

/** §4.3 presence → §25.4's two indicator labels. */
function indicatorFor(presence: PresenceState | null): "ui.ask.typing" | "ui.ask.listening" | null {
  if (presence === null) return null;
  if (presence === "listening") return "ui.ask.listening";
  if (presence === "thoughtful" || presence === "speaking_soft") return "ui.ask.typing";
  return null;
}

/** The most recent turn's rung, which is what the screen reacts to. */
function takenOver(messages: Message[]): boolean {
  const last = [...messages].reverse().find((m) => m.kind === "tara");
  if (!last || last.kind !== "tara") return false;
  return SAFETY_LEVEL_ORDINAL[last.turn.safety_level] >= SAFETY_TAKEOVER_FROM_ORDINAL;
}

const SUGGESTIONS = [
  "ui.ask.suggestion_day",
  "ui.ask.suggestion_timing",
  "ui.ask.suggestion_number",
] as const;

export function AskScreen({
  thread,
  locale,
  night = false,
  onSend,
  onRetry,
  onSelectTab,
  onGetHelp,
  onAcceptMemory,
  onDeclineMemory,
}: {
  thread: ThreadState;
  locale: string;
  /**
   * §25.4's dusk variant. DATA, never `new Date()` here — the Today screen
   * records why (`local_time` comes from the payload): a screen that reads the
   * browser clock renders a different variant than the server composed for,
   * and every baseline then depends on when CI happened to run.
   */
  night?: boolean;
  onSend: (text: string, quotedId?: string) => void;
  onRetry: (id: string) => void;
  onSelectTab: (tab: string) => void;
  onGetHelp: () => void;
  onAcceptMemory: (offer: MemoryChipOffer, summary: string) => void;
  onDeclineMemory: (offer: MemoryChipOffer) => void;
}) {
  const t = useTranslations();
  const [openCitation, setOpenCitation] = useState<ChatCitation | null>(null);
  const [quotedId, setQuotedId] = useState<string | null>(null);
  const [chipDecisions, setChipDecisions] = useState<Record<string, ChipDecision>>({});
  const [dismissedTakeover, setDismissedTakeover] = useState(false);
  const lastTakeover = useRef(false);

  const isTakeover = takenOver(thread.messages);
  useEffect(() => {
    // A NEW L3+ turn re-raises the takeover even if the user dismissed the
    // last one. Left sticky, a second crisis turn would land silently in a
    // thread the user had already dismissed their way out of.
    if (isTakeover && !lastTakeover.current) setDismissedTakeover(false);
    lastTakeover.current = isTakeover;
  }, [isTakeover]);

  const presenceState: PresenceState = useMemo(() => {
    const last = [...thread.messages].reverse().find((m) => m.kind === "tara");
    return last && last.kind === "tara" ? last.turn.presence_state : "profile_portrait";
  }, [thread.messages]);

  const lastTara = [...thread.messages].reverse().find((m) => m.kind === "tara");
  const offers = lastTara?.kind === "tara" ? lastTara.turn.memory_chips : [];

  if (isTakeover && !dismissedTakeover) {
    return (
      <SafetyTakeover
        onBackToTara={() => setDismissedTakeover(true)}
        onGetHelp={onGetHelp}
      />
    );
  }

  const quoted = thread.messages.find((m) => m.id === quotedId);

  return (
    <div
      data-testid="ask"
      data-connected={thread.connected}
      className="relative flex min-h-screen flex-col bg-bg-canvas"
    >
      {/* §25.4's chat wallpaper. Decorative, and no text sits on it. */}
      <Wallpaper night={night} />

      <div className="relative flex min-h-screen flex-col">
        <ChatHeader presenceState={presenceState} />

        {thread.handedOffToText ? (
          <p
            data-testid="handoff-banner"
            className="border-b border-border-subtle bg-surface-sunken px-4 py-2 text-caption text-ink-muted"
          >
            {t("ui.ask.handoff")}
          </p>
        ) : null}

        {thread.messages.length === 0 ? (
          <div className="flex flex-1 flex-col justify-end gap-3 px-4 py-6">
            <Card measure className="flex flex-col gap-2">
              <p className="text-title text-ink-primary">{t("ui.ask.empty_title")}</p>
              <p className="text-body text-ink-muted">{t("ui.ask.empty_body")}</p>
            </Card>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => onSend(t(key))}
                  className="rounded-chip border border-border-strong bg-surface px-3 py-2 text-caption text-ink-primary"
                >
                  {t(key)}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <MessageList
            messages={thread.messages}
            locale={locale}
            presenceLabelKey={indicatorFor(thread.presence)}
            onOpenTrust={setOpenCitation}
            onRetry={onRetry}
            onQuote={setQuotedId}
            onAction={() => {}}
          />
        )}

        {offers.length > 0 ? (
          <div className="flex flex-col gap-2 px-4 pb-2">
            {offers.map((offer) => (
              <MemoryChipHost
                key={`${offer.type}:${offer.summary}`}
                offer={offer}
                decision={chipDecisions[offer.summary] ?? null}
                onAccept={(summary) => {
                  setChipDecisions((d) => ({ ...d, [offer.summary]: "accepted" }));
                  onAcceptMemory(offer, summary);
                }}
                onDecline={() => {
                  setChipDecisions((d) => ({ ...d, [offer.summary]: "declined" }));
                  onDeclineMemory(offer);
                }}
              />
            ))}
          </div>
        ) : null}

        {thread.error ? (
          <div className="px-4 pb-2">
            <ErrorState
              error={{
                code: thread.error.code as never,
                message_key: thread.error.message_key,
                trace_id: "",
                retryable: true,
              }}
            />
          </div>
        ) : null}

        <Composer
          quoting={quoted?.kind === "user" ? quoted.text : undefined}
          onClearQuote={() => setQuotedId(null)}
          onSend={(text) => {
            onSend(text, quotedId ?? undefined);
            setQuotedId(null);
          }}
        />

        <TabBar active="ask" onSelect={onSelectTab} />
      </div>

      <TrustSheet
        open={openCitation !== null}
        onClose={() => setOpenCitation(null)}
        plainLanguage={openCitation?.trust.plain ?? ""}
        confidence={openCitation?.confidence ?? "verified"}
        sourceState={openCitation?.source_state ?? "default"}
        detailLines={openCitation ? [...openCitation.trust.details] : []}
      />
    </div>
  );
}
