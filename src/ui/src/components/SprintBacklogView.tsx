import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  description: string;
  priority: string;
  story_points?: number | null;
  labels: string[];
  dependencies: string[];
  assignee_id?: string | null;
  assignee_name?: string | null;
}

interface CapacityPlanItem {
  assignee_id: string;
  assignee_name: string;
  item_count: number;
  total_story_points: number;
}

interface Props {
  payload: {
    session_id?: string;
    sprint_goal?: string;
    selected_items?: BacklogItem[];
    capacity_plan?: CapacityPlanItem[];
    convergence_metrics?: {
      recommendation_rounds?: number;
      assignment_rounds?: number;
      retention_pct?: number;
    };
  };
  myParticipantId?: string;
}

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

export default function SprintBacklogView({ payload, myParticipantId }: Props) {
  const { sprint_goal, selected_items = [], capacity_plan = [], convergence_metrics } = payload;

  const totalSP = capacity_plan.reduce((acc, curr) => acc + (curr.total_story_points || 0), 0);

  // Group items by assignee
  const groupedItems = selected_items.reduce((acc, item) => {
    const aid = item.assignee_id || "unassigned";
    if (!acc[aid]) acc[aid] = [];
    acc[aid].push(item);
    return acc;
  }, {} as Record<string, BacklogItem[]>);

  // Sort assignees: current user first, then others
  const sortedAssignees = [...capacity_plan].sort((a, b) => {
    if (a.assignee_id === myParticipantId) return -1;
    if (b.assignee_id === myParticipantId) return 1;
    return 0;
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base text-green-600 dark:text-green-400">
            Sprint Planning Completed
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {sprint_goal && (
            <p className="text-lg font-medium">{sprint_goal}</p>
          )}
          <p className="text-sm text-muted-foreground">
            The session has concluded. Here is the final sprint backlog.
          </p>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mt-6">
          Assignments by Participant
        </h3>

        {sortedAssignees.map((cp) => {
          const items = groupedItems[cp.assignee_id] || [];
          const isMe = cp.assignee_id === myParticipantId;

          return (
            <div 
              key={cp.assignee_id} 
              className={`space-y-3 p-4 rounded-xl border transition-colors ${
                isMe ? "bg-primary/5 border-primary/20 ring-1 ring-primary/10" : "bg-card"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`font-semibold ${isMe ? "text-primary" : ""}`}>
                    {cp.assignee_name || cp.assignee_id}
                    {isMe && <span className="ml-2 text-xs font-normal opacity-70">(You)</span>}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <Badge variant="outline">{cp.item_count} items</Badge>
                  <Badge variant="outline">{cp.total_story_points} SP</Badge>
                </div>
              </div>

              <div className="grid gap-2">
                {items.map((item) => (
                  <Card key={item.item_id} className="shadow-none border-dashed bg-transparent">
                    <CardHeader className="p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <CardTitle className="text-xs font-medium truncate">{item.title}</CardTitle>
                          <p className="text-[10px] text-muted-foreground font-mono truncate">{item.item_id}</p>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {item.priority && (
                            <Badge variant={priorityVariant[item.priority] || "outline"} className="text-[9px] h-4 px-1 uppercase">
                              {item.priority}
                            </Badge>
                          )}
                          {item.story_points != null && (
                            <Badge variant="outline" className="text-[9px] h-4 px-1">
                              {item.story_points} SP
                            </Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                  </Card>
                ))}
              </div>
            </div>
          );
        })}

        {groupedItems["unassigned"]?.length > 0 && (
          <div className="space-y-3 p-4 rounded-xl border bg-muted/20 border-dashed">
            <span className="text-sm font-semibold text-muted-foreground italic">Unassigned Items</span>
            <div className="grid gap-2">
              {groupedItems["unassigned"].map((item) => (
                <Card key={item.item_id} className="shadow-none border-dashed bg-transparent opacity-60">
                  <CardHeader className="p-3">
                    <CardTitle className="text-xs font-medium">{item.title}</CardTitle>
                  </CardHeader>
                </Card>
              ))}
            </div>
          </div>
        )}

        <div className="pt-4 border-t flex justify-between text-sm text-muted-foreground px-2">
          <span>Total Assigned:</span>
          <span className="font-medium text-foreground">{selected_items.length} items ({totalSP} SP)</span>
        </div>

        {/* Convergence metrics (v2 sessions) */}
        {convergence_metrics && (
          <div className="pt-4 border-t space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Convergence Metrics
            </h4>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-muted/20 rounded p-2">
                <p className="text-lg font-bold">
                  {convergence_metrics.recommendation_rounds ?? "—"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Recommendation Rounds
                </p>
              </div>
              <div className="bg-muted/20 rounded p-2">
                <p className="text-lg font-bold">
                  {convergence_metrics.assignment_rounds ?? "—"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Assignment Rounds
                </p>
              </div>
              <div className="bg-muted/20 rounded p-2">
                <p className="text-lg font-bold">
                  {convergence_metrics.retention_pct != null
                    ? `${convergence_metrics.retention_pct}%`
                    : "—"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Retention
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
