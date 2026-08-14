/**
 * A stand-in for `sitara-realtime`, spoken to over a REAL WebSocket.
 *
 * ── Why this is a process and not a `page.route` ───────────────────────────
 *
 * CL-013: "Browser-side request interception stops a request before the server
 * sees it, so it can never observe middleware, rewrites, redirects, or
 * routing." That rule cost a milestone once — `page.route` hid the fact that
 * every onboarding step 307'd to `/<locale>/v1/…` and 404'd in a real browser.
 *
 * A socket has its own version of the same trap, and a worse one. `page.route`
 * cannot intercept a WebSocket at all, so the only browser-side option would
 * be to replace `window.WebSocket` with a fake — which means the suite would
 * verify that the client handles frames the test invented, over a transport
 * that was never opened. Every one of the things S18 can actually get wrong
 * would be invisible: the handshake, the ticket exchange, the close event, the
 * reconnect, the ordering of frames against the DOM updates they cause.
 *
 * So this is a real RFC 6455 server. The browser performs a real upgrade
 * against a real origin, and `close()` here is a real close in the client.
 *
 * ── Dependency-free, like the other stubs ──────────────────────────────────
 *
 * Text frames AND binary (M9): §34.6's control events are text, and a voice
 * note is real PCM inside a `vad.state` bracket. The bracket rule is enforced
 * here exactly as `services/realtime` enforces it — audio outside one is
 * SYS_VALIDATION, and a sequence gap fails the note — because a stub that
 * accepted what the real service refuses is a fake that accepts what the real
 * system rejects, which is the root CLAUDE.md rule and the one the onboarding
 * stub broke. Node's `crypto` and `net` are enough.
 *
 * ── The turns are RECORDED, never authored ─────────────────────────────────
 *
 * `tests/__fixtures__/chat/` holds `ChatTurn`s produced by the real §9
 * pipeline (`services/api/scripts/record_chat_fixtures.py`). A hand-written
 * reply would be a reply nobody's pipeline produced — with citation spans
 * nobody's validator computed — and every baseline taken from it would survive
 * any regression in grounding, safety or citation rendering. The same rule
 * `stub-api.mjs` already follows for the morning brief.
 *
 * ── The control plane ──────────────────────────────────────────────────────
 *
 * `POST /__control/scenario` picks which recorded turn answers next, and how
 * the socket behaves: `drop_before_reply`, `drop_after_reply`, `handoff`,
 * `error`. Called by the test process directly on this port, never through the
 * app — exactly as `stub-api.mjs` is.
 */

import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const port = Number(process.argv[2] ?? 3102);
const GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

const FIXTURE_DIR = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "tests",
  "__fixtures__",
  "chat",
);

/** @type {Map<string, object>} keyed `${scenario}.${locale}` */
const turns = new Map();
try {
  for (const file of readdirSync(FIXTURE_DIR)) {
    if (!file.endsWith(".json")) continue;
    turns.set(file.slice(0, -".json".length), JSON.parse(
      readFileSync(path.join(FIXTURE_DIR, file), "utf-8"),
    ));
  }
} catch {
  console.warn(`[stub-realtime] no chat fixtures at ${FIXTURE_DIR}`);
}

/** Per-test scenario, keyed by the `client` query param the page carries. */
const scenarios = new Map();

/** Mic bytes received per client, so a test can observe a real capture path. */
const micBytesByClient = new Map();

function scenarioFor(client) {
  return (
    scenarios.get(client) ?? {
      turn: "grounded",
      locale: "en",
      behaviour: "reply",
      stages: ["safety_pre", "memory_retrieval", "generation"],
    }
  );
}

// ---------------------------------------------------------------------------
// RFC 6455, the subset §34.6's control events need
// ---------------------------------------------------------------------------

function accept(key) {
  return createHash("sha1").update(key + GUID).digest("base64");
}

/** 16 kHz mono s16le → milliseconds, so the bubble shows a real duration. */
function durationOf(bytes) {
  return Math.round((bytes / 2 / 16000) * 1000);
}

