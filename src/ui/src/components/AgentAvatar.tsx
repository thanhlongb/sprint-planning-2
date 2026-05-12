import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

export type AgentState = "idle" | "thinking" | "ready" | "done";

interface AgentAvatarProps {
  name: string;
  role: string;
  type: string;
  state?: AgentState;
  isActive?: boolean; // currently taking an action (volunteering, voting)
}

export function AgentAvatar({ name, role, type, state = "idle", isActive = false }: AgentAvatarProps) {
  // AC1: Dynamic state indicators
  const stateColors = {
    idle: "bg-muted text-muted-foreground",
    thinking: "bg-amber-500/20 text-amber-600 border-amber-500/50",
    ready: "bg-blue-500/20 text-blue-600 border-blue-500/50",
    done: "bg-green-500/20 text-green-600 border-green-500/50",
  };

  const stateLabels = {
    idle: "Idle",
    thinking: "Thinking...",
    ready: "Ready",
    done: "Done",
  };

  return (
    <motion.div
      layout
      // AC3: "thinking" pulse or glow effect
      animate={
        state === "thinking"
          ? { boxShadow: ["0px 0px 0px rgba(245,158,11,0)", "0px 0px 15px rgba(245,158,11,0.5)", "0px 0px 0px rgba(245,158,11,0)"] }
          : isActive
          ? { scale: [1, 1.05, 1] }
          : {}
      }
      transition={
        state === "thinking"
          ? { duration: 2, repeat: Infinity, ease: "easeInOut" }
          : { duration: 0.3 }
      }
      className={`flex items-center justify-between p-3 rounded-lg border bg-card transition-colors ${
        state === "thinking" ? "border-amber-500/30" : "border-border"
      }`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 shrink-0 rounded-full bg-secondary flex items-center justify-center font-bold text-sm">
          {name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{name}</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground truncate">{role}</span>
            {type === "AI" && (
              <Badge variant="outline" className="text-[10px] h-4 px-1 py-0 shrink-0">AI</Badge>
            )}
          </div>
        </div>
      </div>
      <Badge variant="outline" className={`text-xs shrink-0 whitespace-nowrap ml-2 ${stateColors[state]}`}>
        {state === "thinking" ? (
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            {stateLabels[state]}
          </span>
        ) : (
          stateLabels[state]
        )}
      </Badge>
    </motion.div>
  );
}
