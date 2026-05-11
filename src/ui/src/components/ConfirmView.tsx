/**
 * ConfirmView — Sprint summary with Confirm/Reject (AC4, AC5)
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

interface Props {
  taskId: string;
  sessionCtx: {
    sprint_goal?: string;
    backlog_items?: BacklogItem[];
    selected_items?: string[];
    assignments?: Record<string, string>;
    participants?: Array<{ participant_id: string | null; name: string; role: string }>;
  };
  payload: {
    sprint_goal?: string;
    selected_items?: string[];
    assignments?: Record<string, string>;
  };
  onSubmit: (taskId: string, artifact: Record<string, unknown>) => void;
  submitted: boolean;
  submittedArtifact?: Record<string, unknown>;
}

export default function ConfirmView({
  taskId,
  sessionCtx,
  payload,
  onSubmit,
  submitted,
  submittedArtifact,
}: Props) {
  const sprint_goal =
    payload.sprint_goal ?? sessionCtx.sprint_goal ?? "—";

  const selectedItems =
    payload.selected_items ??
    sessionCtx.selected_items ??
    [];

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

      {/* Selected items */}
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
                const assigneeName = participantMap[assignments[id] ?? ""] ?? "Unassigned";
                return (
                  <li key={id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium">{item?.title ?? id}</p>
                        {item?.priority && (
                          <span className="text-xs text-muted-foreground">{item.priority}</span>
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
          {confirmed ? "You confirmed the sprint plan." : "You rejected the sprint plan."}
        </p>
      )}
    </div>
  );
}
