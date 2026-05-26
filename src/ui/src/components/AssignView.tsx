/**
 * AssignView — v1: Accept/Decline card; v2: Algorithmic assignment proposal discussion
 *
 * For v2 (US-39 AC5-AC7): Shows assignment_proposal from comm bus,
 * round counter, volunteer/object/reassign discussion panel.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

// ── Types ────────────────────────────────────────────────────────────────────

interface BacklogItem {
  item_id: string;
  title: string;
  description?: string;
  story_points?: number | null;
  labels?: string[];
  priority?: string;
}

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: string;
}

interface Props {
  taskId: string;
  sessionCtx: {
    backlog_items?: BacklogItem[];
    participants?: Participant[];
    template_id?: string;
    template?: string;
  };
  payload: {
    item_id?: string;
    title?: string;
  };
  onSubmit: (taskId: string, artifact: Record<string, unknown>) => void;
  submitted: boolean;
  submittedArtifact?: Record<string, unknown>;
}

// ── V2-specific types ────────────────────────────────────────────────────────

interface AssignmentState {
  context: string;
  assignments: Record<string, string>;       // item_id → participant_id
  round: number;
}

// ── V1 View (unchanged, extracted for clarity) ──────────────────────────────

function V1AssignView({
  taskId,
  sessionCtx,
  payload,
  onSubmit,
  submitted,
  submittedArtifact,
}: Props) {
  const { backlog_items = [] } = sessionCtx;
  const targetId = payload.item_id;
  const item = backlog_items.find((i) => i.item_id === targetId) ?? {
    item_id: targetId ?? "?",
    title: payload.title ?? targetId ?? "Unknown item",
    description: "",
    story_points: null,
    labels: [],
  };
  const volunteered = submittedArtifact?.volunteer === true;
  const declined = submitted && !volunteered;

  return (
    <div className="space-y-4">
      <Card
        className={
          submitted ? (volunteered ? "ring-2 ring-primary/40" : "opacity-70") : ""
        }
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle className="text-base">Volunteer for this task?</CardTitle>
            {submitted && (
              <Badge variant={volunteered ? "default" : "secondary"}>
                {volunteered ? "Volunteered ✓" : "Declined"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <p className="font-medium">{item.title}</p>
            {item.description && (
              <p className="text-sm text-muted-foreground mt-1">{item.description}</p>
            )}
          </div>
          {(item.story_points != null || (item.labels ?? []).length > 0) && (
            <>
              <Separator />
              <div className="flex items-center gap-2 flex-wrap">
                {item.story_points != null && (
                  <Badge variant="outline" className="text-xs">
                    {item.story_points} story points
                  </Badge>
                )}
                {(item.labels ?? []).map((l) => (
                  <span
                    key={l}
                    className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded"
                  >
                    {l}
                  </span>
                ))}
              </div>
            </>
          )}
          {!submitted && (
            <>
              <Separator />
              <div className="flex gap-3">
                <Button
                  className="flex-1"
                  onClick={() => onSubmit(taskId, { volunteer: true })}
                >
                  Accept
                </Button>
                <Button
                  className="flex-1"
                  variant="outline"
                  onClick={() => onSubmit(taskId, { volunteer: false })}
                >
                  Decline
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── V2 View ──────────────────────────────────────────────────────────────────

function V2AssignView({
  sessionCtx,
  taskId,
  onSubmit,
  submitted,
}: Props) {
  const { backlog_items = [], participants = [] } = sessionCtx;
  const itemMap = Object.fromEntries(backlog_items.map((i) => [i.item_id, i]));
  const participantMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p])
  );
  const nameMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p.name])
  );

  // Derive session_id from taskId (format: ph_{session_id}_{phase_id} or similar)
  const sessionId =
    typeof taskId === "string"
      ? taskId.replace(/^ph_/, "").split("_").slice(0, -1).join("_")
      : "";

  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [round, setRound] = useState(0);
  const [connected, setConnected] = useState(false);
  const [allItems, setAllItems] = useState<string[]>([]);
  const sseRef = useRef<EventSource | null>(null);

  const myPid =
    sessionStorage.getItem(`pid:${sessionId}`) ?? "anonymous";

  // Subscribe to comm-feed for assignment updates
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

        // Handle assignment context discussion_update broadcasts
        if (
          data.task_type === "discussion_update" &&
          content.context === "assignment"
        ) {
          const state = data.content as AssignmentState;
          setAssignments(state.assignments || {});
          setRound(state.round ?? 0);
          setAllItems(Object.keys(state.assignments || {}));
        }
      } catch {
        // ignore
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [sessionId]);

  const sendAction = useCallback(
    async (action: string, content: Record<string, unknown>) => {
      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myPid,
            sender_name: participants.find((p) => p.participant_id === myPid)?.name ?? myPid,
            action,
            content,
          }),
        });
      } catch {
        // silently fail
      }
    },
    [sessionId, myPid, participants]
  );

  function handleVolunteer(itemId: string) {
    sendAction("volunteer", { item_id: itemId });
  }

  function handleObject(itemId: string) {
    sendAction("object", { item_id: itemId, reason: "Disagree with assignment" });
  }

  function handleReassign(itemId: string, toParticipantId: string) {
    const currentAssignee = assignments[itemId];
    sendAction("reassign", {
      item_id: itemId,
      to_participant_id: toParticipantId,
      from_participant_id: currentAssignee || "",
    });
  }

  const unassignedItems = allItems.filter((id) => !assignments[id]);
  const assignedItems = allItems.filter((id) => !!assignments[id]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              Algorithmic Assignment Proposal
            </CardTitle>
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  connected ? "bg-green-500" : "bg-muted animate-pulse"
                }`}
              />
              <Badge variant="outline" className="text-xs">
                Round {round}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            The platform proposes assignments based on expertise and capacity.
            Volunteer for unassigned items, object to assignments you disagree
            with, or suggest reassignments.
          </p>
        </CardContent>
      </Card>

      {/* Assignment Table */}
      {allItems.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-muted-foreground text-sm">
            Waiting for assignment proposal…
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {/* Assigned items */}
          {assignedItems.map((itemId) => {
            const item = itemMap[itemId];
            const assigneePid = assignments[itemId];
            const assigneeName = nameMap[assigneePid] ?? assigneePid ?? "Unknown";
            const isMe = assigneePid === myPid;

            return (
              <Card
                key={itemId}
                className={isMe ? "ring-2 ring-primary/30" : ""}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-sm font-medium">
                        {item?.title ?? itemId}
                      </CardTitle>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {itemId}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {item?.story_points != null && (
                        <Badge variant="outline" className="text-xs">
                          {item.story_points} SP
                        </Badge>
                      )}
                      <Badge
                        variant={isMe ? "default" : "secondary"}
                        className="text-xs"
                      >
                        → {assigneeName}{isMe ? " (You)" : ""}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <Separator />
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={() => handleObject(itemId)}
                    >
                      Object
                    </Button>
                    {/* Reassign dropdown */}
                    <select
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) {
                          handleReassign(itemId, e.target.value);
                          e.target.value = "";
                        }
                      }}
                      className="text-xs rounded border border-border bg-background px-1.5 py-0.5 text-foreground h-7"
                    >
                      <option value="">Reassign to…</option>
                      {participants
                        .filter(
                          (p) =>
                            p.participant_id &&
                            p.participant_id !== assigneePid
                        )
                        .map((p) => (
                          <option key={p.participant_id} value={p.participant_id!}>
                            {p.name} ({p.role})
                          </option>
                        ))}
                    </select>
                  </div>
                </CardContent>
              </Card>
            );
          })}

          {/* Unassigned items */}
          {unassignedItems.map((itemId) => {
            const item = itemMap[itemId];
            return (
              <Card key={itemId} className="border-dashed opacity-80">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-sm font-medium">
                        {item?.title ?? itemId}
                      </CardTitle>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {itemId}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {item?.story_points != null && (
                        <Badge variant="outline" className="text-xs">
                          {item.story_points} SP
                        </Badge>
                      )}
                      <Badge variant="outline" className="text-xs">
                        Unassigned
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <Separator />
                  <Button
                    size="sm"
                    variant="default"
                    className="h-7 text-xs"
                    onClick={() => handleVolunteer(itemId)}
                  >
                    Volunteer
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main component — detect v1 vs v2 ─────────────────────────────────────────

export default function AssignView(props: Props) {
  const isV2 = isV2Session(props);
  if (isV2) {
    return <V2AssignView {...props} />;
  }
  return <V1AssignView {...props} />;
}

function isV2Session(props: Props): boolean {
  // Check for template identifier in session context
  const tpl =
    props.sessionCtx.template_id ??
    props.sessionCtx.template ??
    "";
  return typeof tpl === "string" && tpl.includes("v2");
}