/** Server→client text frame. Never masked, never fragmented. */
function encode(text) {
  const body = Buffer.from(text, "utf-8");
  const length = body.length;
  let header;
  if (length < 126) {
    header = Buffer.from([0x81, length]);
  } else if (length < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(length), 2);
  }
  return Buffer.concat([header, body]);
}

/**
 * Client→server frames are always masked (RFC 6455 §5.3), and a browser sends
 * short control events, so this handles one complete frame at a time and
 * returns the remainder. A partial frame is buffered by the caller.
 */
function decode(buffer) {
  if (buffer.length < 2) return null;
  const opcode = buffer[0] & 0x0f;
  const masked = (buffer[1] & 0x80) !== 0;
  let length = buffer[1] & 0x7f;
  let offset = 2;
  if (length === 126) {
    if (buffer.length < 4) return null;
    length = buffer.readUInt16BE(2);
    offset = 4;
  } else if (length === 127) {
    if (buffer.length < 10) return null;
    length = Number(buffer.readBigUInt64BE(2));
    offset = 10;
  }
  const maskKey = masked ? buffer.subarray(offset, offset + 4) : null;
  if (masked) offset += 4;
  if (buffer.length < offset + length) return null;

  const payload = Buffer.from(buffer.subarray(offset, offset + length));
  if (maskKey) {
    for (let i = 0; i < payload.length; i += 1) payload[i] ^= maskKey[i % 4];
  }
  return { opcode, payload, rest: buffer.subarray(offset + length) };
}

// ---------------------------------------------------------------------------

const server = createServer((req, res) => {
  if (req.url === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok", service: "stub-realtime" }));
    return;
  }
  if (req.method === "GET" && req.url?.startsWith("/__control/mic")) {
    const id = new URL(req.url, "http://localhost").searchParams.get("client") ?? "default";
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ bytes: micBytesByClient.get(id) ?? 0 }));
    return;
  }
  if (req.method === "POST" && req.url?.startsWith("/__control/scenario")) {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      const parsed = JSON.parse(body || "{}");
      scenarios.set(parsed.client ?? "default", parsed);
      res.writeHead(204).end();
    });
    return;
  }
  res.writeHead(404).end();
});

