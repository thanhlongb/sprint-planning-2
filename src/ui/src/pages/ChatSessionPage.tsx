/**
 * ChatSessionPage — main v2 session page with chat-centric layout.
 *
 * DESIGN: Two-panel layout — chat (left ~65%) + task state panel (right ~35%).
 * Phase state management via comm bus events. Routes to this page when
 * template contains "v2".
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ChatPanel } from "@/components/ChatPanel";
import { TaskPanel } from "@/components/TaskPanel";
import type { Phase, Participant } from "@/components/ChatPanel";

// ── Types ────────────────────────────────────────────────────────────────────

interface TaskEnvelope {
  task_id: string;
  task_type: string;
  session_ctx: Record<string, unknown>;
  payload: Record<string, unknown>;
}

// ── Phase helpers ────────────────────────────────────────────────────────────

const PHASE_NUM: Record<Phase, number> = {
  lobby: 0,
  recommendation: 1,
  assignment: 2,
  confirmation: 3,
  complete: 3,
};

const PHASE_NAME: Record<Phase, string> = {
  lobby: "Lobby",
  recommendation: "Task Refinement",
  assignment: "Assignment Discussion",
  confirmation: "PO Confirmation",
  complete: "Complete",
};

function getPhaseFromTaskType(taskType: string): Phase {
  switch (taskType) {
    case "session_invite":
    case "session_ready":
      return "lobby";
    case "present_backlog":
    case "vote":
    case "recommendation_phase":
    case "phase_started": // may carry phase in payload
      return "recommendation";
    case "assign_opportunity":
    case "assignment_phase":
      return "assignment";
    case "confirm":
    case "confirmation_phase":
    case "sprint_backlog":
      return "confirmation";
    default:
      return "lobby";
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export default function ChatSessionPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const navigate = useNavigate();
  const participantId =
    sessionStorage.getItem(`pid:${session_id}`) ?? "";
  const myName =
    sessionStorage.getItem(`name:${session_id}`) ?? undefined;

  const [phase, setPhase] = useState<Phase>("lobby");
  const [sprintGoal, setSprintGoal] = useState<string>("");
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const [planAccepted, setPlanAccepted] = useState(false);

  const sseRef = useRef<EventSource | null>(null);
  const latestTaskTypeRef = useRef<string>("");

  // ── SSE subscription for task events (phase changes, participants, etc.) ──
  useEffect(() => {
    if (!session_id) return;

    const url = `/proxy/tasks?participant_id=${encodeURIComponent(participantId || "anonymous")}`;
    const es = new EventSource(url);
    sseRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setConnectionError(false);
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "connected") {
          setConnected(true);
          return;
        }
        if (data.type === "heartbeat") return;

        const envelope = data as TaskEnvelope;
        if (!envelope.task_id || !envelope.task_type) return;

        // Track latest task type for phase inference
        latestTaskTypeRef.current = envelope.task_type;

        // Handle phase_started — may carry explicit phase info
        if (envelope.task_type === "phase_started") {
          const payloadPhase = (envelope.payload as any)?.phase as string;
          if (payloadPhase) {
            setPhase(payloadPhase as Phase);
          }
        }

        // Infer phase from task type
        const inferredPhase = getPhaseFromTaskType(envelope.task_type);
        if (inferredPhase !== "lobby") {
          setPhase(inferredPhase);
        }

        // Extract sprint goal
        const ctx = envelope.session_ctx as any;
        if (ctx?.sprint_goal) {
          setSprintGoal(ctx.sprint_goal as string);
        }

        // Extract participants
        if (ctx?.participants) {
          setParticipants(ctx.participants as Participant[]);
        }

        // Navigate to summary when session completes (sprint_backlog)
        if (envelope.task_type === "sprint_backlog" && session_id) {
          setPhase("confirmation");
          if ((envelope.payload as any)?.selected_items) {
            // Will render confirmation view via task panel
          }
        }

        // Handle acknowledge_assignment
        if (envelope.task_type === "acknowledge_assignment") {
          const pl = envelope.payload as {
            assignee_name?: string;
            item_id?: string;
          };
          toast.info(
            `Assignment: ${pl.item_id ?? "item"} → ${pl.assignee_name ?? "someone"}`
          );
        }
      } catch {
        // ignore malformed
      }
    };

    es.onerror = () => {
      setConnectionError(true);
    };

    return () => es.close();
  }, [session_id, participantId]);

  // ── Accept plan handler ──────────────────────────────────────────────────
  const handleAcceptPlan = useCallback(async () => {
    if (!session_id) return;

    try {
      // Find the confirm task and submit
      const resp = await fetch("/proxy/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: `conf_${session_id}`,
          artifact: { confirmed: true },
        }),
      });
      if (resp.ok) {
        setPlanAccepted(true);
        toast.success("Plan accepted!");
        setTimeout(() => {
          navigate(`/sessions/${session_id}/summary`);
        }, 3000);
      } else {
        toast.error("Failed to accept plan");
      }
    } catch {
      toast.error("Network error accepting plan");
    }
  }, [session_id, navigate]);

  // ── Render ────────────────────────────────────────────────────────────────

  const phaseNum = PHASE_NUM[phase];
  const phaseName = PHASE_NAME[phase];

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-card/80 shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold tracking-tight">
            HASP · Phase {phaseNum}/3 — {phaseName}
          </h1>
          {sprintGoal && (
            <span className="text-sm text-muted-foreground border-l border-border pl-4">
              Goal: <span className="font-medium text-foreground">{sprintGoal}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {session_id && (
            <span className="text-xs font-mono text-muted-foreground">
              {session_id.slice(0, 12)}…
            </span>
          )}
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                connectionError
                  ? "bg-destructive"
                  : connected
                  ? "bg-green-500"
                  : "bg-muted animate-pulse"
              }`}
            />
            <span className="text-xs text-muted-foreground">
              {connectionError
                ? "Reconnecting…"
                : connected
                ? "Connected"
                : "Connecting…"}
            </span>
          </div>
          <span className="text-xs text-muted-foreground border-l border-border pl-4">
            {participants.length} participants
          </span>
        </div>
      </header>

      {/* Two-panel layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left: Chat panel (~65%) */}
        <div className="w-[65%] min-w-0">
          <ChatPanel
            sessionId={session_id!}
            participants={participants}
            myParticipantId={participantId || undefined}
            myName={myName}
            phase={phase}
            sprintGoal={sprintGoal}
          />
        </div>

        {/* Right: Task state panel (~35%) */}
        <div className="w-[35%] min-w-0">
          <TaskPanel
            sessionId={session_id!}
            participants={participants}
            phase={phase}
            myParticipantId={participantId || undefined}
            myName={myName}
            sprintGoal={sprintGoal}
            onAcceptPlan={handleAcceptPlan}
            accepted={planAccepted}
          />
        </div>
      </div>
    </div>
  );
}
