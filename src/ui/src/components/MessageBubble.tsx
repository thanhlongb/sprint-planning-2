/**
 * MessageBubble — renders a single message in the chat-centric UI.
 *
 * Supports: platform (system), human, AI agent messages, and action notifications.
 * Provides platform-rich cards for task lists / assignments.
 */
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

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
  message_kind:
    | "task_request"
    | "task_response"
    | "thought"
    | "human_message"
    | "discussion_action"
    | "broadcast"
    | "chat"
    | "agent_chat"
    | "agent_reply";
  content: Record<string, unknown> | string;
}

export interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: string;
}

interface Props {
  event: CommEvent;
  participants: Participant[];
  myParticipantId?: string;
}

// ── Role config ──────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  PRODUCT_OWNER:
    "bg-indigo-500/10 text-indigo-700 border-indigo-500/30 dark:text-indigo-400",
  DEVELOPER:
    "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400",
  ARCHITECT:
    "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
  SCRUM_MASTER:
    "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-400",
  platform: "bg-muted text-muted-foreground border-border",
};

const AVATAR_BG: Record<string, string> = {
  PRODUCT_OWNER: "bg-indigo-500",
  DEVELOPER: "bg-emerald-500",
  ARCHITECT: "bg-amber-500",
  SCRUM_MASTER: "bg-violet-500",
  platform: "bg-muted-foreground",
};