server.on("upgrade", (req, socket) => {
  const key = req.headers["sec-websocket-key"];
  if (!key) {
    socket.destroy();
    return;
  }
  socket.write(
    "HTTP/1.1 101 Switching Protocols\r\n" +
      "Upgrade: websocket\r\n" +
      "Connection: Upgrade\r\n" +
      `Sec-WebSocket-Accept: ${accept(key)}\r\n\r\n`,
  );

  const url = new URL(req.url ?? "/", "http://localhost");
  const client = url.searchParams.get("client") ?? "default";
  const isCall = url.pathname.startsWith("/call");
  let seq = 0;
  let buffered = Buffer.alloc(0);

  const send = (type, payload, ack = null) =>
    socket.write(encode(JSON.stringify({ type, seq: seq++, ts: Date.now(), ack, payload })));

  /** The open §34.6 bracket, or null. One at a time, as the real service does. */
  let recording = null;
  /**
   * Mic bytes a CALL has received. Exposed on `/__control/mic` so a test can
   * assert the browser really opened a capture path — stubbing `VoiceRecorder`
   * instead would verify frames the test invented over a microphone that never
   * opened, which is CL-013's failure mode one layer further in.
   */
  let micBytes = 0;

  socket.on("data", (chunk) => {
    buffered = Buffer.concat([buffered, chunk]);
    for (;;) {
      const frame = decode(buffered);
      if (!frame) return;
      buffered = frame.rest;

      if (frame.opcode === 0x8) {
        socket.end();
        return;
      }
      if (frame.opcode === 0x2) {
        if (isCall) {
          // §25.3's call has NO bracket: the microphone is open for the whole
          // call and §25.3's mute is client-hard, so silence on the wire is
          // what a muted user sounds like. Counting the bytes is enough — a
          // test asserts the browser really opened a capture path.
          micBytes += frame.payload.length - 8;
          micBytesByClient.set(client, micBytes);
          continue;
        }
        // §34.6's binary frame — real PCM over a real socket, which is the
        // whole point of this file existing. Accepted only inside a bracket,
        // exactly as `services/realtime` does, so a client that sends audio
        // without one fails here the way it fails in production.
        if (!recording) {
          send("error", {
            code: "SYS_VALIDATION",
            message_key: "errors.sys.validation",
            trace_id: "",
            retryable: false,
          });
          continue;
        }
        const seq = frame.payload.readUInt32BE(0);
        if (seq !== recording.nextSeq) {
          // A gap fails the note. Splicing across it would transcribe into a
          // sentence nobody said, and no §9 validator can catch that — the
          // fabrication is on the user's side of the turn.
          recording = null;
          send("error", {
            code: "SYS_VALIDATION",
            message_key: "errors.sys.validation",
            trace_id: "",
            retryable: false,
          });
          continue;
        }
        recording.nextSeq += 1;
        recording.bytes += frame.payload.length - 8;
        continue;
      }
      if (frame.opcode !== 0x1) continue;

      let event;
      try {
        event = JSON.parse(frame.payload.toString("utf-8"));
      } catch {
        continue;
      }
      const scenario = scenarioFor(client);

      if (isCall) {
        if (event.type === "session.start") {
          runCall(send, scenario, event.seq);
          continue;
        }
        if (event.type === "session.end") {
          socket.end();
          return;
        }
        continue;
      }

      if (event.type === "session.start") {
        // A resume token that names a pending turn gets it back, exactly as
        // the real service does — never by re-running the turn.
        if (event.payload?.resume_token && scenario.pending) {
          send("resume.offer", {
            conversation_id: "c1",
            pending_turn: turns.get(`${scenario.turn}.${scenario.locale}`) ?? null,
            pending_client_message_id: scenario.pending,
          }, event.seq);
        }
        if (scenario.behaviour === "handoff") {
          send("handoff.to_text", { conversation_id: "c1", reason: "resume_window_elapsed" }, event.seq);
          return;
        }
        send("session.ready", {
          resume_token: "resume-tok",
          resume_window_s: 300,
          conversation_id: "c1",
        }, event.seq);
        continue;
      }

      if (event.type === "captions.final" && event.payload?.role === "user") {
        const turn = turns.get(`${scenario.turn}.${scenario.locale}`);
        const cid = event.payload.client_message_id;

        for (const stage of scenario.stages ?? []) {
          send("presence.state", { state: presenceFor(stage), stage });
        }

        if (scenario.behaviour === "drop_before_reply") {
          // The socket dies with the question in flight and no answer coming.
          socket.destroy();
          return;
        }
        if (scenario.behaviour === "hold") {
          // Presence emitted, no answer, socket still OPEN — a turn genuinely
          // in flight. This is what the typing indicator's baseline needs;
          // `drop_before_reply` cannot serve it, because a close correctly
          // clears the indicator.
          continue;
        }
        if (scenario.behaviour === "error") {
          send("error", {
            code: scenario.code ?? "SYS_UNAVAILABLE",
            message_key: scenario.message_key ?? "errors.sys.unavailable",
            trace_id: "",
            retryable: true,
          }, event.seq);
          continue;
        }
        if (!turn) {
          send("error", {
            code: "SYS_INTERNAL",
            message_key: "errors.sys.internal",
            trace_id: "",
            retryable: true,
          }, event.seq);
          continue;
        }

        send("captions.final", { role: "tara", client_message_id: cid, turn }, event.seq);
        if (scenario.behaviour === "drop_after_reply") socket.destroy();
        continue;
      }

      if (event.type === "vad.state") {
        const cid = event.payload?.client_message_id;
        const state = event.payload?.state;

        if (state === "speech_start") {
          if (!cid) {
            send("error", {
              code: "SYS_VALIDATION",
              message_key: "errors.sys.validation",
              trace_id: "",
              retryable: false,
            }, event.seq);
            continue;
          }
          recording = { cid, nextSeq: 0, bytes: 0 };
          continue;
        }

        if (state === "cancelled") {
          // §28.3: discarded. Nothing transcribed, nothing stored, nothing sent.
          recording = null;
          continue;
        }

        if (state === "speech_end") {
          const held = recording;
          recording = null;
          if (!held || held.bytes === 0) {
            send("error", {
              code: "SYS_VALIDATION",
              message_key: "errors.sys.validation",
              trace_id: "",
              retryable: false,
            }, event.seq);
            continue;
          }

          for (const stage of scenario.voiceStages ?? ["transcription", "generation"]) {
            send("presence.state", { state: presenceFor(stage), stage });
          }

          if (scenario.behaviour === "transcribe_fail") {
            // §28.3's designed state: the transcript failed, the RECORDING did
            // not. Carried on the user's own bubble, never as an error
            // envelope — that would put a retry over a note that was recorded
            // and stored successfully.
            send("captions.final", {
              role: "user",
              client_message_id: held.cid,
              text: "",
              transcript_status: "failed",
              playback_policy: "original_audio",
              source_audio_asset_id: "6a70000000000000000000e1",
              duration_ms: durationOf(held.bytes),
              source_audio_expires_at: "2026-09-12T09:30:00+00:00",
              quoted_message_id: null,
            }, event.seq);
            continue;
          }

          const ephemeral = scenario.behaviour === "ephemeral_audio";
          send("captions.final", {
            role: "user",
            client_message_id: held.cid,
            text: scenario.transcript ?? "Mera rahu kaal kab hai aaj?",
            transcript_status: "ready",
            // §33.1's ephemeral mode: nothing was stored, so the bubble
            // promises no playback and shows the "voice input" marker.
            playback_policy: ephemeral ? "transcript_only" : "original_audio",
            source_audio_asset_id: ephemeral ? null : "6a70000000000000000000e1",
            duration_ms: durationOf(held.bytes),
            source_audio_expires_at: ephemeral ? null : "2026-09-12T09:30:00+00:00",
            quoted_message_id: null,
          }, event.seq);

          const turn = turns.get(`${scenario.turn}.${scenario.locale}`);
          if (!turn) continue;
          send("captions.final", { role: "tara", client_message_id: held.cid, turn }, event.seq);

          // §25.4's voice-note reply, AFTER her words — so the transcript the
          // toggle shows is on screen before any audio plays.
          if (scenario.behaviour !== "no_tts") {
            send("tts.start", {
              client_message_id: held.cid,
              tts_audio_asset_id: "6a70000000000000000000e2",
              sample_rate_hz: 16000,
              voice_id: null,
            });
            send("tts.end", { client_message_id: held.cid, duration_ms: 3400 });
          }
          continue;
        }

        continue;
      }

      if (event.type === "session.end") {
        socket.end();
        return;
      }
    }
  });

  socket.on("error", () => socket.destroy());
});

