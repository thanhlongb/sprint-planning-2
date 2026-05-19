/**
 * US-07: React UI Human Proxy — A2A proxy server (Hono + Bun)
 *
 * Runs on port 5174. Exposes:
 *   GET  /.well-known/agent.json  — Agent Card (AC1)
 *   POST /a2a/tasks               — receive tasks from platform (AC1)
 *   GET  /a2a/tasks/:task_id      — SSE stream for platform to await completion (AC1)
 *   GET  /proxy/tasks             — SSE stream that pushes tasks to the browser (AC7)
 *   POST /proxy/respond           — browser submits human response (AC5)
 *   GET  /proxy/session/:id       — fetch session details from platform
 *   POST /proxy/join              — human joins session (passes proxy endpoint to platform)
 *
 * Design: docs/decisions/DR-07-ui-proxy-architecture.md
 */

import { Hono } from "hono";
import { cors } from "hono/cors";

const PORT = Number(process.env.PROXY_PORT ?? 5174);
const PUBLIC_URL = (process.env.PROXY_PUBLIC_URL ?? `http://localhost:${PORT}`).replace(/\/$/, "");
const PLATFORM_URL = (process.env.PLATFORM_URL ?? "http://platform:8000").replace(/\/$/, "");

// Global unhandled rejection handler to prevent process exit on floating promises
process.on("unhandledRejection", (reason, promise) => {
  console.error("[ui-proxy] Unhandled Rejection at:", promise, "reason:", reason);
});

// ── Types ──────────────────────────────────────────────────────────────────────

interface TaskEnvelope {
  task_id: string;
  task_type: string;
  session_ctx: Record<string, unknown>;
  payload: Record<string, unknown>;
}

/** Callbacks registered by platform SSE subscribers, keyed by task_id. */
type SseResolver = (artifact: Record<string, unknown> | null, error?: string) => void;

/** Callbacks registered by browser SSE subscribers, keyed by participant_id. */
type BrowserPushFn = (envelope: TaskEnvelope) => void;

// ── In-memory state ────────────────────────────────────────────────────────────

/** task_id → { resolve, envelope } — awaiting human response */
const pendingTasks = new Map<
  string,
  { resolver: SseResolver; envelope: TaskEnvelope }
>();

/** participant_id → list of push callbacks (one per open browser SSE connection) */
const browserListeners = new Map<string, Set<BrowserPushFn>>();

/** participant_id → queued envelopes for when browser reconnects */
const browserBacklog = new Map<string, TaskEnvelope[]>();

// ── Task types that require human interaction (async 202 + SSE) ───────────────
const ASYNC_TASK_TYPES = new Set(["vote", "assign_opportunity", "confirm"]);

// ── Helpers ────────────────────────────────────────────────────────────────────

function pushToBrowserListeners(
  participant_id: string | null,
  envelope: TaskEnvelope
) {
  // If participant_id is provided, push to that participant only.
  // Otherwise push to all connected browsers (broadcast).
  const targets = participant_id
    ? [participant_id]
    : Array.from(browserListeners.keys());

  for (const pid of targets) {
    const listeners = browserListeners.get(pid);
    if (listeners && listeners.size > 0) {
      for (const fn of listeners) fn(envelope);
    } else {
      // No browser connected yet — queue for later
      if (!browserBacklog.has(pid)) browserBacklog.set(pid, []);
      browserBacklog.get(pid)!.push(envelope);
    }
  }
}

