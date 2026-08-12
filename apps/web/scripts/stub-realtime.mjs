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
 * Text frames only, which is all §34.6's control events need — binary is
 * refused on the chat socket until M9 anyway, so there is nothing this has to
 * frame that does not fit. Node's `crypto` and `net` are enough.
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
  let seq = 0;
  let buffered = Buffer.alloc(0);

  const send = (type, payload, ack = null) =>
    socket.write(encode(JSON.stringify({ type, seq: seq++, ts: Date.now(), ack, payload })));

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
      if (frame.opcode !== 0x1) continue;

      let event;
      try {
        event = JSON.parse(frame.payload.toString("utf-8"));
      } catch {
        continue;
      }
      const scenario = scenarioFor(client);

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

      if (event.type === "session.end") {
        socket.end();
        return;
      }
    }
  });

  socket.on("error", () => socket.destroy());
});

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
