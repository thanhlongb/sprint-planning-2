import { AgentAvatar, AgentState } from "./AgentAvatar";

interface Participant {
  participant_id: string | null;
  name: string;
  role: string;
  type: string;
}

interface Props {
  participants: Participant[];
  currentTaskType?: string;
  myParticipantId: string;
}

export function ParticipantsSidebar({ participants, currentTaskType, myParticipantId }: Props) {
  if (participants.length === 0) return null;

  // Infer pseudo-states for UI demonstration based on the current task type
  // In a real implementation, these would stream from the backend
  const getSimulatedState = (p: Participant): AgentState => {
    if (p.participant_id === myParticipantId) return "idle";
    
    switch (currentTaskType) {
      case "vote":
      case "assign_opportunity":
      case "confirm":
        return "thinking";
      case "session_ready":
      case "present_backlog":
      case "sprint_backlog":
        return "idle";
      default:
        return "idle";
    }
  };

  return (
    <div className="w-64 shrink-0 space-y-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        Participants
      </h3>
      <div className="space-y-2">
        {participants.map((p, i) => (
          <AgentAvatar
            key={p.participant_id || i}
            name={p.name}
            role={p.role}
            type={p.type}
            state={getSimulatedState(p)}
          />
        ))}
      </div>
    </div>
  );
}
