/** session_ready → Session start screen (AC4) */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const PHASES = [
  { id: "backlog_presentation", name: "Backlog Presentation", desc: "Product Owner presents candidate items" },
  { id: "prioritization", name: "Prioritisation", desc: "Team votes to select sprint items" },
  { id: "assignment", name: "Assignment", desc: "Selected items are assigned to developers" },
  { id: "confirmation", name: "Confirmation", desc: "Team confirms the sprint plan" },
];

interface Props {
  sessionCtx: {
    sprint_goal?: string;
    template_id?: string;
    participants?: Array<{ name: string; role: string; type: string }>;
  };
}

export default function ReadyView({ sessionCtx }: Props) {
  const { sprint_goal, template_id, participants = [] } = sessionCtx;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Session Ready!</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-lg font-medium">{sprint_goal || "—"}</p>
          <p className="text-xs text-muted-foreground">
            Template: <code>{template_id}</code>
          </p>
          <p className="text-xs text-muted-foreground">
            {participants.length} participants joined
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Session Phases</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {PHASES.map((phase, i) => (
              <li key={phase.id} className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-muted text-muted-foreground text-xs flex items-center justify-center font-medium">
                  {i + 1}
                </span>
                <div>
                  <p className="text-sm font-medium">{phase.name}</p>
                  <p className="text-xs text-muted-foreground">{phase.desc}</p>
                </div>
              </li>
            ))}
          </ol>
          <Separator className="my-3" />
          <p className="text-xs text-muted-foreground">
            The session is starting. Stay on this page to participate.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Participants</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1">
            {participants.map((p, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span>{p.name}</span>
                <div className="flex gap-2 items-center">
                  <span className="text-xs text-muted-foreground">{p.role}</span>
                  <Badge variant={p.type === "HUMAN" ? "secondary" : "outline"} className="text-xs">
                    {p.type === "HUMAN" ? "Human" : "AI"}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
