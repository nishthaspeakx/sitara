/**
 * §25.3's call behaviour, with no socket, no browser and no audio.
 *
 * Same arrangement as `chat-thread.spec.ts`, and for the same reason: which
 * state the screen is in, what the captions say, and what a dropped socket does
 * to a call in progress are decisions that should be checkable in milliseconds.
 * This runs in the `library` project with no server at all.
 */

import { expect, test } from "@playwright/test";
import type { ControlEvent, ControlEventType } from "@sitara/schemas";
import { HOLDING_PHRASE_AFTER_MS } from "@sitara/schemas";

import {
  IDLE_CALL,
  callReducer,
  holdingPhraseDue,
  type CallModel,
} from "../src/lib/call-state";

let seq = 0;
function event(type: ControlEventType, payload: Record<string, unknown> = {}): ControlEvent {
  return { type, seq: seq++, ts: 0, ack: null, payload };
}

function apply(model: CallModel, ...events: ControlEvent[]): CallModel {
  return events.reduce((m, e) => callReducer(m, { type: "event", event: e, at: 1_000 }), model);
}

const ready = event("session.ready", { conversation_id: "c1", resume_token: "r1" });

test.describe("the six states", () => {
  test("a connected call is listening, not connecting", async () => {
    const model = apply(IDLE_CALL, ready);
    expect(model.state).toBe("listening");
    expect(model.conversationId).toBe("c1");
  });

  test("she is speaking from tts.start until tts.end", async () => {
    let model = apply(IDLE_CALL, ready, event("tts.start", { client_message_id: "u1" }));
    expect(model.state).toBe("speaking");
    model = apply(model, event("tts.end", { client_message_id: "u1" }));
    expect(model.state).toBe("listening");
  });

  test("a barge-in stops her looking like she is speaking", async () => {
    // §25.3: the interruption is instant on screen. Whether it was the user
    // talking over her or a dead synthesiser is `reason`'s job — and the
    // handoff that follows the second case is a separate event.
    const model = apply(
      IDLE_CALL,
      ready,
      event("tts.start", { client_message_id: "u1" }),
      event("barge_in", { cancelled_client_message_id: "u1", reason: "user_speech" }),
    );
    expect(model.state).toBe("listening");
  });

  test("a dropped socket is degraded, never ended", async () => {
    // A drop that rendered as a normal goodbye would tell the user they hung
    // up. §25.3 has a designed screen for this and it is not the ended one.
    const model = callReducer(apply(IDLE_CALL, ready), { type: "socket_lost", at: 2_000 });
    expect(model.state).toBe("degraded");
  });

  test("ending a call that already ended does not reopen it", async () => {
    const ended = callReducer(apply(IDLE_CALL, ready), { type: "end", at: 2_000 });
    expect(callReducer(ended, { type: "socket_lost", at: 3_000 }).state).toBe("ended");
  });
});

test.describe("captions", () => {
  test("a final replaces its partial rather than appending beside it", async () => {
    // The recogniser corrects itself mid-sentence. Two lines saying nearly the
    // same thing reads as Tara mishearing twice.
    const model = apply(
      IDLE_CALL,
      ready,
      event("captions.partial", { client_message_id: "u1", text: "what is Sat", role: "user" }),
      event("captions.final", {
        client_message_id: "u1",
        text: "what is Saturn doing?",
        role: "user",
      }),
    );
    expect(model.captions).toHaveLength(1);
    expect(model.captions[0]!.text).toBe("what is Saturn doing?");
    expect(model.captions[0]!.partial).toBe(false);
  });

  test("her caption and the user's are separate lines with the same id", async () => {
    const model = apply(
      IDLE_CALL,
      ready,
      event("captions.final", { client_message_id: "u1", text: "hello", role: "user" }),
      event("captions.final", {
        client_message_id: "u1",
        role: "tara",
        turn: { text: "Hello — how is your morning?" },
      }),
    );
    expect(model.captions.map((c) => c.role)).toEqual(["user", "tara"]);
  });

  test("a partial is always the user's own speech", async () => {
    // §34.6's fabrication gate, one layer out. The payload type pins `role` to
    // the constant "user" so a partial of Tara's words is unrepresentable; this
    // asserts the client does not invent one either.
    const model = apply(
      IDLE_CALL,
      ready,
      event("captions.partial", { client_message_id: "u1", text: "half a thought" }),
    );
    expect(model.captions.every((c) => c.role === "user" || !c.partial)).toBe(true);
  });
});

