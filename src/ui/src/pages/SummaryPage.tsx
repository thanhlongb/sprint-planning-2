import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

interface BacklogItem {
  item_id: string;
  title: string;
  story_points: number | null;
  priority: string;
  assigned_to: string | null;
}

interface PhaseBreakdown {
  phase_name: string;
  duration_seconds: number;
  outcome: string;
}

interface KeyDecision {
  type: string;
  description: string;
  timestamp: string | null;
}

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: "HUMAN" | "AGENT";
  message_count: number;
}

interface MetricsSnapshot {
  total_items: number;
  selected_items: number;
  assigned_items: number;
  total_story_points: number;
  human_participants: number;
  agent_participants: number;
  phase_count: number;
  total_messages: number;
}

interface Message {
  sender_id: string;
  sender_name: string;
  content: string;
  timestamp: string | null;
  kind: "human" | "agent";
}

interface SessionSummary {
  session_id: string;
  sprint_goal: string;
  template_used: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  participants: Participant[];
  backlog_output: BacklogItem[];
  phase_breakdown: PhaseBreakdown[];
  key_decisions: KeyDecision[];
  metrics_snapshot: MetricsSnapshot;
  messages: Message[];
  generation_status: "OK" | "PARTIAL";
}

const priorityVariant: Record<string, "default" | "secondary" | "outline"> = {
  HIGH: "default",
  MEDIUM: "secondary",
  LOW: "outline",
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function formatDatetime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function SummaryPage() {
  const { session_id } = useParams<{ session_id: string }>();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session_id) return;
    setLoading(true);
    fetch(`/proxy/session/${session_id}/summary`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Summary not available yet." : "Failed to load summary.");
        return r.json();
      })
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [session_id]);

  function handleCopyMarkdown() {
    if (!summary) return;
    const header = `# Sprint Backlog — ${summary.sprint_goal}\n\n| Title | Story Points | Priority | Assigned To |\n|---|---|---|---|\n`;
    const rows = summary.backlog_output
      .map((item) => `| ${item.title} | ${item.story_points ?? "—"} | ${item.priority} | ${item.assigned_to ?? "—"} |`)
      .join("\n");
    navigator.clipboard.writeText(header + rows).then(() => toast.success("Copied to clipboard"));
  }

  function handleDownloadJson() {
    if (!summary) return;
    const blob = new Blob([JSON.stringify(summary, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session-summary-${summary.session_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Loading summary…
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-3 text-muted-foreground">
        <p>{error ?? "Summary not found."}</p>
        <p className="text-xs font-mono">{session_id}</p>
      </div>
    );
  }

  const m = summary.metrics_snapshot;
  const maxPhaseDuration = Math.max(...summary.phase_breakdown.map((p) => p.duration_seconds), 1);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="max-w-5xl mx-auto p-6 md:p-10 space-y-8"
    >
      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold">Session Summary</h1>
          <p className="text-xs text-muted-foreground font-mono mt-1">{summary.session_id}</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleDownloadJson}>
          Download JSON
        </Button>
      </div>

      {summary.generation_status === "PARTIAL" && (
        <div className="rounded-md border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30 px-4 py-3 text-sm text-yellow-800 dark:text-yellow-300">
          Summary is incomplete — some data could not be retrieved.
        </div>
      )}

      {/* ── Section 1: Overview card ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardDescription className="mb-1">Sprint Goal</CardDescription>
              <CardTitle className="text-xl">{summary.sprint_goal || "—"}</CardTitle>
            </div>
            <Badge variant={summary.generation_status === "OK" ? "default" : "secondary"}>
              {summary.generation_status}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 text-sm">
            <div>
              <p className="text-muted-foreground text-xs mb-0.5">Date</p>
              <p className="font-medium">{formatDatetime(summary.started_at)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs mb-0.5">Duration</p>
              <p className="font-medium">{formatDuration(summary.duration_seconds)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs mb-0.5">Participants</p>
              <p className="font-medium">
                {summary.participants.length} total
                <span className="text-muted-foreground font-normal">
                  {" "}({m.human_participants ?? 0} human, {m.agent_participants ?? 0} agent)
                </span>
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs mb-0.5">Template</p>
              <p className="font-medium font-mono text-xs">{summary.template_used}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Section 2: Sprint Backlog panel ──────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Sprint Backlog</h2>
          <Button variant="ghost" size="sm" onClick={handleCopyMarkdown}>
            Copy as Markdown
          </Button>
        </div>

        {summary.backlog_output.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No backlog items recorded.</p>
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">Title</th>
                  <th className="text-center px-3 py-2.5 font-medium w-20">SP</th>
                  <th className="text-center px-3 py-2.5 font-medium w-24">Priority</th>
                  <th className="text-left px-4 py-2.5 font-medium">Assigned To</th>
                </tr>
              </thead>
              <tbody>
                {summary.backlog_output.map((item, i) => (
                  <tr key={item.item_id} className={i % 2 === 0 ? "bg-card" : "bg-muted/20"}>
                    <td className="px-4 py-2.5 font-medium">{item.title}</td>
                    <td className="px-3 py-2.5 text-center text-muted-foreground">
                      {item.story_points ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <Badge
                        variant={priorityVariant[item.priority] ?? "outline"}
                        className="text-[10px] h-4 px-1.5 uppercase"
                      >
                        {item.priority}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{item.assigned_to ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-xs text-muted-foreground text-right">
          {summary.backlog_output.length} items ·{" "}
          {m.total_story_points ?? 0} story points total
        </p>
      </div>

      {/* ── Section 3: Session Insights panel ────────────────────────────────── */}
      <div className="space-y-6">
        <h2 className="text-lg font-semibold">Session Insights</h2>

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Items Selected", value: `${m.selected_items ?? 0} / ${m.total_items ?? 0}` },
            { label: "Story Points", value: m.total_story_points ?? 0 },
            { label: "Assigned", value: `${m.assigned_items ?? 0} items` },
            { label: "Messages", value: m.total_messages ?? 0 },
          ].map(({ label, value }) => (
            <Card key={label} className="text-center py-4">
              <p className="text-2xl font-bold">{value}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
            </Card>
          ))}
        </div>

        {/* Phase timeline */}
        {summary.phase_breakdown.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Phase Timeline</h3>
            <div className="space-y-2">
              {summary.phase_breakdown.map((phase, i) => {
                const widthPct = Math.max(4, Math.round((phase.duration_seconds / maxPhaseDuration) * 100));
                return (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <span className="w-40 text-right text-muted-foreground text-xs shrink-0 truncate">
                      {phase.phase_name}
                    </span>
                    <div className="flex-1 bg-muted rounded-full h-5 overflow-hidden">
                      <div
                        className="h-full bg-primary/70 rounded-full flex items-center px-2 transition-all"
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-14 shrink-0">
                      {formatDuration(phase.duration_seconds)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <Separator />

        {/* Key decisions */}
        {summary.key_decisions.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Key Decisions</h3>
            <ol className="space-y-2">
              {summary.key_decisions.map((d, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  <span className="text-muted-foreground font-mono text-xs mt-0.5 w-5 shrink-0">
                    {i + 1}.
                  </span>
                  <span className="flex-1">{d.description}</span>
                  {d.timestamp && (
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatDatetime(d.timestamp)}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {/* ── Section 4: Exchanged Messages ─────────────────────────────────────── */}
      {summary.messages.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Exchanged Messages</h2>
          <div className="space-y-2">
            {summary.messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-3 ${msg.kind === "human" ? "flex-row-reverse" : ""}`}
              >
                {/* Avatar */}
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5 ${
                    msg.kind === "human"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {msg.sender_name.slice(0, 2).toUpperCase()}
                </div>

                {/* Bubble */}
                <div className={`max-w-[80%] space-y-0.5 ${msg.kind === "human" ? "items-end" : "items-start"} flex flex-col`}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium">{msg.sender_name}</span>
                    {msg.timestamp && (
                      <span className="text-[10px] text-muted-foreground">{formatDatetime(msg.timestamp)}</span>
                    )}
                  </div>
                  <div
                    className={`px-3 py-2 rounded-xl text-sm leading-relaxed ${
                      msg.kind === "human"
                        ? "bg-primary text-primary-foreground rounded-tr-sm"
                        : "bg-muted text-foreground rounded-tl-sm"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
