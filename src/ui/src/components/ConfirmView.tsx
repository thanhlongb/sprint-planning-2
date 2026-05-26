/**
 * ConfirmView — v1: Sprint summary with Confirm/Reject + quorum bar;
 *               v2: PO Confirmation with convergence metrics, single Accept button.
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  story_points?: number | null;
  priority?: string;
}

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
}

interface SummaryPayload {
  sprint_goal?: string;
  selected_items?: string[];
  assignments?: Record<string, string>;
  convergence_metrics?: {
    recommendation_rounds?: number;
    assignment_rounds?: number;
    retention_pct?: number;
  };
}

interface Props {
  taskId: string;
  sessionCtx: {
    sprint_goal?: string;
    backlog_items?: BacklogItem[];
    selected_items?: string[];
    assignments?: Record<string, string>;
    participants?: Participant[];
    template_id?: string;
    template?: string;
  };
  payload: SummaryPayload;
  onSubmit: (taskId: string, artifact: Record<string, unknown>) => void;
  submitted: boolean;
  submittedArtifact?: Record<string, unknown>;
}

// ── V1 View ──────────────────────────────────────────────────────────────────

function V1ConfirmView({
  taskId,
  sessionCtx,
  payload,
  onSubmit,
  submitted,
  submittedArtifact,
}: Props) {
  const sprint_goal = payload.sprint_goal ?? sessionCtx.sprint_goal ?? "—";
  const selectedItems =
    payload.selected_items ?? sessionCtx.selected_items ?? [];
  const assignments: Record<string, string> =
    payload.assignments ?? sessionCtx.assignments ?? {};
  const backlogItems = sessionCtx.backlog_items ?? [];
  const participants = sessionCtx.participants ?? [];

  const itemMap = Object.fromEntries(backlogItems.map((i) => [i.item_id, i]));
  const participantMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p.name])
  );

  const totalSP = selectedItems.reduce((acc, id) => {
    const item = itemMap[id];
    return acc + (item?.story_points ?? 0);
  }, 0);

  const confirmed = submittedArtifact?.confirmed === true;
  const rejected = submitted && !confirmed;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle className="text-base">Confirm Sprint Plan</CardTitle>
            {submitted && (
              <Badge variant={confirmed ? "default" : "destructive"}>
                {confirmed ? "Confirmed ✓" : "Rejected"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="font-medium text-lg">{sprint_goal}</p>
          <p className="text-xs text-muted-foreground">
            {selectedItems.length} items · {totalSP} story points total
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sprint Backlog</CardTitle>
        </CardHeader>
        <CardContent>
          {selectedItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">No items selected.</p>
          ) : (
            <ul className="space-y-3">
              {selectedItems.map((id) => {
                const item = itemMap[id];
                const assigneeName =
                  participantMap[assignments[id] ?? ""] ?? "Unassigned";
                return (
                  <li key={id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">
                          {item?.title ?? id}
                        </p>
                        {item?.priority && (
                          <span className="text-xs text-muted-foreground">
                            {item.priority}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {item?.story_points != null && (
                          <Badge variant="outline" className="text-xs">
                            {item.story_points} SP
                          </Badge>
                        )}
                        <Badge variant="secondary" className="text-xs">
                          {assigneeName}
                        </Badge>
                      </div>
                    </div>
                    <Separator className="mt-3" />
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {!submitted ? (
        <div className="flex gap-3">
          <Button
            className="flex-1"
            onClick={() => onSubmit(taskId, { confirmed: true })}
          >
            Confirm Sprint Plan
          </Button>
          <Button
            className="flex-1"
            variant="outline"
            onClick={() => onSubmit(taskId, { confirmed: false })}
          >
            Reject
          </Button>
        </div>
      ) : (
        <p className="text-sm text-center text-muted-foreground">
          {confirmed
            ? "You confirmed the sprint plan."
            : "You rejected the sprint plan."}
        </p>
      )}
    </div>
  );
}

// ── V2 View ──────────────────────────────────────────────────────────────────

function V2ConfirmView({
  taskId,
  sessionCtx,
  payload,
  onSubmit,
  submitted,
  submittedArtifact,
}: Props) {
  const sprint_goal = payload.sprint_goal ?? sessionCtx.sprint_goal ?? "—";
  const selectedItems =
    payload.selected_items ?? sessionCtx.selected_items ?? [];
  const assignments: Record<string, string> =
    payload.assignments ?? sessionCtx.assignments ?? {};
  const backlogItems = sessionCtx.backlog_items ?? [];
  const participants = sessionCtx.participants ?? [];
  const metrics = payload.convergence_metrics;

  const itemMap = Object.fromEntries(backlogItems.map((i) => [i.item_id, i]));
  const participantMap = Object.fromEntries(
    participants.map((p) => [p.participant_id ?? "", p.name])
  );

  const totalSP = selectedItems.reduce((acc, id) => {
    const item = itemMap[id];
    return acc + (item?.story_points ?? 0);
  }, 0);

  // Determine if current participant is PO
  const myPid =
    sessionStorage.getItem(`pid:${taskId.replace(/^conf_/, "").replace(/_.*/, "")}`) ??
    "anonymous";
  const myRole =
    participants.find((p) => p.participant_id === myPid)?.role ?? "";
  const isPO = myRole === "PRODUCT_OWNER";

  const confirmed = submittedArtifact?.confirmed === true;

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle className="text-base">PO Confirmation</CardTitle>
            {submitted && (
              <Badge variant={confirmed ? "default" : "destructive"}>
                {confirmed ? "Accepted ✓" : "Rejected"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="font-medium text-lg">{sprint_goal}</p>
          <p className="text-xs text-muted-foreground">
            {selectedItems.length} items · {totalSP} story points total
          </p>
        </CardContent>
      </Card>

      {/* Sprint Backlog with Assignments */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sprint Backlog</CardTitle>
        </CardHeader>
        <CardContent>
          {selectedItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">No items selected.</p>
          ) : (
            <ul className="space-y-3">
              {selectedItems.map((id) => {
                const item = itemMap[id];
                const assigneeName =
                  participantMap[assignments[id] ?? ""] ?? "Unassigned";
                return (
                  <li key={id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">
                          {item?.title ?? id}
                        </p>
                        {item?.priority && (
                          <span className="text-xs text-muted-foreground">
                            {item.priority}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {item?.story_points != null && (
                          <Badge variant="outline" className="text-xs">
                            {item.story_points} SP
                          </Badge>
                        )}
                        <Badge variant="secondary" className="text-xs">
                          {assigneeName}
                        </Badge>
                      </div>
                    </div>
                    <Separator className="mt-3" />
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Convergence Metrics */}
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Convergence Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold">
                  {metrics.recommendation_rounds ?? "—"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Recommendation Rounds
                </p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {metrics.assignment_rounds ?? "—"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Assignment Rounds
                </p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {metrics.retention_pct != null
                    ? `${metrics.retention_pct}%`
                    : "—"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Retention
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Action */}
      {!submitted ? (
        isPO ? (
          <Button
            className="w-full"
            onClick={() => onSubmit(taskId, { confirmed: true })}
          >
            Accept Plan
          </Button>
        ) : (
          <Card>
            <CardContent className="pt-6 text-center text-muted-foreground text-sm">
              Waiting for PO to accept the sprint plan…
            </CardContent>
          </Card>
        )
      ) : (
        <p className="text-sm text-center text-muted-foreground">
          {confirmed
            ? "Plan accepted."
            : "Plan rejected."}
        </p>
      )}
    </div>
  );
}

// ── Main component — detect v1 vs v2 ─────────────────────────────────────────

export default function ConfirmView(props: Props) {
  const isV2 = isV2Session(props);
  if (isV2) {
    return <V2ConfirmView {...props} />;
  }
  return <V1ConfirmView {...props} />;
}

function isV2Session(props: Props): boolean {
  const tpl =
    props.sessionCtx.template_id ??
    props.sessionCtx.template ??
    "";
  return typeof tpl === "string" && tpl.includes("v2");
}
