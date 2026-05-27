/**
 * ChatPanel — the discussion feed (left panel) for v2 chat-centric sessions.
 *
 * Subscribes to /proxy/comm-feed SSE for all discussion events.
 * Renders message list with MessageBubble.
 * Input bar with text input + quick action buttons that change by phase.
 * Parses slash commands client-side.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "@/components/MessageBubble";
import type { CommEvent, Participant } from "@/components/MessageBubble";

export type Phase = "recommendation" | "assignment" | "confirmation" | "complete" | "lobby";

// Re-export types for consumers
export type { Participant };

interface Props {
  sessionId: string;
  participants: Participant[];
  myParticipantId?: string;
  myName?: string;
  phase: Phase;
  sprintGoal: string;
}

// ── Slash command patterns ───────────────────────────────────────────────────

const SLASH_ADD = /^\/add\s+(.+?)(?:\s+(\d+)\s*SP?)?$/i;
const SLASH_REMOVE = /^\/remove\s+(\S+)$/i;
const SLASH_VOLUNTEER = /^\/volunteer\s+(\S+)$/i;
const SLASH_OBJECT = /^\/object\s+(\S+)$/i;
const SLASH_REASSIGN = /^\/reassign\s+(\S+)\s+(.+)$/i;

// ── Component ─────────────────────────────────────────────────────────────────

export function ChatPanel({
  sessionId,
  participants,
  myParticipantId,
  myName,
  phase,
  sprintGoal,
}: Props) {
  const [events, setEvents] = useState<CommEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [composerText, setComposerText] = useState("");
  const [isSending, setIsSending] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  // Track scroll position for auto-scroll
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }, []);

  // ── SSE subscription ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    const es = new EventSource(
      `/proxy/comm-feed?session_id=${encodeURIComponent(sessionId)}`
    );

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") {
          setConnected(true);
          return;
        }
        if (data.event_type !== "comm_event") return;

        const ce = data as CommEvent;
        setEvents((prev) => {
          if (prev.some((e) => e.comm_id === ce.comm_id)) return prev;
          return [...prev, ce];
        });

        // Auto-scroll on new messages
        setTimeout(() => {
          if (atBottomRef.current) {
            scrollRef.current?.scrollTo({
              top: scrollRef.current.scrollHeight,
            });
          }
        }, 30);
      } catch {
        // ignore malformed
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [sessionId]);

  // ── Send chat message ─────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = composerText.trim();
    if (!text || !myParticipantId || !myName || isSending) return;

    // Check for slash commands
    let match: RegExpMatchArray | null;

    if ((match = text.match(SLASH_ADD))) {
      const title = match[1].trim();
      const sp = match[2] ? parseInt(match[2]) : null;

      // Optimistic insert
      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: "add_item",
        message_kind: "discussion_action",
        content: { item: { title, story_points: sp } },
      };
      setEvents((prev) => [...prev, optEvent]);
      setComposerText("");
      setIsSending(true);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action: "add_item",
            content: {
              item: {
                item_id: `human-${Date.now()}`,
                title,
                description: "",
                priority: "MEDIUM",
                story_points: sp,
                labels: [],
                dependencies: [],
              },
            },
          }),
        });
      } catch {}
      setIsSending(false);
      return;
    }

    if ((match = text.match(SLASH_REMOVE))) {
      const itemId = match[1];

      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: "remove_item",
        message_kind: "discussion_action",
        content: { item_id: itemId },
      };
      setEvents((prev) => [...prev, optEvent]);
      setComposerText("");
      setIsSending(true);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action: "remove_item",
            content: { item_id: itemId },
          }),
        });
      } catch {}
      setIsSending(false);
      return;
    }

    if ((match = text.match(SLASH_VOLUNTEER)) && phase === "assignment") {
      const itemId = match[1];

      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: "volunteer",
        message_kind: "discussion_action",
        content: { item_id: itemId },
      };
      setEvents((prev) => [...prev, optEvent]);
      setComposerText("");
      setIsSending(true);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action: "volunteer",
            content: { item_id: itemId },
          }),
        });
      } catch {}
      setIsSending(false);
      return;
    }

    if ((match = text.match(SLASH_OBJECT)) && phase === "assignment") {
      const itemId = match[1];

      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: "object",
        message_kind: "discussion_action",
        content: { item_id: itemId, reason: "Objection raised" },
      };
      setEvents((prev) => [...prev, optEvent]);
      setComposerText("");
      setIsSending(true);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action: "object",
            content: { item_id: itemId, reason: "Objection raised" },
          }),
        });
      } catch {}
      setIsSending(false);
      return;
    }

    if ((match = text.match(SLASH_REASSIGN)) && phase === "assignment") {
      const itemId = match[1];
      const toName = match[2].trim();

      // Find participant ID by name
      const target = participants.find((p) => p.name === toName);
      const toPid = target?.participant_id ?? toName;

      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: "reassign",
        message_kind: "discussion_action",
        content: { item_id: itemId, to_participant_id: toPid },
      };
      setEvents((prev) => [...prev, optEvent]);
      setComposerText("");
      setIsSending(true);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action: "reassign",
            content: {
              item_id: itemId,
              to_participant_id: toPid,
              from_participant_id: "",
            },
          }),
        });
      } catch {}
      setIsSending(false);
      return;
    }

    // Regular chat message
    setIsSending(true);

    const optimisticEvent: CommEvent = {
      event_type: "comm_event",
      comm_id: `optimistic-${Date.now()}`,
      session_id: sessionId,
      timestamp: new Date().toISOString(),
      sender_id: myParticipantId,
      sender_name: myName,
      receiver_id: null,
      receiver_name: null,
      task_type: "human_message",
      message_kind: "human_message",
      content: text,
    };
    setEvents((prev) => [...prev, optimisticEvent]);
    setComposerText("");

    try {
      await fetch("/proxy/human-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          sender_id: myParticipantId,
          sender_name: myName,
          content: text,
        }),
      });
    } catch {}
    setIsSending(false);
  }, [
    composerText,
    myParticipantId,
    myName,
    isSending,
    sessionId,
    phase,
    participants,
  ]);

  // ── Quick action button handlers ──────────────────────────────────────────

  const sendQuickAction = useCallback(
    async (action: string, content: Record<string, unknown>) => {
      if (!myParticipantId || !myName) return;

      const optEvent: CommEvent = {
        event_type: "comm_event",
        comm_id: `optimistic-${Date.now()}`,
        session_id: sessionId,
        timestamp: new Date().toISOString(),
        sender_id: myParticipantId,
        sender_name: myName,
        receiver_id: null,
        receiver_name: null,
        task_type: action,
        message_kind: "discussion_action",
        content,
      };
      setEvents((prev) => [...prev, optEvent]);

      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName,
            action,
            content,
          }),
        });
      } catch {}
    },
    [sessionId, myParticipantId, myName]
  );

  const handleAddClick = () => {
    const itemId = `human-${Date.now()}`;
    sendQuickAction("add_item", {
      item: {
        item_id: itemId,
        title: "New item (click to edit in task panel)",
        description: "",
        priority: "MEDIUM",
        story_points: 3,
        labels: [],
        dependencies: [],
      },
    });
  };

  const handleRemoveClick = () => {
    sendQuickAction("remove_item", { item_id: "T-???" });
  };

  const handleModifyClick = () => {
    sendQuickAction("modify_item", {
      item_id: "T-???",
      updates: { story_points: 5 },
    });
  };

  const handleVolunteerClick = () => {
    sendQuickAction("volunteer", { item_id: "Select task in right panel" });
  };

  const handleObjectClick = () => {
    sendQuickAction("object", {
      item_id: "Select task in right panel",
      reason: "Objection",
    });
  };

  const handleReassignClick = () => {
    sendQuickAction("reassign", {
      item_id: "Select task in right panel",
      to_participant_id: "Select participant",
    });
  };

  // ── Agent names for participant lookup ────────────────────────────────────

  const agentNames = Array.from(
    new Set(participants.filter((p) => p.type === "AI_AGENT").map((p) => p.name))
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full border-r border-border">
      {/* Connection indicator + phase info */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-card/50 shrink-0">
        <span
          className={`w-2 h-2 rounded-full ${
            connected ? "bg-green-500" : "bg-muted animate-pulse"
          }`}
        />
        <span className="text-xs text-muted-foreground">
          {connected ? "Live" : "Connecting…"}
        </span>
        <span className="text-xs text-muted-foreground ml-auto">
          {events.length} messages
        </span>
      </div>

      {/* Message list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
      >
        {events.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-sm">No messages yet.</p>
            <p className="text-xs mt-1">
              Type a message or use quick actions to get started.
            </p>
            {sprintGoal && (
              <p className="text-xs mt-3 text-foreground/60">
                Sprint Goal:{" "}
                <span className="font-medium">{sprintGoal}</span>
              </p>
            )}
          </div>
        ) : (
          events.map((event) => (
            <MessageBubble
              key={event.comm_id}
              event={event}
              participants={participants}
              myParticipantId={myParticipantId}
            />
          ))
        )}
      </div>

      {/* Slash-command hints */}
      <div className="px-4 py-1 border-t border-border bg-muted/20 shrink-0">
        <p className="text-[10px] text-muted-foreground">
          Slash commands:{" "}
          {phase === "recommendation" || phase === "lobby" ? (
            <>
              <code className="bg-muted px-1 rounded">/add Title [SP]</code>{" "}
              <code className="bg-muted px-1 rounded">/remove T-001</code>
            </>
          ) : phase === "assignment" ? (
            <>
              <code className="bg-muted px-1 rounded">/volunteer T-001</code>{" "}
              <code className="bg-muted px-1 rounded">/object T-001</code>{" "}
              <code className="bg-muted px-1 rounded">/reassign T-001 Bob</code>
            </>
          ) : (
            <span>Free chat — no special commands in this phase</span>
          )}
        </p>
      </div>

      {/* Quick action buttons */}
      <div className="flex flex-wrap gap-1.5 px-4 py-2 border-t border-border bg-card/50 shrink-0">
        {phase === "recommendation" || phase === "lobby" ? (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleAddClick}
            >
              + Add Task
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleRemoveClick}
            >
              Remove
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleModifyClick}
            >
              Modify
            </Button>
          </>
        ) : phase === "assignment" ? (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleVolunteerClick}
            >
              Volunteer
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleObjectClick}
            >
              Object
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={handleReassignClick}
            >
              Reassign
            </Button>
          </>
        ) : null}
      </div>

      {/* Input bar */}
      <div className="flex gap-2 px-4 py-3 border-t border-border bg-card shrink-0">
        <input
          type="text"
          value={composerText}
          onChange={(e) => setComposerText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={!myParticipantId || !myName}
          placeholder={
            myParticipantId && myName
              ? phase === "recommendation"
                ? "Type a message or /add Title [SP]…"
                : phase === "assignment"
                ? "Type or /volunteer T-001, /reassign T-001 Bob…"
                : "Type a message…"
              : "Join session to chat"
          }
          className="flex-1 min-w-0 text-sm rounded-lg border border-border bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        <Button
          size="sm"
          disabled={
            !myParticipantId || !myName || !composerText.trim() || isSending
          }
          onClick={handleSend}
          className="text-xs h-9 px-3 shrink-0"
        >
          {isSending ? "…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