function sseData(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

// ── App ────────────────────────────────────────────────────────────────────────

const app = new Hono();
app.use("*", cors({ origin: "*" }));

// ── GET /.well-known/agent.json — Agent Card (AC1) ────────────────────────────

app.get("/.well-known/agent.json", (c) => {
  return c.json({
    name: "human-proxy",
    description: "React UI proxy acting as an A2A Remote Agent for human participants.",
    role: "HUMAN",
    capabilities: { can_vote: true, can_volunteer: true, can_provide_backlog: false },
    endpoint: `${PUBLIC_URL}/a2a`,
    auth: { scheme: "none" },
  });
});

// ── POST /a2a/tasks — receive task from platform (AC1) ────────────────────────

app.post("/a2a/tasks", async (c) => {
  const envelope = await c.req.json<TaskEnvelope>();
  const { task_id, task_type } = envelope;

  // Derive participant_id from session_ctx if present
  const participant_id =
    (envelope.payload?.for_participant_id as string | undefined) ?? null;

  if (!ASYNC_TASK_TYPES.has(task_type)) {
    // Informational tasks — ack immediately; push to browser for display only
    pushToBrowserListeners(participant_id, envelope);
    return c.json({ task_id, status: "completed", artifact: { ack: true } });
  }

  // Interactive task — push to browser and return 202; platform will poll SSE
  pushToBrowserListeners(participant_id, envelope);

  // Store a pending entry; resolver is filled when platform opens the SSE stream
  pendingTasks.set(task_id, {
    // placeholder — will be replaced when SSE stream opens
    resolver: () => {},
    envelope,
  });

  c.status(202);
  return c.json({ task_id, status: "working" });
});

// ── GET /a2a/tasks/:task_id — SSE for platform to await completion (AC1) ──────

app.get("/a2a/tasks/:task_id", async (c) => {
  const task_id = c.req.param("task_id");

  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  const write = async (payload: unknown) => {
    await writer.write(encoder.encode(sseData(payload)));
  };

  // Kick off async handler — don't await here so we return the streaming response
  (async () => {
    const pending = pendingTasks.get(task_id);
    if (!pending) {
      await write({ task_id, status: "failed", error: "unknown task_id" });
      await writer.close();
      return;
    }

    // Send initial working event
    try {
      await write({ task_id, status: "working", progress: "awaiting human response" });
    } catch (err) {
      console.error(`[ui-proxy] Initial write failed for task ${task_id}:`, err);
      await writer.close().catch(() => {});
      return;
    }

    // Register resolver: triggered by POST /proxy/respond
    await new Promise<void>((resolve) => {
      pendingTasks.set(task_id, {
        ...pending,
        resolver: async (artifact, error) => {
          try {
            if (error) {
              await write({ task_id, status: "failed", error });
            } else {
              await write({ task_id, status: "completed", artifact });
            }
          } catch (err) {
            console.error(`[ui-proxy] Failed to write result for task ${task_id}:`, err);
          } finally {
            pendingTasks.delete(task_id);
            await writer.close().catch(() => {});
            resolve();
          }
        },
      });
    });
  })().catch(err => {
    console.error(`[ui-proxy] Task SSE loop error for ${task_id}:`, err);
  });

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
});

// ── GET /proxy/tasks — SSE stream to push tasks to the browser (AC7) ──────────

app.get("/proxy/tasks", async (c) => {
  const participant_id = c.req.query("participant_id") ?? "anonymous";

  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  const write = async (payload: unknown) => {
    try {
      await writer.write(encoder.encode(sseData(payload)));
    } catch {
      // Client disconnected — ignore write errors
    }
  };

  const pushFn: BrowserPushFn = (envelope) => {
    write(envelope);
  };

  // Register listener
  if (!browserListeners.has(participant_id)) {
    browserListeners.set(participant_id, new Set());
  }
  browserListeners.get(participant_id)!.add(pushFn);

  // Drain backlog
  const backlog = browserBacklog.get(participant_id) ?? [];
  browserBacklog.delete(participant_id);

  // Send connected event + backlog asynchronously
  let active = true;
  (async () => {
    try {
      await write({ type: "connected", participant_id });
      for (const envelope of backlog) {
        await write(envelope);
      }
      // Heartbeat loop — keep connection alive while tab is open (AC7)
      while (active) {
        await Bun.sleep(15000);
        if (!active) break;
        await write({ type: "heartbeat" });
      }
    } catch (err) {
      console.error(`[ui-proxy] Browser SSE error for ${participant_id}:`, err);
    }
  })().catch(err => {
    console.error(`[ui-proxy] Browser SSE loop error for ${participant_id}:`, err);
  });

  // Clean up on disconnect
  const cleanup = () => {
    active = false;
    browserListeners.get(participant_id)?.delete(pushFn);
    writer.close().catch(() => {});
  };

  c.req.raw.signal.addEventListener("abort", cleanup);

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
});

// ── POST /proxy/respond — browser submits human response (AC5) ────────────────

app.post("/proxy/respond", async (c) => {
  const { task_id, artifact } = await c.req.json<{
    task_id: string;
    artifact: Record<string, unknown>;
  }>();

  const pending = pendingTasks.get(task_id);
  if (!pending) {
    return c.json({ error: "unknown task_id or already resolved" }, 404);
  }

  pending.resolver(artifact);
  return c.json({ ok: true, task_id });
});

// ── POST /proxy/human-message — relay US-27 human chat message to platform ────

app.post("/proxy/human-message", async (c) => {
  const body = await c.req.json<{
    session_id: string;
    sender_id: string;
    sender_name: string;
    content: string;
    target?: string;
  }>();

  const { session_id, ...rest } = body;
  try {
    const resp = await fetch(
      `${PLATFORM_URL}/sessions/${session_id}/human-message`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rest),
      }
    );
    const data = await resp.json();
    return c.json(data, resp.status as any);
  } catch {
    return c.json({ error: "platform unreachable" }, 502);
  }
});

