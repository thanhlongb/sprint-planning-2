/**
 * VoteView — Dot voting interface for the "vote" task type (AC4, AC5)
 *
 * Each participant gets a fixed pool of dots to allocate across backlog items.
 * Dots can be dragged from the pool onto an item, or clicked to add/remove.
 * Submission sends { votes: { item_id: "HIGH" | "MEDIUM" | "LOW" } } where:
 *   ≥2 dots → HIGH, 1 dot → MEDIUM, 0 dots → LOW
 */
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  description: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  story_points: number | null;
  labels: string[];
}

interface Props {
  taskId: string;
  sessionCtx: {
    backlog_items?: BacklogItem[];
  };
  payload: {
    items?: string[];
  };
  onSubmit: (taskId: string, artifact: Record<string, unknown>) => void;
  submitted: boolean;
}

const TOTAL_DOTS = 12;

function dotsToVote(dots: number): "HIGH" | "MEDIUM" | "LOW" {
  if (dots >= 2) return "HIGH";
  if (dots === 1) return "MEDIUM";
  return "LOW";
}

export default function VoteView({ taskId, sessionCtx, payload, onSubmit, submitted }: Props) {
  const { backlog_items = [] } = sessionCtx;
  const itemIds: string[] = payload.items ?? backlog_items.map((i) => i.item_id);

  const itemMap = Object.fromEntries(backlog_items.map((i) => [i.item_id, i]));

  // allocations: item_id → number of dots
  const [allocations, setAllocations] = useState<Record<string, number>>(
    Object.fromEntries(itemIds.map((id) => [id, 0]))
  );

  const usedDots = Object.values(allocations).reduce((a, b) => a + b, 0);
  const remainingDots = TOTAL_DOTS - usedDots;

  function addDot(itemId: string) {
    if (remainingDots <= 0) return;
    setAllocations((prev) => ({ ...prev, [itemId]: (prev[itemId] ?? 0) + 1 }));
  }

  function removeDot(itemId: string) {
    setAllocations((prev) => ({
      ...prev,
      [itemId]: Math.max(0, (prev[itemId] ?? 0) - 1),
    }));
  }

  function resetDots() {
    setAllocations(Object.fromEntries(itemIds.map((id) => [id, 0])));
  }

  function handleSubmit() {
    const votes: Record<string, string> = {};
    for (const id of itemIds) {
      votes[id] = dotsToVote(allocations[id] ?? 0);
    }
    onSubmit(taskId, { votes });
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Vote: Prioritise Backlog Items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Allocate your <strong>{TOTAL_DOTS} dots</strong> across items to indicate priority.
            Items with more dots are ranked higher.
          </p>
          <div className="flex items-center gap-2">
            <span className="text-sm">Remaining dots:</span>
            <div className="flex gap-1">
              {Array.from({ length: TOTAL_DOTS }).map((_, i) => (
                <span
                  key={i}
                  className={`w-4 h-4 rounded-full border-2 ${i < remainingDots
                    ? "bg-primary border-primary"
                    : "bg-background border-muted"
                    }`}
                />
              ))}
            </div>
            <Button variant="ghost" size="sm" onClick={resetDots} disabled={submitted}>
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {itemIds.map((itemId) => {
          const item = itemMap[itemId];
          const dots = allocations[itemId] ?? 0;

          return (
            <Card key={itemId} className={dots > 0 ? "ring-2 ring-primary/30" : ""}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <CardTitle className="text-sm font-medium">
                    {item?.title ?? itemId}
                  </CardTitle>
                  {item?.story_points != null && (
                    <Badge variant="outline" className="text-xs flex-shrink-0">
                      {item.story_points} SP
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-3">
                {item?.description && (
                  <p className="text-xs text-muted-foreground">{item.description}</p>
                )}
                <Separator />
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    {Array.from({ length: TOTAL_DOTS }).map((_, i) => (
                      <button
                        key={i}
                        disabled={submitted}
                        onClick={() => (i < dots ? removeDot(itemId) : addDot(itemId))}
                        className={`w-5 h-5 rounded-full border-2 transition-all cursor-pointer ${i < dots
                          ? "bg-primary border-primary scale-110"
                          : remainingDots > 0
                            ? "bg-background border-muted hover:border-primary/50"
                            : "bg-background border-muted opacity-40 cursor-not-allowed"
                          }`}
                        title={i < dots ? "Click to remove dot" : "Click to add dot"}
                      />
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        dots >= 2 ? "default" : dots === 1 ? "secondary" : "outline"
                      }
                      className="text-xs"
                    >
                      {dotsToVote(dots)}
                    </Badge>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 w-7 p-0"
                        disabled={dots === 0 || submitted}
                        onClick={() => removeDot(itemId)}
                      >
                        −
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 w-7 p-0"
                        disabled={remainingDots === 0 || submitted}
                        onClick={() => addDot(itemId)}
                      >
                        +
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Button
        className="w-full"
        onClick={handleSubmit}
        disabled={submitted}
      >
        {submitted ? "Votes submitted ✓" : "Submit Votes"}
      </Button>
    </div>
  );
}
