import { expect, test } from "@playwright/test";
import type { ChatTurn, ControlEvent } from "@sitara/schemas";

import {
  EMPTY_THREAD,
  groupByDay,
  threadReducer,
  type Message,
  type ThreadState,
} from "../src/lib/chat-thread";

/**
 * §25.4's thread grammar, with no browser and no socket.
 *
 * Everything hard about a chat screen is a state question: which bubble a
 * reply belongs to, what a dropped socket does to a message in flight, whether
 * a resumed turn appears once or twice. None of it needs a DOM, so none of it
 * is tested through one — the same split `today-variant.spec.ts` already uses
 * for §32.1's precedence.
 */

const TURN: ChatTurn = {
  message_id: "6a70000000000000000000d1",
  text: "Saturn is moving through your 10th house today.",
  locale: "en",
  confidence: "verified",
  safety_level: "l1_clear",
  presence_state: "calm_guidance",
  intent: "natal_chart_question",
  trace_id: "t1",
  citations: [],
  memory_chips: [],
  review_queued: false,
  message_key: null,
  budget_notice_key: null,
};

function event(type: string, payload: Record<string, unknown>): ControlEvent {
  return { type, seq: 1, ts: 0, ack: null, payload } as ControlEvent;
}

function afterSend(text = "what is Saturn doing?"): ThreadState {
  return threadReducer(EMPTY_THREAD, { type: "send", id: "m1", text, at: 1_000 });
}

test.describe("§25.4 — the thread", () => {
  test("a sent message is `sending` until Tara answers, then delivered", () => {
    let state = afterSend();
    expect((state.messages[0] as Message & { delivery: string }).delivery).toBe("sending");

    state = threadReducer(state, {
      type: "event",
      event: event("captions.final", { role: "tara", client_message_id: "m1", turn: TURN }),
      at: 2_000,
    });

    const [user, tara] = state.messages;
    expect((user as { delivery: string }).delivery).toBe("delivered");
    expect(tara!.kind).toBe("tara");
  });

  test("there is no state after delivered — no read receipts, ever", () => {
    /**
     * §25.4 drops read receipts and blue ticks as "meaningless and
     * manipulative for an AI"; a single ✓ confirms delivery to Tara and
     * nothing more. This is the type-level version of that: there are three
     * delivery states and none of them means "read". A future ✓✓ would have
     * to add a member here and be noticed.
     */
    const state = threadReducer(afterSend(), {
      type: "event",
      event: event("captions.final", { role: "tara", client_message_id: "m1", turn: TURN }),
      at: 2_000,
    });
    const delivery = (state.messages[0] as { delivery: string }).delivery;
    expect(["sending", "delivered", "failed"]).toContain(delivery);
  });

  test("presence drives the indicator and clears when the turn lands", () => {
    let state = threadReducer(afterSend(), {
      type: "event",
      event: event("presence.state", { state: "thoughtful" }),
      at: 1_500,
    });
    expect(state.presence).toBe("thoughtful");

    state = threadReducer(state, {
      type: "event",
      event: event("captions.final", { role: "tara", client_message_id: "m1", turn: TURN }),
      at: 2_000,
    });
    expect(state.presence).toBeNull();
  });

  test("a turn arriving twice renders once", () => {
    /**
     * §32.11's resume offer can carry a turn the client already received — a
     * socket that dropped AFTER the frame left the server. Keying on the
     * question rather than appending is what makes the resume idempotent.
     */
    let state = threadReducer(afterSend(), {
      type: "event",
      event: event("captions.final", { role: "tara", client_message_id: "m1", turn: TURN }),
      at: 2_000,
    });
    state = threadReducer(state, {
      type: "event",
      event: event("resume.offer", {
        conversation_id: "c1",
        pending_turn: TURN,
        pending_client_message_id: "m1",
      }),
      at: 3_000,
    });

    expect(state.messages.filter((m) => m.kind === "tara")).toHaveLength(1);
  });

  test("a user frame coming back is not rendered as an inbound message", () => {
    const state = threadReducer(afterSend(), {
      type: "event",
      event: event("captions.final", { role: "user", text: "echo", client_message_id: "m1" }),
      at: 2_000,
    });
    expect(state.messages).toHaveLength(1);
  });
});

