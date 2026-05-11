/**
 * JoinPage — AC2, AC3
 *
 * Visiting /join/:session_id shows the session lobby with sprint goal,
 * declared participants, and waiting status. Human selects their declared
 * role and clicks Join, which calls POST /proxy/join (which calls the
 * platform's POST /sessions/{id}/join with the proxy endpoint included).
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface SessionDetail {
  session_id: string;
  sprint_goal: string;
  status: string;
  template: string;
  timeout_at: string;
  participants: Array<{
    participant_id: string | null;
    name: string;
    role: string;
    type: string;
    status: string;
  }>;
}

export default function JoinPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const navigate = useNavigate();

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);

  // Derived list of human slots that haven't joined yet
  const humanSlots =
    session?.participants.filter(
      (p) => p.type === "HUMAN" && p.status === "declared"
    ) ?? [];

  const [selectedName, setSelectedName] = useState<string>("");
  const [selectedRole, setSelectedRole] = useState<string>("");

  // Auto-select if only one human slot
  useEffect(() => {
    if (humanSlots.length === 1) {
      setSelectedName(humanSlots[0].name);
      setSelectedRole(humanSlots[0].role);
    }
  }, [session]);

  useEffect(() => {
    if (!session_id) return;
    fetch(`/proxy/session/${session_id}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.detail) {
          setError(
            typeof data.detail === "string"
              ? data.detail
              : data.detail?.reason ?? "Session not found"
          );
        } else {
          setSession(data);
        }
      })
      .catch(() => setError("Could not reach the platform"))
      .finally(() => setLoading(false));
  }, [session_id]);

  async function handleJoin() {
    if (!selectedName || !selectedRole || !session_id) return;
    setJoining(true);
    try {
      const resp = await fetch("/proxy/join", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id, name: selectedName, role: selectedRole }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setError(data.detail?.reason ?? data.error ?? "Join failed");
        return;
      }
      // Store participant_id for this session
      sessionStorage.setItem(`pid:${session_id}`, data.participant_id);
      navigate(`/session/${session_id}`);
    } catch {
      setError("Network error — could not join session");
    } finally {
      setJoining(false);
    }
  }

  if (loading) {
    return (
      <main className="max-w-2xl mx-auto p-8">
        <p className="text-muted-foreground">Loading session…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="max-w-2xl mx-auto p-8 space-y-4">
        <h1 className="text-2xl font-bold">Join Session</h1>
        <Card className="border-destructive">
          <CardContent className="pt-6 text-destructive">{error}</CardContent>
        </Card>
      </main>
    );
  }

  if (!session) return null;

  const waitingFor = session.participants
    .filter((p) => p.status === "declared")
    .map((p) => p.name);

  return (
    <main className="max-w-2xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Join Session</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Session ID:{" "}
          <code className="bg-muted px-1 py-0.5 rounded text-xs">
            {session.session_id}
          </code>
        </p>
      </div>

      {/* Sprint goal */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sprint Goal</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-medium">
            {session.sprint_goal || <em className="text-muted-foreground">No goal set</em>}
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Template: <code>{session.template}</code>
          </p>
        </CardContent>
      </Card>

      {/* Participants */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Participants</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2">
            {session.participants.map((p, i) => (
              <li key={i} className="flex items-center justify-between">
                <span className="text-sm">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-muted-foreground ml-2">({p.role})</span>
                </span>
                <Badge
                  variant={p.status === "joined" ? "default" : "secondary"}
                  className="text-xs"
                >
                  {p.status === "joined" ? "✓ Joined" : "Waiting"}
                </Badge>
              </li>
            ))}
          </ul>

          {waitingFor.length > 0 && (
            <p className="text-xs text-muted-foreground mt-4">
              Still waiting for: <strong>{waitingFor.join(", ")}</strong>
            </p>
          )}
        </CardContent>
      </Card>

      {/* Join form */}
      {humanSlots.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Your Seat</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {humanSlots.length === 1 ? (
              <div className="space-y-1">
                <Label>Name</Label>
                <p className="text-sm font-medium">{selectedName}</p>
                <Label className="mt-2">Role</Label>
                <p className="text-sm font-medium">{selectedRole}</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label>Select your seat</Label>
                  <Select
                    onValueChange={(v) => {
                      const slot = humanSlots.find((s) => s.name === v);
                      if (slot) {
                        setSelectedName(slot.name);
                        setSelectedRole(slot.role);
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose your name…" />
                    </SelectTrigger>
                    <SelectContent>
                      {humanSlots.map((s) => (
                        <SelectItem key={s.name} value={s.name}>
                          {s.name} — {s.role}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <Button
              className="w-full"
              disabled={!selectedName || !selectedRole || joining}
              onClick={handleJoin}
            >
              {joining ? "Joining…" : "Join Session"}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6 text-muted-foreground text-sm">
            No open human seats in this session.
          </CardContent>
        </Card>
      )}
    </main>
  );
}
