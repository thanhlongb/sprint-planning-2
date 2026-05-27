/**
 * TaskPanel — the task state panel (right panel) for v2 chat-centric sessions.
 *
 * Phase 1 (recommendation): shows recommendation list with scores, inline edit/remove, stats
 * Phase 2 (assignment): shows assignment map table, volunteer/object buttons
 * Phase 3 (confirmation): shows final sprint backlog (read-only), convergence metrics, [Accept Plan] for PO
 * Updates in real-time from comm bus events.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { Phase, Participant } from "@/components/ChatPanel";

// ── Types ────────────────────────────────────────────────────────────────────

interface BacklogItem {
  item_id: string;
  title: string;
  description?: string;
  priority?: "HIGH" | "MEDIUM" | "LOW";
  story_points?: number | null;
  labels?: string[];
  dependencies?: string[];
  score?: number;
}

interface RecommendationState {
  context: string;
  items: BacklogItem[];
  round: number;
}

interface AssignmentState {
  context: string;
  assignments: Record<string, string>; // item_id → participant_id
  round: number;
}

interface ConvergenceMetrics {
  recommendation_rounds?: number;
  assignment_rounds?: number;
  retention_pct?: number;
}

interface Props {
  sessionId: string;
  participants: Participant[];
  phase: Phase;
  myParticipantId?: string;
  myName?: string;
  sprintGoal?: string;
  onAcceptPlan?: () => void;
  accepted?: boolean;
}

// ── Priority config ─────────────────────────────────────────────────────────

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

// ── Component ────────────────────────────────────────────────────────────────

export function TaskPanel({
  sessionId,
  participants,
  phase,
  myParticipantId,
  myName,
  sprintGoal,
  onAcceptPlan,
  accepted,
}: Props) {
  // Phase 1 state
  const [items, setItems] = useState<BacklogItem[]>([]);
  const [round, setRound] = useState(0);
  const [connected, setConnected] = useState(false);

  // Phase 2 state
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [assignmentRound, setAssignmentRound] = useState(0);

  // Phase 3 state
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [convergenceMetrics, setConvergenceMetrics] =
    useState<ConvergenceMetrics | null>(null);
  const [finalAssignments, setFinalAssignments] = useState<
    Record<string, string>
  >({});

  const sseRef = useRef<EventSource | null>(null);

  // ── SSE subscription for real-time updates ────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    const es = new EventSource(
      `/proxy/comm-feed?session_id=${encodeURIComponent(sessionId)}`
    );
    sseRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") {
          setConnected(true);
          return;
        }
        if (data.event_type !== "comm_event") return;

        const content = data.content;
        if (!content || typeof content !== "object") return;

        // Recommendation update
        if (
          data.task_type === "discussion_update" &&
          content.context === "recommendation"
        ) {
          const state = data.content as RecommendationState;
          const mapped: BacklogItem[] = (state.items || []).map((it: any) => ({
            item_id: it.item_id || "",
            title: it.title || "",
            description: it.description || "",
            priority: it.priority || "MEDIUM",
            story_points: it.story_points ?? null,
            labels: it.labels || [],
            dependencies: it.dependencies || [],
            score: it.score ?? it._score,
          }));
          setItems(mapped);
          setRound(state.round ?? 0);
        }

        // Assignment update
        if (
          data.task_type === "discussion_update" &&
          content.context === "assignment"
        ) {
          const state = data.content as AssignmentState;
          setAssignments(state.assignments || {});
          setAssignmentRound(state.round ?? 0);
          // Also update items from assignment context if present
          if ((state as any).items) {
            const mapped: BacklogItem[] = ((state as any).items || []).map(
              (it: any) => ({
                item_id: it.item_id || "",
                title: it.title || "",
                description: it.description || "",
                priority: it.priority || "MEDIUM",
                story_points: it.story_points ?? null,
                labels: it.labels || [],
                dependencies: it.dependencies || [],
                score: it.score ?? it._score,
              })
            );
            setItems(mapped);
          }
        }

        // Confirmation / sprint backlog
        if (data.task_type === "confirm" || data.task_type === "sprint_backlog") {
          const c = content as Record<string, unknown>;
          if (c.selected_items) {
            setSelectedItems(c.selected_items as string[]);
          }
          if (c.assignments) {
            setFinalAssignments(c.assignments as Record<string, string>);
          }
          if (c.convergence_metrics) {
            setConvergenceMetrics(c.convergence_metrics as ConvergenceMetrics);
          }
        }
      } catch {
        // ignore
      }
    };

    es.onerror = () => setConnected(false);
    return () => es.close();
  }, [sessionId]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const sendAction = useCallback(
    async (action: string, content: Record<string, unknown>) => {
      if (!myParticipantId || !myName) return;
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

  function handleRemoveItem(itemId: string) {
    sendAction("remove_item", { item_id: itemId });
  }

  function handleModifySP(itemId: string, sp: number) {
    sendAction("modify_item", {
      item_id: itemId,
      updates: { story_points: sp },
    });
  }

  function handleModifyPriority(itemId: string, priority: string) {
    sendAction("modify_item", {
      item_id: itemId,
      updates: { priority },
    });
  }

  function handleAddItem() {
    const itemId = `human-${Date.now()}`;
    sendAction("add_item", {
      item: {
        item_id: itemId,
        title: "New task from panel",
        description: "",
        priority: "MEDIUM",
        story_points: 3,
        labels: [],
        dependencies: [],
      },
    });
  }

  function handleVolunteer(itemId: string) {
    sendAction("volunteer", { item_id: itemId });
  }

  function handleObject(itemId: string) {
    sendAction("object", {
      item_id: itemId,
      reason: "Disagree with assignment",
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const itemMap = Object.fromEntries(items.map((i) => [i.item_id, i]));
  const participantMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p.name])
  );
  const nameMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p.name])
  );

  const totalSP = items.reduce((acc, i) => acc + (i.story_points ?? 0), 0);
  const capacityTotal = 90; // default capacity
  const capacityUsed = totalSP;

  const isPO =
    participants.find((p) => p.participant_id === myParticipantId)?.role ===
    "PRODUCT_OWNER";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-card/30">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border bg-card/50 shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            {phase === "recommendation" || phase === "lobby"
              ? `Tasks (${items.length})`
              : phase === "assignment"
              ? "Assignments"
              : "Sprint Backlog"}
          </h2>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-green-500" : "bg-muted animate-pulse"
              }`}
            />
            {phase === "recommendation" && round > 0 && (
              <Badge variant="outline" className="text-xs">
                Round {round}
              </Badge>
            )}
            {phase === "assignment" && assignmentRound > 0 && (
              <Badge variant="outline" className="text-xs">
                Round {assignmentRound}
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Content area — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {/* ── Phase 1: Recommendation ─────────────────────────────────────── */}
        {(phase === "recommendation" || phase === "lobby") && (
          <>
            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="bg-muted/30 rounded-lg p-2">
                <p className="text-sm font-bold">{items.length}</p>
                <p className="text-[10px] text-muted-foreground">Items</p>
              </div>
              <div className="bg-muted/30 rounded-lg p-2">
                <p className="text-sm font-bold">
                  {capacityUsed}/{capacityTotal} SP
                </p>
                <p className="text-[10px] text-muted-foreground">Capacity</p>
              </div>
            </div>

            {/* Item list */}
            {items.length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center text-muted-foreground text-sm">
                  Waiting for recommendations…
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {items.map((item) => (
                  <Card key={item.item_id} className="overflow-hidden">
                    <CardHeader className="pb-1 px-3 pt-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">
                            {item.title}
                          </p>
                          <p className="text-[10px] text-muted-foreground font-mono">
                            {item.item_id}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {item.score != null && (
                            <Badge variant="secondary" className="text-[10px] h-4 px-1">
                              {typeof item.score === "number"
                                ? item.score.toFixed(1)
                                : item.score}
                            </Badge>
                          )}
                          {item.priority && (
                            <Badge
                              variant={priorityVariant[item.priority] || "outline"}
                              className="text-[10px] h-4 px-1"
                            >
                              {item.priority === "HIGH"
                                ? "Hi"
                                : item.priority === "MEDIUM"
                                ? "Med"
                                : "Lo"}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="pb-1 px-3 space-y-1.5">
                      {/* SP inline edit */}
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground">SP:</span>
                        <input
                          type="number"
                          min={0}
                          defaultValue={item.story_points ?? ""}
                          onBlur={(e) => {
                            const val = Number(e.target.value);
                            if (!isNaN(val) && val >= 0) {
                              handleModifySP(item.item_id, val);
                            }
                          }}
                          className="w-14 text-[10px] rounded border border-border bg-background px-1 py-0.5"
                        />
                        <span className="text-[10px] text-muted-foreground">Pr:</span>
                        <select
                          defaultValue={item.priority ?? "MEDIUM"}
                          onChange={(e) =>
                            handleModifyPriority(item.item_id, e.target.value)
                          }
                          className="text-[10px] rounded border border-border bg-background px-1 py-0.5"
                        >
                          <option value="HIGH">HIGH</option>
                          <option value="MEDIUM">MEDIUM</option>
                          <option value="LOW">LOW</option>
                        </select>
                        <button
                          onClick={() => handleRemoveItem(item.item_id)}
                          className="text-[10px] text-destructive hover:underline ml-auto"
                          title="Remove item"
                        >
                          ✕
                        </button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* Add button */}
            <Button
              size="sm"
              variant="outline"
              className="w-full text-xs h-8"
              onClick={handleAddItem}
            >
              + Add Task
            </Button>
          </>
        )}

        {/* ── Phase 2: Assignment ─────────────────────────────────────────── */}
        {phase === "assignment" && (
          <>
            {Object.keys(assignments).length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center text-muted-foreground text-sm">
                  Waiting for assignment proposals…
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {Object.entries(assignments).map(([itemId, assigneeId]) => {
                  const item = itemMap[itemId];
                  const assigneeName =
                    nameMap[assigneeId] ?? assigneeId ?? "Unknown";
                  const isMe = assigneeId === myParticipantId;

                  return (
                    <Card
                      key={itemId}
                      className={`overflow-hidden ${
                        isMe ? "ring-1 ring-primary/30" : ""
                      }`}
                    >
                      <CardHeader className="pb-1 px-3 pt-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-medium truncate">
                              {item?.title ?? itemId}
                            </p>
                            <p className="text-[10px] text-muted-foreground font-mono">
                              {itemId}
                            </p>
                          </div>
                          <Badge
                            variant={isMe ? "default" : "secondary"}
                            className="text-[10px] h-4 px-1 flex-shrink-0"
                          >
                            → {assigneeName}
                            {isMe ? " (You)" : ""}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="pb-1 px-3">
                        <div className="flex gap-1.5">
                          {item?.story_points != null && (
                            <Badge
                              variant="outline"
                              className="text-[10px] h-4 px-1"
                            >
                              {item.story_points} SP
                            </Badge>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 text-[10px] px-1.5"
                            onClick={() => handleVolunteer(itemId)}
                          >
                            Volunteer
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 text-[10px] px-1.5"
                            onClick={() => handleObject(itemId)}
                          >
                            Object
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ── Phase 3: Confirmation ───────────────────────────────────────── */}
        {phase === "confirmation" && (
          <>
            {/* Sprint backlog table */}
            {selectedItems.length === 0 ? (
              <Card>
                <CardContent className="pt-6 text-center text-muted-foreground text-sm">
                  Waiting for final sprint backlog…
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {selectedItems.map((itemId) => {
                  const item = itemMap[itemId];
                  const assigneeName =
                    participantMap[finalAssignments[itemId] ?? ""] ??
                    finalAssignments[itemId] ??
                    "Unassigned";
                  return (
                    <Card key={itemId}>
                      <CardHeader className="pb-1 px-3 pt-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-medium truncate">
                              {item?.title ?? itemId}
                            </p>
                            <p className="text-[10px] text-muted-foreground font-mono">
                              {itemId}
                            </p>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {item?.story_points != null && (
                              <Badge
                                variant="outline"
                                className="text-[10px] h-4 px-1"
                              >
                                {item.story_points} SP
                              </Badge>
                            )}
                            <Badge
                              variant="secondary"
                              className="text-[10px] h-4 px-1"
                            >
                              {assigneeName}
                            </Badge>
                          </div>
                        </div>
                      </CardHeader>
                    </Card>
                  );
                })}
              </div>
            )}

            {/* Convergence metrics */}
            {convergenceMetrics && (
              <Card>
                <CardHeader className="pb-1 px-3 pt-3">
                  <p className="text-xs font-semibold text-muted-foreground">
                    Convergence
                  </p>
                </CardHeader>
                <CardContent className="px-3 pb-3">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-lg font-bold">
                        {convergenceMetrics.recommendation_rounds ?? "—"}
                      </p>
                      <p className="text-[9px] text-muted-foreground">
                        Rec. Rounds
                      </p>
                    </div>
                    <div>
                      <p className="text-lg font-bold">
                        {convergenceMetrics.assignment_rounds ?? "—"}
                      </p>
                      <p className="text-[9px] text-muted-foreground">
                        Assign. Rounds
                      </p>
                    </div>
                    <div>
                      <p className="text-lg font-bold">
                        {convergenceMetrics.retention_pct != null
                          ? `${convergenceMetrics.retention_pct}%`
                          : "—"}
                      </p>
                      <p className="text-[9px] text-muted-foreground">
                        Retention
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Accept Plan button for PO */}
            {!accepted && (
              isPO ? (
                <Button
                  className="w-full"
                  size="sm"
                  onClick={onAcceptPlan}
                  disabled={selectedItems.length === 0}
                >
                  Accept Plan
                </Button>
              ) : (
                <Card>
                  <CardContent className="py-3 text-center text-muted-foreground text-xs">
                    Waiting for PO to accept the sprint plan…
                  </CardContent>
                </Card>
              )
            )}
            {accepted && (
              <p className="text-xs text-center text-muted-foreground">
                ✓ Plan accepted. Redirecting…
              </p>
            )}
          </>
        )}
      </div>

      {/* Participants footer */}
      <div className="px-4 py-3 border-t border-border bg-card/50 shrink-0">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
          Participants
        </p>
        <div className="space-y-1">
          {participants.map((p, i) => (
            <div key={p.participant_id || i} className="flex items-center gap-2">
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white shrink-0 ${
                  p.type === "AI_AGENT"
                    ? "bg-violet-500"
                    : p.role === "PRODUCT_OWNER"
                    ? "bg-indigo-500"
                    : p.role === "DEVELOPER"
                    ? "bg-emerald-500"
                    : "bg-amber-500"
                }`}
              >
                {p.name.charAt(0).toUpperCase()}
              </div>
              <span className="text-xs truncate">
                {p.name}
                {p.participant_id === myParticipantId ? " (You)" : ""}
              </span>
              {p.type === "AI_AGENT" && (
                <Badge variant="outline" className="text-[9px] h-3.5 px-1">
                  AI
                </Badge>
              )}
            </div>
          ))}
          {participants.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No participants connected
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