/**
 * §25.3's call, scripted (M10).
 *
 * The whole exchange is driven from `session.start` because a call is a
 * SEQUENCE — a screen that renders `speaking` correctly and never renders the
 * handoff is a screen that passes a frame-by-frame test and fails a call.
 *
 * `tts_kill` is the chaos scenario the milestone was built around: synthesis
 * dies mid-utterance, and the socket must leave her words on screen, stop the
 * audio with a REASON, and land in `handoff.to_text`. It mirrors, frame for
 * frame, what `services/realtime/tests/test_call_degrade.py` asserts against
 * the real service — the two would have to drift together to both be wrong.
 */
function runCall(send, scenario, ack) {
  const behaviour = scenario.behaviour ?? "reply";
  const turn = turns.get(`${scenario.turn ?? "grounded"}.${scenario.locale ?? "en"}`);
  const cid = "u1";

  // §25.3's `connecting` is a real state and the only way to observe it is a
  // socket that has upgraded and not yet answered. A test that raced the
  // handshake would capture it once in twenty runs.
  if (behaviour === "hold_ready") return;

  send("session.ready", {
    resume_token: "call-resume-tok",
    resume_window_s: 300,
    conversation_id: "c1",
  }, ack);

  if (behaviour === "connecting") return; // stays on the connecting state

  // The user speaks. Server-side VAD opens the bracket and mints the id.
  send("vad.state", { state: "speech_start", client_message_id: cid });
  send("captions.partial", { role: "user", text: "what is Saturn", client_message_id: cid });
  send("captions.final", {
    role: "user",
    text: "what is Saturn doing today?",
    client_message_id: cid,
    quoted_message_id: null,
    transcript_status: "ready",
    // Spoken, and never stored (§13/§33.1). `text_only` would say they typed it.
    playback_policy: "transcript_only",
    source_audio_asset_id: null,
    duration_ms: null,
    source_audio_expires_at: null,
  });

  if (behaviour === "turn_failed") {
    send("error", {
      code: "SYS_UNAVAILABLE",
      message_key: "errors.sys.unavailable",
      trace_id: "",
      retryable: true,
    });
    send("handoff.to_text", { conversation_id: "c1", reason: "turn_failed" });
    return;
  }

  send("presence.state", { state: "thoughtful", stage: "fact_tools" });
  if (behaviour === "thinking") return;

  if (!turn) return;
  // Her words FIRST, always — before a single byte of audio.
  send("captions.final", { role: "tara", client_message_id: cid, turn });

  send("tts.start", {
    client_message_id: cid,
    // Null: a call's audio is streamed and never stored, so there is no asset
    // and nothing to replay (§33.1).
    tts_audio_asset_id: null,
    sample_rate_hz: 16000,
    voice_id: null,
  });
  send("tts.chunk_meta", { client_message_id: cid, seq: 0, byte_length: 640 });

  // Mid-utterance and STAYING there. §25.3's `speaking` is a state a person
  // sits in for seconds; a script that reached `tts.end` in the same tick left
  // it unobservable from a browser, and a test asserting it was asserting a
  // frame that had already gone by.
  if (behaviour === "speaking") return;

  if (behaviour === "tts_kill") {
    // §8's ladder. `barge_in` and NOT `tts.end`: a cut utterance has no total
    // duration that was ever true, so a scrubber over it would be a lie.
    send("barge_in", {
      cancelled_client_message_id: cid,
      cancelled_after_chunk_seq: 0,
      reason: "provider_failed",
    });
    send("handoff.to_text", { conversation_id: "c1", reason: "tts_provider_failed" });
    return;
  }

  if (behaviour === "warning") {
    send("entitlement.warning", {
      // §32.9 fires at 5 AND at 2, and the two render different sentences
      // through the same ICU plural — the singular/plural split is exactly the
      // kind of thing a single-threshold baseline would never show.
      minutes_left: scenario.warningMinutes ?? 5,
      minutes_quota: 300,
      plan: "monthly",
      message_key: "ui.call.warning_minutes",
    });
  }

  send("tts.end", { client_message_id: cid, duration_ms: 3400 });

  if (behaviour === "exhausted") {
    send("handoff.to_text", { conversation_id: "c1", reason: "entitlement_exhausted" });
  }
}

/** The same map the real service carries, kept in step by `ask-ws.spec.ts`. */
function presenceFor(stage) {
  return (
    {
      safety_pre: "listening",
      intent: "listening",
      memory_retrieval: "thoughtful",
      fact_tools: "thoughtful",
      generation: "speaking_soft",
    }[stage] ?? null
  );
}

server.listen(port, "127.0.0.1", () => {
  console.log(`[stub-realtime] ws://127.0.0.1:${port} (${turns.size} recorded turns)`);
});