const TASK_TYPE_LABELS: Record<string, string> = {
  present_backlog: "Present Backlog",
  vote: "Vote",
  assign_opportunity: "Assign",
  acknowledge_assignment: "Acknowledge",
  confirm: "Confirm",
  sprint_backlog: "Sprint Backlog",
  discussion_update: "Discussion Update",
  add_item: "Add Item",
  remove_item: "Remove Item",
  modify_item: "Modify Item",
  volunteer: "Volunteer",
  object: "Objection",
  reassign: "Reassign",
  recommendation_phase: "Recommendation",
  assignment_phase: "Assignment Discussion",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function getRoleForName(name: string, participants: Participant[]): string {
  const p = participants.find((p) => p.name === name);
  return p?.role ?? "platform";
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatContent(
  taskType: string,
  kind: string,
  content: Record<string, unknown> | string
): string {
  if (kind === "human_message") {
    if (typeof content === "string") return content;
    const c = content as Record<string, unknown>;
    return typeof c.content === "string" ? c.content : JSON.stringify(c);
  }
  if (kind === "thought") {
    return typeof content === "string" ? content : JSON.stringify(content);
  }

  const c =
    typeof content === "object" && content !== null
      ? (content as Record<string, unknown>)
      : {};

  // discussion actions
  switch (taskType) {
    case "add_item": {
      const item = (c.item as Record<string, unknown>) ?? c;
      return `Added: "${item.title ?? c.item_id}"${c.story_points ? ` (${c.story_points} SP)` : ""}`;
    }
    case "remove_item":
      return `Removed: "${c.item_id}"`;
    case "modify_item":
      return `Modified: "${c.item_id}" — ${JSON.stringify(c.updates)}`;
    case "volunteer":
      return `Volunteered for "${c.item_id}"`;
    case "object":
      return `Objected to "${c.item_id}": ${c.reason ?? ""}`;
    case "reassign":
      return `Reassigned "${c.item_id}" to ${c.to_participant_id}`;
  }

  // discussion_update broadcasts
  if (taskType === "discussion_update") {
    const ctx = c.context as string;
    if (ctx === "recommendation") {
      const items = c.items as unknown[];
      return `Recommendation: ${items?.length ?? 0} items (round ${c.round})`;
    }
    if (ctx === "assignment") {
      const asgn = c.assignments as Record<string, unknown>;
      return `Assignments: ${Object.keys(asgn ?? {}).length} mapped (round ${c.round})`;
    }
    return `State update (${ctx})`;
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
      default:
        return TASK_TYPE_LABELS[taskType] ?? taskType;
    }
  }

  if (kind === "task_response") {
    switch (taskType) {
      case "vote":
        return `Submitted ${Object.keys((c.votes as Record<string, string>) ?? {}).length} votes`;
      case "assign_opportunity":
        return c.volunteer ? "Volunteered" : "Declined";
      case "confirm":
        return c.confirmed ? "Confirmed" : "Rejected";
      default:
        return JSON.stringify(content).slice(0, 120);
    }
  }

  if (kind === "chat" || kind === "agent_chat" || kind === "agent_reply") {
    return typeof content === "string" ? content : JSON.stringify(content);
  }

  return JSON.stringify(content).slice(0, 120);
}

function isActionNotification(taskType: string, kind: string): boolean {
  return (
    kind === "discussion_action" ||
    ["add_item", "remove_item", "modify_item", "volunteer", "object", "reassign"].includes(taskType)
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MessageBubble({ event, participants, myParticipantId }: Props) {
  const isHumanMessage = event.message_kind === "human_message";
  const isMyMessage = event.sender_id === myParticipantId;
  const isAction = isActionNotification(event.task_type, event.message_kind);
  const role = getRoleForName(event.sender_name, participants);
  const summary = formatContent(event.task_type, event.message_kind, event.content);
  const colorClass = ROLE_COLORS[role] ?? ROLE_COLORS.platform;
  const avatarBg = AVATAR_BG[role] ?? AVATAR_BG.platform;
  const isAi =
    participants.find((p) => p.name === event.sender_name)?.type === "AI_AGENT";
  const isPlatform = event.sender_name === "Platform" || role === "platform";

  // ── Action notification: compact inline notification ───────────────────────
  if (isAction) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex justify-center py-1"
      >
        <span className="text-xs bg-muted/50 text-muted-foreground px-3 py-1 rounded-full">
          <span className="font-medium">{event.sender_name}</span>{" "}
          {summary.replace(/^Added: /, "added ").replace(/^Removed: /, "removed ").replace(/^Modified: /, "modified ").replace(/^Volunteered /, "volunteered ").replace(/^Objected /, "objected ").replace(/^Reassigned /, "reassigned ")}
        </span>
      </motion.div>
    );
  }

  // ── Platform / System message ──────────────────────────────────────────────
  if (isPlatform) {
    const hasRichContent =
      event.task_type === "discussion_update" &&
      event.content &&
      typeof event.content === "object";

    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex gap-3 px-1"
      >
        {/* Platform icon */}
        <div className="w-7 h-7 shrink-0 rounded-full bg-muted flex items-center justify-center text-xs mt-0.5">
          ⚙
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs font-semibold text-muted-foreground">
              Platform
            </span>
            <span className="text-[9px] text-muted-foreground/60">
              {formatTime(event.timestamp)}
            </span>
          </div>
          {hasRichContent ? (
            <div className="bg-muted/30 border border-border rounded-lg p-3 space-y-2">
              <p className="text-sm font-medium text-foreground">{summary}</p>
              {(event.content as any).items && (
                <div className="space-y-1">
                  {((event.content as any).items as any[]).slice(0, 5).map((item: any, i: number) => (
                    <div
                      key={item.item_id ?? i}
                      className="text-xs text-muted-foreground flex items-center gap-2"
                    >
                      <span className="font-mono">{item.item_id}</span>
                      <span>{item.title}</span>
                      {item.story_points != null && (
                        <Badge variant="outline" className="text-[10px] h-4 px-1">
                          {item.story_points} SP
                        </Badge>
                      )}
                    </div>
                  ))}
                  {((event.content as any).items as any[]).length > 5 && (
                    <p className="text-[10px] text-muted-foreground/60 italic">
                      +{((event.content as any).items as any[]).length - 5} more items
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="bg-muted/30 border border-border rounded-lg px-3 py-2">
              <p className="text-sm text-foreground leading-snug">{summary}</p>
            </div>
          )}
        </div>
      </motion.div>
    );
  }

  // ── AI Agent message ───────────────────────────────────────────────────────
  if (isAi) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex gap-3 px-1"
      >
        {/* Agent avatar */}
        <div
          className={`w-7 h-7 shrink-0 rounded-full ${avatarBg} flex items-center justify-center text-[11px] font-bold text-white mt-0.5`}
        >
          {event.sender_name.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span
              className={`text-xs font-semibold px-1 py-0 rounded border ${colorClass}`}
            >
              {event.sender_name}
            </span>
            <Badge variant="outline" className="text-[9px] h-4 px-1">
              AI
            </Badge>
            <span className="text-[9px] text-muted-foreground/60">
              {formatTime(event.timestamp)}
            </span>
          </div>
          <div className="bg-secondary/30 border border-secondary rounded-lg px-3 py-2">
            <p className="text-sm text-foreground leading-snug">{summary}</p>
          </div>
        </div>
      </motion.div>
    );
  }

  // ── Human message (chat bubble) ────────────────────────────────────────────
  const isOwn = isMyMessage;
  const bubbleStyle = isOwn
    ? "bg-primary text-primary-foreground ml-auto"
    : "bg-accent text-accent-foreground";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 px-1 ${isOwn ? "justify-end" : ""}`}
    >
      {!isOwn && (
        <div
          className={`w-7 h-7 shrink-0 rounded-full ${avatarBg} flex items-center justify-center text-[11px] font-bold text-white mt-0.5`}
        >
          {event.sender_name.charAt(0).toUpperCase()}
        </div>
      )}
      <div className={`max-w-[75%] ${isOwn ? "order-first" : ""}`}>
        <div
          className={`flex items-center gap-2 mb-0.5 ${isOwn ? "justify-end" : ""}`}
        >
          <span className="text-xs font-semibold text-foreground">
            {isOwn ? "You" : event.sender_name}
          </span>
          <span className="text-[9px] text-muted-foreground/60">
            {formatTime(event.timestamp)}
          </span>
        </div>
        <div className={`rounded-lg px-3 py-2 ${bubbleStyle}`}>
          <p className="text-sm leading-snug break-words">{summary}</p>
        </div>
        {event.receiver_name && (
          <p
            className={`text-[9px] text-muted-foreground mt-0.5 ${isOwn ? "text-right" : ""}`}
          >
            → {event.receiver_name}
          </p>
        )}
      </div>
      {isOwn && (
        <div
          className={`w-7 h-7 shrink-0 rounded-full ${avatarBg} flex items-center justify-center text-[11px] font-bold text-white mt-0.5`}
        >
          {event.sender_name.charAt(0).toUpperCase()}
        </div>
      )}
    </motion.div>
  );
}