test.describe("§25.3's 1.8s thinking cap", () => {
  test("the shimmer is due for a holding phrase after 1.8s and not before", async () => {
    const thinking = apply(IDLE_CALL, ready, event("presence.state", { state: "thoughtful" }));
    expect(thinking.state).toBe("thinking");
    expect(holdingPhraseDue(thinking, 1_000 + HOLDING_PHRASE_AFTER_MS - 1)).toBe(false);
    expect(holdingPhraseDue(thinking, 1_000 + HOLDING_PHRASE_AFTER_MS)).toBe(true);
  });

  test("her words clear the shimmer", async () => {
    const model = apply(
      IDLE_CALL,
      ready,
      event("presence.state", { state: "thoughtful" }),
      event("captions.final", { client_message_id: "u1", role: "tara", turn: { text: "…" } }),
    );
    expect(holdingPhraseDue(model, 999_999)).toBe(false);
  });
});

test.describe("§32.9's minute warnings and §25.3's plan chip", () => {
  test("a warning carries a key and updates the chip", async () => {
    let model = callReducer(IDLE_CALL, {
      type: "grant",
      plan: { plan: "monthly", unlimited: false, minutesLeft: 12, minutesQuota: 300 },
      captionsOn: true,
    });
    model = apply(
      model,
      ready,
      event("entitlement.warning", {
        minutes_left: 5,
        minutes_quota: 300,
        plan: "monthly",
        message_key: "ui.call.warning_minutes",
      }),
    );
    expect(model.warningKey).toBe("ui.call.warning_minutes");
    expect(model.warningMinutes).toBe(5);
    expect(model.plan?.minutesLeft).toBe(5);
  });

  test("dismissing a warning does not disturb the chip", async () => {
    let model = callReducer(IDLE_CALL, {
      type: "grant",
      plan: { plan: "monthly", unlimited: false, minutesLeft: 5, minutesQuota: 300 },
      captionsOn: false,
    });
    model = callReducer(model, { type: "dismiss_warning" });
    expect(model.warningKey).toBeNull();
    expect(model.plan?.minutesLeft).toBe(5);
  });

  test("captions default to the server's answer, not to a guess", async () => {
    // §25.3 wants them on for a FIRST call, and only the server knows whether
    // this account has ever spent a minute — a client-side "have I called
    // before?" resets with storage and would turn them on again forever.
    const first = callReducer(IDLE_CALL, {
      type: "grant",
      plan: { plan: "trial", unlimited: false, minutesLeft: 60, minutesQuota: 60 },
      captionsOn: true,
    });
    expect(first.captionsOn).toBe(true);

    const later = callReducer(IDLE_CALL, {
      type: "grant",
      plan: { plan: "monthly", unlimited: false, minutesLeft: 220, minutesQuota: 300 },
      captionsOn: false,
    });
    expect(later.captionsOn).toBe(false);
  });
});

test.describe("the degrade ladder reaches the screen", () => {
  test("a handoff names the conversation the words are already in", async () => {
    const model = apply(
      IDLE_CALL,
      ready,
      event("handoff.to_text", { conversation_id: "c1", reason: "tts_provider_failed" }),
    );
    expect(model.state).toBe("degraded");
    expect(model.handoffReason).toBe("tts_provider_failed");
    expect(model.conversationId).toBe("c1");
  });

  test("a resume offer is only ever an offer", async () => {
    // §32.11 is a one-tap chip, not an automatic reconnection: metering
    // restarts only if the user accepts, so nothing here changes the state.
    const model = apply(
      IDLE_CALL,
      ready,
      event("handoff.to_text", { conversation_id: "c1", reason: "media_socket_lost" }),
      event("resume.offer", { conversation_id: "c1" }),
    );
    expect(model.resumeOffered).toBe(true);
    expect(model.state).toBe("degraded");
  });

  test("an error keeps the envelope whole", async () => {
    const model = apply(
      IDLE_CALL,
      event("error", {
        code: "VOICE_PROVIDER_UNAVAILABLE",
        message_key: "errors.voice.call_language_unavailable",
      }),
    );
    expect(model.error).toEqual({
      code: "VOICE_PROVIDER_UNAVAILABLE",
      message_key: "errors.voice.call_language_unavailable",
    });
  });
});
