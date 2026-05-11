/** assign_opportunity → Accept/Decline card (AC4, AC5) */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  description?: string;
  story_points?: number | null;
  labels?: string[];
}

interface Props {
  taskId: string;
  sessionCtx: {
    backlog_items?: BacklogItem[];
  };
  payload: {
    item_id?: string;
    title?: string;
  };
  onSubmit: (taskId: string, artifact: Record<string, unknown>) => void;
  submitted: boolean;
  submittedArtifact?: Record<string, unknown>;
}

export default function AssignView({
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
      <Card className={submitted ? (volunteered ? "ring-2 ring-primary/40" : "opacity-70") : ""}>
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
