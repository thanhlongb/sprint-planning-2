/**
 * HomePage — lists all sessions and provides navigation to join one.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface SessionSummary {
  session_id: string;
  sprint_goal: string;
  status: string;
  join_url: string;
  template: string;
}

const PLATFORM_URL = import.meta.env.VITE_PLATFORM_URL ?? "http://localhost:8000";

export default function HomePage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [health, setHealth] = useState<string>("…");

  useEffect(() => {
    fetch(`${PLATFORM_URL}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.status))
      .catch(() => setHealth("unreachable"));

    fetch(`${PLATFORM_URL}/sessions`)
      .then((r) => r.json())
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);

  function joinSession(id: string) {
    navigate(`/join/${id}`);
  }

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Sprint Planning 2.0</h1>
        <p className="text-muted-foreground mt-1">
          Platform:{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">{PLATFORM_URL}</code>{" "}
          — status: <strong>{health}</strong>
        </p>
      </div>

      <section>
        <h2 className="text-xl font-semibold mb-4">Active Sessions</h2>
        {sessions.length === 0 ? (
          <p className="text-muted-foreground">No sessions found.</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Card key={s.session_id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-base font-medium">
                      {s.sprint_goal || "—"}
                    </CardTitle>
                    <Badge
                      variant={s.status === "ACTIVE" ? "default" : "secondary"}
                    >
                      {s.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground font-mono">
                    {s.session_id}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={s.status !== "PENDING"}
                    onClick={() => joinSession(s.session_id)}
                  >
                    {s.status === "PENDING" ? "Join" : "View"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
