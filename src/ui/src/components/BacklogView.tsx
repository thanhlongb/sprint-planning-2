/** present_backlog → Read-only backlog list (PO only) (AC4) */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  description: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  story_points: number | null;
  labels: string[];
  dependencies: string[];
}

interface Props {
  sessionCtx: {
    backlog_items?: BacklogItem[];
    sprint_goal?: string;
  };
}

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

export default function BacklogView({ sessionCtx }: Props) {
  const { backlog_items = [], sprint_goal } = sessionCtx;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backlog Presentation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            The Product Owner is presenting the candidate backlog. Review the items below.
          </p>
          {sprint_goal && (
            <p className="mt-2 text-sm">
              <span className="font-medium">Sprint Goal:</span> {sprint_goal}
            </p>
          )}
        </CardContent>
      </Card>

      {backlog_items.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-muted-foreground text-sm">
            Waiting for backlog items…
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {backlog_items.map((item) => (
            <Card key={item.item_id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="text-sm font-medium">{item.title}</CardTitle>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Badge variant={priorityVariant[item.priority]} className="text-xs">
                      {item.priority}
                    </Badge>
                    {item.story_points != null && (
                      <Badge variant="outline" className="text-xs">
                        {item.story_points} SP
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                <p className="text-xs text-muted-foreground">{item.description}</p>
                {item.labels.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {item.labels.map((l) => (
                      <span
                        key={l}
                        className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded"
                      >
                        {l}
                      </span>
                    ))}
                  </div>
                )}
                {item.dependencies.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Depends on: {item.dependencies.join(", ")}
                  </p>
                )}
                <Separator />
                <p className="text-xs text-muted-foreground font-mono">{item.item_id}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