// ── GET /proxy/comm-feed — relay US-26 comm-feed SSE from platform ────────────

app.get("/proxy/comm-feed", async (c) => {
  const session_id = c.req.query("session_id");
  if (!session_id) return c.json({ error: "session_id required" }, 400);

  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();

  (async () => {
    try {
      const resp = await fetch(
        `${PLATFORM_URL}/sessions/${session_id}/comm-feed`,
        { headers: { Accept: "text/event-stream" } }
      );
      if (!resp.ok || !resp.body) {
        await writer.close().catch(() => {});
        return;
      }
      // @ts-ignore — Bun supports async iteration over response body
      for await (const chunk of resp.body) {
        await writer.write(chunk);
      }
    } catch {
      // Client disconnected or platform unavailable
    } finally {
      await writer.close().catch(() => {});
    }
  })();

  c.req.raw.signal.addEventListener("abort", () => {
    writer.close().catch(() => {});
  });

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
});

// ── GET /proxy/session/:session_id — fetch session details ────────────────────

app.get("/proxy/session/:session_id", async (c) => {
  const session_id = c.req.param("session_id");
  try {
    const resp = await fetch(`${PLATFORM_URL}/sessions/${session_id}`);
    const data = await resp.json();
    return c.json(data, resp.status as any);
  } catch (err) {
    return c.json({ error: "platform unreachable" }, 502);
  }
});

// ── POST /proxy/join — human joins session (includes proxy endpoint) ──────────

app.post("/proxy/join", async (c) => {
  const { session_id, name, role } = await c.req.json<{
    session_id: string;
    name: string;
    role: string;
  }>();

  try {
    const resp = await fetch(`${PLATFORM_URL}/sessions/${session_id}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        role,
        endpoint: `${PUBLIC_URL}/a2a`,
      }),
    });
    const data = await resp.json();
    return c.json(data, resp.status as any);
  } catch (err) {
    return c.json({ error: "platform unreachable" }, 502);
  }
});

// ── Start ──────────────────────────────────────────────────────────────────────

const server = Bun.serve({
  port: PORT,
  fetch: app.fetch,
});

console.log(`[ui-proxy] Listening on http://localhost:${PORT}`);
console.log(`[ui-proxy] Public URL: ${PUBLIC_URL}`);
console.log(`[ui-proxy] Platform URL: ${PLATFORM_URL}`);
