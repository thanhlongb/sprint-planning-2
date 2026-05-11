/** session_invite → Lobby view (AC4) */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: string;
}

interface Props {
  sessionCtx: {
    sprint_goal?: string;
    participants?: Participant[];
  };
}

export default function LobbyView({ sessionCtx }: Props) {
  const { sprint_goal, participants = [] } = sessionCtx;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sprint Goal</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-medium">
            {sprint_goal || <em className="text-muted-foreground">Awaiting goal…</em>}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Waiting for participants</CardTitle>
        </CardHeader>
        <CardContent>
          {participants.length === 0 ? (
            <p className="text-sm text-muted-foreground">No participants declared yet.</p>
          ) : (
            <ul className="space-y-2">
              {participants.map((p, i) => (
                <li key={i} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{p.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{p.role}</span>
                    <Badge variant={p.type === "HUMAN" ? "secondary" : "outline"} className="text-xs">
                      {p.type === "HUMAN" ? "Human" : "AI"}
                    </Badge>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Separator className="my-3" />
          <p className="text-xs text-muted-foreground">
            Waiting for all participants to join before the session starts…
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
