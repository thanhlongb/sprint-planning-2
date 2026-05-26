/**
 * US-26 / US-27: Agent Communication Feed + Human Chat
 *
 * Displays a real-time feed of A2A messages exchanged between agents during
 * a sprint planning session.  Connects to GET /proxy/comm-feed?session_id=…
 * via SSE and renders task_request, task_response, thought, and human_message events.
 * US-27 adds a message composer for human participants to send freeform messages to agents.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ── Types ────────────────────────────────────────────────────────────────────

export interface CommEvent {
  event_type: string;
  comm_id: string;
  session_id: string;
  timestamp: string;
  sender_id: string;
  sender_name: string;
  receiver_id: string | null;
  receiver_name: string | null;
  task_type: string;
  message_kind: "task_request" | "task_response" | "thought" | "human_message" | "discussion_action" | "broadcast" | "chat" | "agent_chat" | "agent_reply";
  content: Record<string, unknown> | string;
}

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: string;
}

interface Props {
  sessionId: string;
  participants: Participant[];
  myParticipantId?: string;
  myName?: string;
  currentTaskType?: string;
}

// ── Constants ────────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  PRODUCT_OWNER:  "bg-indigo-500/10 text-indigo-700 border-indigo-500/30 dark:text-indigo-400",
  DEVELOPER:      "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400",
  ARCHITECT:      "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
  SCRUM_MASTER:   "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-400",
  platform:       "bg-muted text-muted-foreground border-border",
};

const AVATAR_BG: Record<string, string> = {
  PRODUCT_OWNER: "bg-indigo-500",
  DEVELOPER:     "bg-emerald-500",
  ARCHITECT:     "bg-amber-500",
  SCRUM_MASTER:  "bg-violet-500",
  platform:      "bg-muted-foreground",
};

const KIND_LABELS: Record<string, string> = {
  task_request:  "Request",
  task_response: "Response",
  thought:       "Thought",
  human_message: "Message",
  discussion_action: "Action",
  broadcast:     "Update",
  chat:          "Chat",
  agent_chat:    "Agent",
};

// Phases in which the composer is enabled (AC7) — includes v2 phases
const ACTIVE_PHASES = new Set([
  "session_ready",
  "present_backlog",
  "vote",
  "assign_opportunity",
  "confirm",
  "recommendation_phase",
  "assignment_phase",
  "confirmation_phase",
]);

const TASK_TYPE_LABELS: Record<string, string> = {
  present_backlog:      "Present Backlog",
  vote:                 "Vote",
  assign_opportunity:   "Assign",
  acknowledge_assignment: "Acknowledge",
  confirm:              "Confirm",
  sprint_backlog:       "Sprint Backlog",
  discussion_update:    "Discussion Update",
  add_item:             "Add Item",
  remove_item:          "Remove Item",
  modify_item:          "Modify Item",
  volunteer:            "Volunteer",
  object:               "Objection",
  reassign:             "Reassign",
  recommendation_phase: "Recommendation",
  assignment_phase:     "Assignment Discussion",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function getRoleForName(name: string, participants: Participant[]): string {
  const p = participants.find((p) => p.name === name);
  return p?.role ?? "platform";
}

function summariseContent(
  taskType: string,
  kind: "task_request" | "task_response" | "thought" | "human_message" | "discussion_action" | "broadcast" | "chat" | "agent_chat" | "agent_reply",
  content: Record<string, unknown> | string,
): string {
  if (kind === "human_message") {
    if (typeof content === "string") return content;
    const c = content as Record<string, unknown>;
    return typeof c.content === "string" ? c.content : JSON.stringify(c);
  }
  if (kind === "thought") {
    return typeof content === "string" ? content : JSON.stringify(content);
  }

  // Handle discussion actions and broadcast updates (v2)
  const c = typeof content === "object" && content !== null
    ? (content as Record<string, unknown>)
    : {};
  const action = taskType;

  // discussion_update broadcasts
  if (action === "discussion_update") {
    const ctx = c.context as string;
    if (ctx === "recommendation") {
      const items = c.items as unknown[];
      return `Recommendation update: ${items?.length ?? 0} items (round ${c.round})`;
    }
    if (ctx === "assignment") {
      const asgn = c.assignments as Record<string, unknown>;
      return `Assignment update: ${Object.keys(asgn ?? {}).length} assignments (round ${c.round})`;
    }
    return `Discussion state update (${ctx})`;
  }

  // discussion actions
  switch (action) {
    case "add_item": {
      const item = (c.item as Record<string, unknown>) ?? c;
      return `Add item: "${item.title ?? c.item_id}"`;
    }
    case "remove_item":
      return `Remove item: "${c.item_id}"`;
    case "modify_item":
      return `Modify item: "${c.item_id}" — ${JSON.stringify(c.updates)}`;
    case "volunteer":
      return `Volunteer for "${c.item_id}"`;
    case "object":
      return `Objected to assignment of "${c.item_id}": ${c.reason ?? ""}`;
    case "reassign":
      return `Reassigned "${c.item_id}" to ${c.to_participant_id}`;
  }

  if (kind === "task_request") {
    switch (taskType) {
      case "vote":
        return `Vote request on ${(c.items as string[])?.length ?? 0} items`;
      case "assign_opportunity":
        return `Volunteer request: "${c.title ?? c.item_id}"`;
      case "present_backlog":
        return "Backlog presentation requested";
      case "confirm":
        return `Confirm sprint plan (${(c.selected_items as string[])?.length ?? 0} items)`;
      case "acknowledge_assignment":
        return `Assignment: "${c.item_id}" → ${c.assignee_name}`;
      case "sprint_backlog":
        return `Final sprint backlog (${(c.selected_items as unknown[])?.length ?? 0} items)`;
      default:
        return TASK_TYPE_LABELS[taskType] ?? taskType;
    }
  }

  // task_response
  switch (taskType) {
    case "vote": {
      const votes = c.votes as Record<string, string> | undefined;
      return votes ? `Submitted ${Object.keys(votes).length} votes` : "Submitted votes";
    }
    case "assign_opportunity":
      return c.volunteer ? "Volunteered" : "Declined";
    case "present_backlog": {
      const items = (c.backlog as unknown[])?.length ?? 0;
      return `Submitted ${items} backlog item${items !== 1 ? "s" : ""}`;
    }
    case "confirm":
      return c.confirmed ? "Confirmed" : "Rejected";
    case "sprint_backlog":
      return "Acknowledged sprint backlog";
    default:
      return JSON.stringify(content).slice(0, 120);
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CommunicationFeed({
  sessionId,
  participants,
  myParticipantId,
  myName,
  currentTaskType,
}: Props) {
  const [events, setEvents] = useState<CommEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [filterAgent, setFilterAgent] = useState<string>("all");
  const [filterKind, setFilterKind] = useState<string>("all");
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [isOpen, setIsOpen] = useState(true);

  // Composer state (US-27)
  const [composerText, setComposerText] = useState("");
  const [composerTarget, setComposerTarget] = useState<string>("all");
  const [isSending, setIsSending] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const processingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  // Track whether the user is scrolled near the bottom
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottomRef.current) setHasNewMessages(false);
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    setHasNewMessages(false);
  }, []);

  // Clear processing indicator when an agent replies with a thought for human_message (US-27)
  useEffect(() => {
    if (!isProcessing) return;
    const lastEvent = events[events.length - 1];
    if (lastEvent?.task_type === "human_message" && lastEvent?.message_kind === "thought") {
      if (processingTimerRef.current) clearTimeout(processingTimerRef.current);
      setIsProcessing(false);
    }
  }, [events, isProcessing]);

  // Cleanup processing timer on unmount
  useEffect(() => {
    return () => {
      if (processingTimerRef.current) clearTimeout(processingTimerRef.current);
    };
  }, []);

  // Send human message (US-27)
  const handleSend = useCallback(async () => {
    const text = composerText.trim();
    if (!text || !myParticipantId || !myName || isSending) return;

    setIsSending(true);

    // Optimistic insert
    const optimisticEvent: CommEvent = {
      event_type: "comm_event",
      comm_id: `optimistic-${Date.now()}`,
      session_id: sessionId,
      timestamp: new Date().toISOString(),
      sender_id: myParticipantId,
      sender_name: myName,
      receiver_id: composerTarget === "all" ? null : composerTarget,
      receiver_name: composerTarget === "all" ? null : composerTarget,
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
          target: composerTarget,
        }),
      });

      // Show processing indicator for up to 10s
      setIsProcessing(true);
      processingTimerRef.current = setTimeout(() => setIsProcessing(false), 10000);
    } catch {
      // Silently fail — optimistic message already shown
    } finally {
      setIsSending(false);
    }
  }, [composerText, composerTarget, myParticipantId, myName, isSending, sessionId]);

  const composerEnabled =
    !!myParticipantId &&
    !!myName &&
    !!currentTaskType &&
    ACTIVE_PHASES.has(currentTaskType);

  // Derive AI agent names for composer target selector
  const aiAgentNames = Array.from(
    new Set(
      participants
        .filter((p) => p.type === "AI_AGENT")
        .map((p) => p.name)
    )
  );

  // SSE connection
  useEffect(() => {
    if (!sessionId || !isOpen) return;

    const es = new EventSource(`/proxy/comm-feed?session_id=${encodeURIComponent(sessionId)}`);

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") { setConnected(true); return; }
        if (data.event_type !== "comm_event") return;

        const ce = data as CommEvent;
        setEvents((prev) => {
          if (prev.some((e) => e.comm_id === ce.comm_id)) return prev;
          return [...prev, ce];
        });

        // Auto-scroll or show indicator
        setTimeout(() => {
          if (atBottomRef.current) {
            scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
          } else {
            setHasNewMessages(true);
          }
        }, 30);
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [sessionId, isOpen]);

  // Derive unique agent names for filter dropdown
  const agentNames = Array.from(new Set(events.map((e) => e.sender_name)));

  // Apply filters
  const visible = events.filter((e) => {
    if (filterAgent !== "all" && e.sender_name !== filterAgent) return false;
    if (filterKind !== "all" && e.message_kind !== filterKind) return false;
    return true;
  });

  return (
    <div className="mt-4 rounded-lg border bg-card">
      {/* Header */}
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Communication Feed
          </span>
          {events.length > 0 && (
            <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
              {events.length}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connected ? "bg-green-500" : "bg-muted animate-pulse"
            }`}
          />
          <span className="text-muted-foreground text-xs">{isOpen ? "▲" : "▼"}</span>
        </div>
      </button>

      {isOpen && (
        <>
          {/* Filters */}
          <div className="flex items-center gap-2 px-3 pb-2 border-t pt-2">
            <select
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              className="text-xs rounded border border-border bg-background px-1.5 py-0.5 text-foreground"
            >
              <option value="all">All agents</option>
              {agentNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
            <div className="flex gap-1 flex-wrap">
              {(["all", "task_request", "task_response", "thought", "human_message", "discussion_action", "broadcast"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => setFilterKind(k)}
                  className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
                    filterKind === k
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:border-foreground"
                  }`}
                >
                  {k === "all" ? "All" : KIND_LABELS[k]}
                </button>
              ))}
            </div>
          </div>

          {/* Message list */}
          <div className="relative">
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="h-80 overflow-y-auto px-3 pb-3 space-y-2"
            >
              {visible.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-8">
                  {events.length === 0 ? "Waiting for agent activity…" : "No messages match the current filter."}
                </p>
              ) : (
                <AnimatePresence initial={false}>
                  {visible.map((event) => (
                    <CommMessage
                      key={event.comm_id}
                      event={event}
                      participants={participants}
                    />
                  ))}
                </AnimatePresence>
              )}
            </div>

            {/* New messages indicator (AC7) */}
            {hasNewMessages && (
              <button
                onClick={scrollToBottom}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1 text-xs bg-primary text-primary-foreground px-3 py-1 rounded-full shadow-lg hover:bg-primary/90 transition-colors"
              >
                New messages ↓
              </button>
            )}
          </div>

          {/* Message composer (US-27) */}
          <div className={`border-t px-3 py-2 space-y-1.5 ${!composerEnabled ? "opacity-50" : ""}`}>
            {isProcessing && (
              <p className="text-[10px] text-muted-foreground animate-pulse">
                Agents are processing your message…
              </p>
            )}
            <div className="flex gap-1.5">
              <select
                value={composerTarget}
                onChange={(e) => setComposerTarget(e.target.value)}
                disabled={!composerEnabled}
                className="text-xs rounded border border-border bg-background px-1.5 py-0.5 text-foreground shrink-0"
              >
                <option value="all">All</option>
                {aiAgentNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <input
                type="text"
                value={composerText}
                onChange={(e) => setComposerText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && composerEnabled) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                disabled={!composerEnabled}
                placeholder={
                  composerEnabled
                    ? "Message agents… (Enter to send)"
                    : "Chat available during active phases"
                }
                className="flex-1 min-w-0 text-xs rounded border border-border bg-background px-2 py-1 text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed"
              />
              <Button
                size="sm"
                variant="default"
                disabled={!composerEnabled || !composerText.trim() || isSending}
                onClick={handleSend}
                className="text-xs h-7 px-2 shrink-0"
              >
                {isSending ? "…" : "Send"}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Single message bubble ──────────────────────────────────────────────────────

function CommMessage({
  event,
  participants,
}: {
  event: CommEvent;
  participants: Participant[];
}) {
  const [expanded, setExpanded] = useState(false);

  const isHumanMessage = event.message_kind === "human_message";
  const isThought = event.message_kind === "thought";

  // Human messages render right-aligned in a distinct style
  if (isHumanMessage) {
    const summary = summariseContent(event.task_type, event.message_kind, event.content);
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex flex-col items-end gap-0.5"
      >
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] text-muted-foreground">{formatTime(event.timestamp)}</span>
          <Badge variant="secondary" className="text-[9px] h-3.5 px-1 py-0">You</Badge>
          <span className="text-[11px] font-semibold text-foreground">{event.sender_name}</span>
        </div>
        <div className="bg-primary/10 border border-primary/20 rounded-lg px-2.5 py-1.5 max-w-[85%]">
          <p className="text-xs text-foreground leading-snug break-words">{summary}</p>
        </div>
        {event.receiver_name && (
          <span className="text-[9px] text-muted-foreground">→ {event.receiver_name}</span>
        )}
      </motion.div>
    );
  }

  const role = getRoleForName(event.sender_name, participants);
  const colorClass = ROLE_COLORS[role] ?? ROLE_COLORS.platform;
  const avatarBg = AVATAR_BG[role] ?? AVATAR_BG.platform;
  const summary = summariseContent(event.task_type, event.message_kind, event.content);
  const TRUNCATE_AT = 160;
  const shouldTruncate = isThought && summary.length > TRUNCATE_AT;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-2 ${isThought ? "opacity-70" : ""}`}
    >
      {/* Avatar */}
      <div
        className={`w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-[10px] font-bold text-white mt-0.5 ${avatarBg}`}
      >
        {event.sender_name.charAt(0).toUpperCase()}
      </div>

      <div className="flex-1 min-w-0">
        {/* Header row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`text-[11px] font-semibold px-1 py-0 rounded border ${colorClass}`}>
            {event.sender_name}
          </span>
          {event.receiver_name && event.message_kind !== "thought" && (
            <>
              <span className="text-[10px] text-muted-foreground">→</span>
              <span className="text-[11px] text-muted-foreground">{event.receiver_name}</span>
            </>
          )}
          <Badge
            variant="outline"
            className={`text-[9px] h-3.5 px-1 py-0 ${
              isThought
                ? "border-amber-500/40 text-amber-600"
                : event.message_kind === "task_request"
                ? "border-blue-500/40 text-blue-600"
                : "border-green-500/40 text-green-600"
            }`}
          >
            {KIND_LABELS[event.message_kind]}
          </Badge>
          <span className="text-[9px] text-muted-foreground ml-auto shrink-0">
            {formatTime(event.timestamp)}
          </span>
        </div>

        {/* Content */}
        <p
          className={`text-xs mt-0.5 leading-snug break-words ${
            isThought ? "italic text-muted-foreground" : "text-foreground"
          }`}
        >
          {shouldTruncate && !expanded
            ? `${summary.slice(0, TRUNCATE_AT)}…`
            : summary}
          {shouldTruncate && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="ml-1 text-primary underline-offset-2 hover:underline"
            >
              {expanded ? "Read less" : "Read more"}
            </button>
          )}
        </p>

        {/* Task type label for requests/responses */}
        {!isThought && (
          <span className="text-[9px] text-muted-foreground/60">
            {TASK_TYPE_LABELS[event.task_type] ?? event.task_type}
          </span>
        )}
      </div>
    </motion.div>
  );
}
