"use client";

/**
 * One bubble, with §25.4's citation underlines inside it.
 *
 * **The spans are SERVED, not found here.** `ChatCitation` carries
 * `span_start`/`span_end` into the turn's own text, computed by the grounding
 * validator that decided which sentence stood on which fact. A client that
 * re-derived them would be a second implementation of "what is a claim", and
 * the two would disagree exactly where it matters.
 *
 * **Offsets are Unicode code points.** JavaScript string indices are UTF-16
 * units, and the two differ for anything outside the BMP. `[...text]` splits
 * into code points so a Devanagari or emoji-bearing reply underlines the words
 * the server verified rather than a window two characters off.
 *
 * **Fact IDs never reach the DOM** (§30.4). `ChatBubble` takes a message-local
 * `spanId`; the citation itself is resolved privately by the caller and the
 * Trust Sheet is handed finished sentences.
 */

import { useTranslations } from "next-intl";
import type { ChatCitation, ChatTurn } from "@sitara/schemas";

import { ChatBubble, ConfidenceChip, VoiceNoteBubble, type CitedSpan } from "@/components/ui";
import type { Message } from "@/lib/chat-thread";
import { voiceNoteAudioUrl } from "@/lib/api";
import { formatDuration } from "@/lib/voice-note";

/** Split a turn's text into plain runs and cited spans, in order. */
export function contentParts(turn: ChatTurn): Array<string | CitedSpan> {
  const points = [...turn.text];
  const parts: Array<string | CitedSpan> = [];
  let cursor = 0;

  const ordered = [...turn.citations].sort((a, b) => a.span_start - b.span_start);
  ordered.forEach((citation, index) => {
    const start = Math.max(citation.span_start, cursor);
    const end = Math.min(citation.span_end, points.length);
    if (end <= start) return;
    if (start > cursor) parts.push(points.slice(cursor, start).join(""));
    parts.push({ spanId: `c${index}`, text: points.slice(start, end).join("") });
    cursor = end;
  });
  if (cursor < points.length) parts.push(points.slice(cursor).join(""));
  return parts.length ? parts : [turn.text];
}

export function MessageBubble({
  message,
  timestamp,
  onOpenTrust,
  onRetry,
}: {
  message: Message;
  timestamp: string;
  onOpenTrust?: (citation: ChatCitation) => void;
  onRetry?: () => void;
}) {
  const t = useTranslations();

  if (message.kind === "user") {
    return (
      <div className="flex flex-col items-end gap-1">
        {message.voice ? (
          // §25.4/§33.1, and the single most important wiring decision in this
          // file: `src` is the ORIGINAL recording, addressed by
          // `source_audio_asset_id`. It is NEVER `tts_audio_asset_id` — there
          // is no field on a `UserMessage` that could carry one, which is how
          // "replay plays the user's own audio, never a TTS reconstruction"
          // stops depending on whoever writes this line next.
          //
          // `playbackPolicy` is SERVED, never inferred. A client deciding for
          // itself whether a recording exists would guess wrong in exactly the
          // two interesting cases — the ephemeral account and the note whose
          // thirty days are up — and would draw a play control over nothing.
          <div className="max-w-reading rounded-bubble rounded-ee-sm bg-surface-sunken px-3 py-2">
            <VoiceNoteBubble
              mode="idle"
              duration={formatDuration(message.voice.durationMs)}
              transcriptStatus={message.voice.transcriptStatus}
              transcript={message.text || undefined}
              src={
                message.voice.playbackPolicy === "original_audio" && message.voice.assetId
                  ? voiceNoteAudioUrl(message.voice.assetId)
                  : undefined
              }
              // §33.1: the bubble "honestly drops playback of expired/deleted
              // audio and shows the transcript with a 'voice input' marker".
              markerKey={
                message.voice.playbackPolicy === "transcript_only"
                  ? "ui.audio.voice_input"
                  : undefined
              }
              expiresOn={message.voice.expiresAt ?? undefined}
            />
            <span className="block pt-1 text-caption text-ink-muted">{timestamp}</span>
          </div>
        ) : (
          <ChatBubble
            author="user"
            content={[message.text]}
            timestamp={timestamp}
            failed={message.delivery === "failed"}
            onRetry={onRetry}
          />
        )}
        {/* §25.4: a single ✓ confirms delivery to Tara, nothing more. There
            are no read receipts and no second tick — the state set has no
            member that could render one. */}
        {message.delivery === "delivered" ? (
          <span className="pe-1 text-caption text-ink-muted" data-testid="delivered">
            ✓ <span className="sr-only">{t("ui.ask.delivered")}</span>
          </span>
        ) : null}
      </div>
    );
  }

  const { turn } = message;
  const ordered = [...turn.citations].sort((a, b) => a.span_start - b.span_start);

  return (
    <div className="flex flex-col items-start gap-1">
      <ChatBubble
        author="tara"
        content={contentParts(turn)}
        timestamp={timestamp}
        onOpenTrust={(spanId) => {
          const citation = ordered[Number(spanId.slice(1))];
          if (citation) onOpenTrust?.(citation);
        }}
      />
      {/* §25.4: "ConfidenceChips render inside bubbles unchanged — familiarity
          never dilutes the honesty layer." Shown when the turn stands on facts;
          a turn with no claims has no confidence to report. */}
      {ordered.length > 0 ? (
        <div className="ps-1">
          <ConfidenceChip state={ordered[0]!.confidence} />
        </div>
      ) : null}
    </div>
  );
}
