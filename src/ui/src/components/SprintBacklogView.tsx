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
  };
}

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

export default function SprintBacklogView({ payload }: Props) {
  const { sprint_goal, selected_items = [], capacity_plan = [] } = payload;

  const totalSP = capacity_plan.reduce((acc, curr) => acc + (curr.total_story_points || 0), 0);

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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Capacity Plan</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
            {capacity_plan.map((cp) => (
              <div
                key={cp.assignee_id}
                className="flex flex-col gap-1 p-3 border rounded-md bg-muted/30"
              >
                <span className="font-medium text-sm">{cp.assignee_name || cp.assignee_id}</span>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{cp.item_count} items</span>
                  <span>&bull;</span>
                  <span>{cp.total_story_points} SP</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-4 border-t flex justify-between text-sm">
            <span className="font-medium">Total Assigned:</span>
            <span className="font-medium">{selected_items.length} items ({totalSP} SP)</span>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mt-6 mb-2">
          Final Backlog
        </h3>
        {selected_items.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-muted-foreground text-sm">
              No items selected for this sprint.
            </CardContent>
          </Card>
        ) : (
          selected_items.map((item) => (
            <Card key={item.item_id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-sm font-medium">{item.title}</CardTitle>
                    <p className="text-xs text-muted-foreground mt-1 font-mono">{item.item_id}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                    <Badge variant="secondary" className="text-xs font-medium">
                      {item.assignee_name || item.assignee_id || "Unassigned"}
                    </Badge>
                    <div className="flex items-center gap-1.5">
                      {item.priority && (
                        <Badge variant={priorityVariant[item.priority] || "outline"} className="text-[10px] uppercase">
                          {item.priority}
                        </Badge>
                      )}
                      {item.story_points != null && (
                        <Badge variant="outline" className="text-[10px]">
                          {item.story_points} SP
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </CardHeader>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
