/**
 * SessionPage — AC4, AC5, AC6, AC7
 *
 * Subscribes to the proxy's SSE stream for the human's participant_id.
 * Dispatches each incoming task to the appropriate component.
 * Submits human responses via POST /proxy/respond.
 * Closing the tab closes only the browser SSE — the platform SSE remains open
 * and its timeout handles the missed response (AC6, AC7).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import { ParticipantsSidebar } from "@/components/ParticipantsSidebar";
import { CommunicationFeed } from "@/components/CommunicationFeed";
import LobbyView from "@/components/LobbyView";
import ReadyView from "@/components/ReadyView";
import BacklogView from "@/components/BacklogView";
import VoteView from "@/components/VoteView";
import AssignView from "@/components/AssignView";
import ConfirmView from "@/components/ConfirmView";
import SprintBacklogView from "@/components/SprintBacklogView";
import RecommendationView from "@/components/RecommendationView";

interface TaskEnvelope {
  task_id: string;
  task_type: string;
  session_ctx: Record<string, unknown>;
  payload: Record<string, unknown>;
}

interface ActiveTask {
  envelope: TaskEnvelope;
  submitted: boolean;
  submittedArtifact?: Record<string, unknown>;
}

export default function SessionPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const navigate = useNavigate();
  const participantId = sessionStorage.getItem(`pid:${session_id}`) ?? "anonymous";

  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [participants, setParticipants] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  // Track template version from session context
  const [templateVersion, setTemplateVersion] = useState<string>("v1");

  useEffect(() => {
    if (!session_id) return;

    // Open SSE stream to proxy (AC7: stays open while tab is active)
    const url = `/proxy/tasks?participant_id=${encodeURIComponent(participantId)}`;
    const es = new EventSource(url);
    sseRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setConnectionError(false);
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Control messages from proxy
        if (data.type === "connected") {
          setConnected(true);
          return;
        }
        if (data.type === "heartbeat") {
          return;
        }

        // A2A task envelope
        const envelope = data as TaskEnvelope;
        if (!envelope.task_id || !envelope.task_type) return;

        // Handle informational tasks that don't require interaction
        if (envelope.task_type === "acknowledge_assignment") {
          const payload = envelope.payload as {
            assignee_name?: string;
            item_id?: string;
            reason?: string;
          };
          toast.info(
            `Assignment: ${payload.item_id ?? "item"} → ${payload.assignee_name ?? "someone"}`,
            { description: payload.reason }
          );
          return;
        }

        // Navigate to summary screen when session completes
        if (envelope.task_type === "sprint_backlog" && session_id) {
          setTimeout(() => navigate(`/sessions/${session_id}/summary`), 4000);
        }

        // Add interactive or display tasks to the stack
        setTasks((prev) => {
          // Don't add duplicate task_ids
          if (prev.some((t) => t.envelope.task_id === envelope.task_id)) return prev;
          return [...prev, { envelope, submitted: false }];
        });

        if (envelope.session_ctx?.participants) {
          setParticipants(envelope.session_ctx.participants as any[]);
        }

        // Detect v2 template from session context
        const tpl =
          envelope.session_ctx?.template_id ??
          envelope.session_ctx?.template;
        if (typeof tpl === "string" && tpl.includes("v2")) {
          setTemplateVersion("v2");
        }
      } catch {
        // Ignore malformed frames
      }
    };

    es.onerror = () => {
      setConnectionError(true);
      // EventSource auto-reconnects; we just flag the error state
    };

    return () => {
      es.close();
    };
  }, [session_id, participantId]);

  async function handleSubmit(taskId: string, artifact: Record<string, unknown>) {
    // Optimistically mark as submitted
    setTasks((prev) =>
      prev.map((t) =>
        t.envelope.task_id === taskId
          ? { ...t, submitted: true, submittedArtifact: artifact }
          : t
      )
    );

    try {
      const resp = await fetch("/proxy/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, artifact }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        toast.error("Failed to submit response", {
          description: err.error ?? "Unknown error",
        });
        // Revert optimistic update
        setTasks((prev) =>
          prev.map((t) =>
            t.envelope.task_id === taskId
              ? { ...t, submitted: false, submittedArtifact: undefined }
              : t
          )
        );
      } else {
        toast.success("Response submitted");
      }
    } catch {
      toast.error("Network error submitting response");
    }
  }

  const isV2 = templateVersion === "v2";

  // Render the appropriate component per task type (AC4)
  function renderTask(active: ActiveTask) {
    const { envelope, submitted, submittedArtifact } = active;
    const { task_id, task_type, session_ctx, payload } = envelope;

    const ctx = session_ctx as any;
    const pl = payload as any;

    switch (task_type) {
      case "session_invite":
        return <LobbyView sessionCtx={ctx} />;
      case "session_ready":
        return <ReadyView sessionCtx={ctx} />;
      case "present_backlog":
        // v2: route to RecommendationView for discussion-driven recommendation
        if (isV2 && session_id) {
          return (
            <RecommendationView
              sessionId={session_id}
              sessionCtx={ctx}
              myParticipantId={participantId}
              myName={
                sessionStorage.getItem(`name:${session_id}`) ?? undefined
              }
            />
          );
        }
        return <BacklogView sessionCtx={ctx} />;
      case "vote":
        // v2: replaced by RecommendationView — if a vote task arrives in v2, show recommendation
        if (isV2 && session_id) {
          return (
            <RecommendationView
              sessionId={session_id}
              sessionCtx={ctx}
              myParticipantId={participantId}
              myName={
                sessionStorage.getItem(`name:${session_id}`) ?? undefined
              }
            />
          );
        }
        return (
          <VoteView
            taskId={task_id}
            sessionCtx={ctx}
            payload={pl}
            onSubmit={handleSubmit}
            submitted={submitted}
          />
        );
      case "assign_opportunity":
        return (
          <AssignView
            taskId={task_id}
            sessionCtx={ctx}
            payload={pl}
            onSubmit={handleSubmit}
            submitted={submitted}
            submittedArtifact={submittedArtifact}
          />
        );
      case "confirm":
        return (
          <ConfirmView
            taskId={task_id}
            sessionCtx={ctx}
            payload={pl}
            onSubmit={handleSubmit}
            submitted={submitted}
            submittedArtifact={submittedArtifact}
          />
        );
      case "sprint_backlog":
        return <SprintBacklogView payload={pl} myParticipantId={participantId} />;
      case "phase_started": {
        // US-36: Route to appropriate view based on phase
        const phase = (payload as any)?.phase as string | undefined;
        if (phase === "recommendation") {
          if (isV2 && session_id) {
            return (
              <RecommendationView
                sessionId={session_id}
                sessionCtx={ctx}
                myParticipantId={participantId}
                myName={
                  sessionStorage.getItem(`name:${session_id}`) ?? undefined
                }
              />
            );
          }
          return <BacklogView sessionCtx={ctx} />;
        }
        if (phase === "assignment") {
          return (
            <AssignView
              taskId={task_id}
              sessionCtx={ctx}
              payload={pl}
              onSubmit={handleSubmit}
              submitted={submitted}
              submittedArtifact={submittedArtifact}
            />
          );
        }
        if (phase === "confirmation") {
          return (
            <ConfirmView
              taskId={task_id}
              sessionCtx={ctx}
              payload={pl}
              onSubmit={handleSubmit}
              submitted={submitted}
              submittedArtifact={submittedArtifact}
            />
          );
        }
        return (
          <div className="text-sm text-muted-foreground">
            Phase: <code>{phase ?? "unknown"}</code>
          </div>
        );
      }
      default:
        return (
          <div className="text-sm text-muted-foreground">
            Received task: <code>{task_type}</code>
          </div>
        );
    }
  }

  const phaseLabel: Record<string, string> = {
    session_invite: "Lobby",
    session_ready: "Session Starting",
    present_backlog: isV2 ? "Goal-Aligned Recommendation" : "Backlog Presentation",
    vote: isV2 ? "Discuss & Refine" : "Prioritisation",
    assign_opportunity: isV2 ? "Assignment Discussion" : "Assignment",
    confirm: isV2 ? "PO Confirmation" : "Confirmation",
    sprint_backlog: "Sprint Backlog",
    phase_started: "Phase Update",
  };

  return (
    <div className="flex max-w-6xl mx-auto items-start gap-8 p-8">
      <main className="flex-1 space-y-6">
        {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Sprint Session</h1>
          <p className="text-xs text-muted-foreground mt-0.5 font-mono">
            {session_id} · You: {participantId.slice(0, 8)}…
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connectionError
                ? "bg-destructive"
                : connected
                ? "bg-green-500"
                : "bg-muted animate-pulse"
            }`}
          />
          <span className="text-muted-foreground">
            {connectionError ? "Reconnecting…" : connected ? "Connected" : "Connecting…"}
          </span>
        </div>
      </div>

      {/* Task stack — newest first */}
      {tasks.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center py-16 text-muted-foreground"
        >
          <p>Waiting for the session to begin…</p>
          <p className="text-xs mt-2">Keep this tab open to receive tasks.</p>
        </motion.div>
      ) : (
        <div className="space-y-8">
          <AnimatePresence>
            {[...tasks].reverse().map((active, idx) => (
              <motion.section
                key={active.envelope.task_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              >
                {idx === 0 && (
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                    {phaseLabel[active.envelope.task_type] ?? active.envelope.task_type}
                  </h2>
                )}
                {idx > 0 && (
                  <h3 className="text-xs text-muted-foreground mb-3 opacity-60">
                    ↑ Earlier: {phaseLabel[active.envelope.task_type] ?? active.envelope.task_type}
                  </h3>
                )}
                <div className={idx > 0 ? "opacity-50 pointer-events-none" : ""}>
                  {renderTask(active)}
                </div>
              </motion.section>
            ))}
          </AnimatePresence>
        </div>
      )}
      </main>
      
      <div className="w-72 shrink-0 flex flex-col gap-0">
        {participants.length > 0 && (
          <ParticipantsSidebar
            participants={participants}
            currentTaskType={tasks.length > 0 ? tasks[tasks.length - 1].envelope.task_type : undefined}
            myParticipantId={participantId}
          />
        )}
        {session_id && (
          <CommunicationFeed
            sessionId={session_id}
            participants={participants}
            myParticipantId={participantId !== "anonymous" ? participantId : undefined}
            myName={sessionStorage.getItem(`name:${session_id}`) ?? undefined}
            currentTaskType={tasks.length > 0 ? tasks[tasks.length - 1].envelope.task_type : undefined}
          />
        )}
      </div>
    </div>
  );
}