test.describe("§34.6 — what a dropped socket does to the thread", () => {
  test("a message in flight fails rather than spinning forever", () => {
    /**
     * The T2 case, at the state level. A bubble left on `sending` is the shape
     * of every chat client that has ever eaten a message; §25.4's own retry
     * affordance lives on the bubble, so the state has to reach it.
     */
    const state = threadReducer(afterSend(), { type: "socket_lost", at: 5_000 });

    expect((state.messages[0] as { delivery: string }).delivery).toBe("failed");
    expect(state.presence).toBeNull();
    expect(state.connected).toBe(false);
  });

  test("an already-answered message is not retroactively failed", () => {
    let state = threadReducer(afterSend(), {
      type: "event",
      event: event("captions.final", { role: "tara", client_message_id: "m1", turn: TURN }),
      at: 2_000,
    });
    state = threadReducer(state, { type: "socket_lost", at: 5_000 });

    expect((state.messages[0] as { delivery: string }).delivery).toBe("delivered");
  });

  test("a reconnect inside the window delivers the pending turn without re-asking", () => {
    let state = threadReducer(afterSend(), { type: "socket_lost", at: 5_000 });
    state = threadReducer(state, {
      type: "event",
      event: event("session.ready", { resume_token: "tok", resume_window_s: 300 }),
      at: 6_000,
    });
    state = threadReducer(state, {
      type: "event",
      event: event("resume.offer", {
        pending_turn: TURN,
        pending_client_message_id: "m1",
      }),
      at: 6_100,
    });

    expect(state.messages.filter((m) => m.kind === "tara")).toHaveLength(1);
    expect((state.messages[0] as { delivery: string }).delivery).toBe("delivered");
    expect(state.resumeToken).toBe("tok");
  });

  test("past the window the thread says so and keeps working", () => {
    /**
     * §34.6: after five minutes `handoff.to_text` fires with full context. The
     * banner is not decoration — the transport genuinely changed, and
     * pretending nothing happened would be the fake-online-status §25.4
     * refuses, pointed the other way.
     */
    const state = threadReducer(afterSend(), {
      type: "event",
      event: event("handoff.to_text", { conversation_id: "c1", reason: "resume_window_elapsed" }),
      at: 400_000,
    });

    expect(state.handedOffToText).toBe(true);
    expect(state.connected).toBe(false);
    expect(state.presence).toBeNull();
  });

  test("a turn answered over the handoff path lands in the same thread", () => {
    let state = threadReducer(afterSend(), {
      type: "event",
      event: event("handoff.to_text", { conversation_id: "c1", reason: "gone" }),
      at: 400_000,
    });
    state = threadReducer(state, {
      type: "handoff_reply",
      turn: TURN,
      replyTo: "m1",
      at: 401_000,
    });

    expect(state.messages.filter((m) => m.kind === "tara")).toHaveLength(1);
    expect((state.messages[0] as { delivery: string }).delivery).toBe("delivered");
  });

  test("an error envelope fails the question it answers and is rendered", () => {
    const state = threadReducer(afterSend(), {
      type: "event",
      event: event("error", { code: "SYS_UNAVAILABLE", message_key: "errors.sys.unavailable" }),
      at: 2_000,
    });

    expect(state.error).toEqual({
      code: "SYS_UNAVAILABLE",
      message_key: "errors.sys.unavailable",
    });
    expect((state.messages[0] as { delivery: string }).delivery).toBe("failed");
    expect(state.presence).toBeNull();
  });

  test("voice members of the closed set change nothing here", () => {
    /**
     * §34.6's set is closed at fifteen and M9 owns five of them. Ignoring
     * rather than switching exhaustively means M9 adds behaviour instead of
     * rewriting this.
     */
    const before = afterSend();
    for (const type of ["vad.state", "barge_in", "tts.start", "tts.chunk_meta", "tts.end"]) {
      expect(threadReducer(before, { type: "event", event: event(type, {}), at: 9 })).toEqual(
        before,
      );
    }
  });
});

test.describe("§25.4 — date pills", () => {
  test("messages group by local day, in order", () => {
    const day1 = new Date(2026, 7, 10, 9, 0).getTime();
    const day1b = new Date(2026, 7, 10, 21, 0).getTime();
    const day2 = new Date(2026, 7, 11, 8, 0).getTime();

    const groups = groupByDay([
      { kind: "user", id: "a", text: "one", at: day1, delivery: "delivered" },
      { kind: "user", id: "b", text: "two", at: day1b, delivery: "delivered" },
      { kind: "user", id: "c", text: "three", at: day2, delivery: "delivered" },
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[0]!.items).toHaveLength(2);
    expect(groups[1]!.items).toHaveLength(1);
  });
});
