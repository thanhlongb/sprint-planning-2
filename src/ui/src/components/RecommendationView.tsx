/**
 * RecommendationView — US-39 v2 Discussion-Driven Recommendation Phase
 *
 * Replaces BacklogView + VoteView for v2 sessions.
 * Shows platform-recommended item list with scores, round counter,
 * add/remove/modify discussion panel.
 * Subscribes to comm-feed for recommendation/recommendation_update events.
 */
import { useEffect, useRef, useState, useCallback } from "react";
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
  dependencies: string[];
  score?: number;
}

interface RecommendationState {
  context: string;
  items: BacklogItem[];
  round: number;
}

interface Props {
  sessionId: string;
  sessionCtx: {
    sprint_goal?: string;
    backlog_items?: BacklogItem[];
    template_id?: string;
  };
  myParticipantId: string;
  myName?: string;
}

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

export default function RecommendationView({
  sessionId,
  sessionCtx,
  myParticipantId,
  myName,
}: Props) {
  const { sprint_goal, backlog_items: ctxItems = [] } = sessionCtx;

  const [items, setItems] = useState<BacklogItem[]>(ctxItems);
  const [round, setRound] = useState(0);
  const [addTitle, setAddTitle] = useState("");
  const [addSP, setAddSP] = useState<number | string>("");
  const [connected, setConnected] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  // Subscribe to comm-feed for recommendation updates
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

        // Handle discussion_update broadcasts from platform
        if (
          data.task_type === "discussion_update" &&
          content.context === "recommendation"
        ) {
          const recState = data as {
            content: RecommendationState;
          };
          // Map items, preserving any score field
          const recItems: BacklogItem[] = (recState.content.items || []).map(
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
          setItems(recItems);
          setRound(recState.content.round ?? 0);
        }
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => setConnected(false);

    return () => es.close();
  }, [sessionId]);

  // Send a discussion action via the proxy
  const sendAction = useCallback(
    async (action: string, content: Record<string, unknown>) => {
      try {
        await fetch("/proxy/discussion-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            sender_id: myParticipantId,
            sender_name: myName || myParticipantId,
            action,
            content,
          }),
        });
      } catch {
        // silently fail — comm bus will handle
      }
    },
    [sessionId, myParticipantId, myName]
  );

  function handleAddItem() {
    const title = addTitle.trim();
    if (!title) return;
    const sp = typeof addSP === "number" ? addSP : Number(addSP);
    const itemId = `human-${Date.now()}`;
    sendAction("add_item", {
      item: {
        item_id: itemId,
        title,
        description: "",
        priority: "MEDIUM",
        story_points: isNaN(sp) ? null : sp,
        labels: [],
        dependencies: [],
      },
    });
    setAddTitle("");
    setAddSP("");
  }

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

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              Goal-Aligned Recommendation
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
        <CardContent className="space-y-2">
          {sprint_goal && (
            <p className="text-sm">
              <span className="font-medium">Sprint Goal:</span> {sprint_goal}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            The platform recommends these items aligned to the goal. Discuss and
            refine the list below.
          </p>
        </CardContent>
      </Card>

      {/* Add Item Form */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Add Item</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-muted-foreground">Title</label>
              <input
                type="text"
                value={addTitle}
                onChange={(e) => setAddTitle(e.target.value)}
                placeholder="New item title..."
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAddItem();
                }}
                className="w-full text-sm rounded border border-border bg-background px-2 py-1.5 text-foreground placeholder:text-muted-foreground"
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-muted-foreground">SP</label>
              <input
                type="number"
                min={0}
                value={addSP}
                onChange={(e) =>
                  setAddSP(e.target.value === "" ? "" : Number(e.target.value))
                }
                placeholder="SP"
                className="w-full text-sm rounded border border-border bg-background px-2 py-1.5 text-foreground placeholder:text-muted-foreground"
              />
            </div>
            <Button size="sm" onClick={handleAddItem} disabled={!addTitle.trim()}>
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Item List */}
      {items.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-muted-foreground text-sm">
            Waiting for platform recommendation…
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Card key={item.item_id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-sm font-medium">
                      {item.title}
                    </CardTitle>
                    <p className="text-xs text-muted-foreground font-mono mt-0.5">
                      {item.item_id}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Badge
                      variant={priorityVariant[item.priority] || "outline"}
                      className="text-xs"
                    >
                      {item.priority}
                    </Badge>
                    {item.story_points != null && (
                      <Badge variant="outline" className="text-xs">
                        {item.story_points} SP
                      </Badge>
                    )}
                    {item.score != null && (
                      <Badge variant="secondary" className="text-xs">
                        {typeof item.score === "number"
                          ? item.score.toFixed(1)
                          : item.score}
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                {item.description && (
                  <p className="text-xs text-muted-foreground">
                    {item.description}
                  </p>
                )}
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

                <Separator />

                {/* Discussion controls */}
                <div className="flex items-center gap-2 flex-wrap">
                  {/* Modify SP */}
                  <div className="flex items-center gap-1">
                    <label className="text-xs text-muted-foreground">SP:</label>
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
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          const val = Number(
                            (e.target as HTMLInputElement).value
                          );
                          if (!isNaN(val) && val >= 0) {
                            handleModifySP(item.item_id, val);
                          }
                        }
                      }}
                      className="w-16 text-xs rounded border border-border bg-background px-1.5 py-0.5 text-foreground"
                    />
                  </div>

                  {/* Modify Priority */}
                  <select
                    defaultValue={item.priority}
                    onChange={(e) =>
                      handleModifyPriority(item.item_id, e.target.value)
                    }
                    className="text-xs rounded border border-border bg-background px-1.5 py-0.5 text-foreground"
                  >
                    <option value="HIGH">HIGH</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="LOW">LOW</option>
                  </select>

                  {/* Remove */}
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs text-destructive hover:text-destructive"
                    onClick={() => handleRemoveItem(item.item_id)}
                  >
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
