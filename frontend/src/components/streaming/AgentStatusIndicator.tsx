// src/components/streaming/AgentStatusIndicator.tsx
import { Loader2, CheckCircle, XCircle, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { tokens } from "@/styles/design-tokens";
import type { AgentOutputs } from "@/types/cdss";

type AgentStatus = "idle" | "running" | "completed" | "error";
type AgentName = keyof AgentOutputs;

export interface AgentStatusIndicatorProps {
  agentName: AgentName;
  status: AgentStatus;
  latencyMs?: number | null;
  className?: string;
}

const agentLabels: Record<AgentName, string> = {
  patient_history: "Patient History",
  literature: "Literature",
  protocols: "Protocols",
  drug_safety: "Drug Safety",
};

const agentColors: Record<AgentName, string> = {
  patient_history: tokens.color.agent.patientHistory,
  literature: tokens.color.agent.literature,
  protocols: tokens.color.agent.protocol,
  drug_safety: tokens.color.agent.drugSafety,
};

export function AgentStatusIndicator({
  agentName,
  status,
  latencyMs,
  className = "",
}: AgentStatusIndicatorProps): JSX.Element {
  const label = agentLabels[agentName];
  const color = agentColors[agentName];

  const renderStatus = () => {
    switch (status) {
      case "idle":
        return (
          <>
            <Circle
              className="w-3 h-3"
              style={{ color: tokens.color.text.muted }}
              aria-hidden="true"
            />
            <span className="text-clinical-text-muted">Waiting</span>
          </>
        );

      case "running":
        return (
          <>
            <Loader2
              className="w-3 h-3 animate-spin"
              style={{ color }}
              aria-hidden="true"
            />
            <span style={{ color }}>Processing...</span>
          </>
        );

      case "completed":
        return (
          <>
            <CheckCircle
              className="w-3 h-3"
              style={{ color: tokens.color.confidence.high }}
              aria-hidden="true"
            />
            <span className="text-clinical-text-secondary">
              {latencyMs !== null && latencyMs !== undefined ? `${latencyMs}ms` : "Done"}
            </span>
          </>
        );

      case "error":
        return (
          <>
            <XCircle
              className="w-3 h-3"
              style={{ color: tokens.color.alert.critical }}
              aria-hidden="true"
            />
            <span style={{ color: tokens.color.alert.critical }}>Failed</span>
          </>
        );

      default:
        return null;
    }
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 max-w-[200px] text-xs font-medium",
        className
      )}
      role="status"
      aria-label={`${label} agent: ${status}`}
    >
      <span className="text-clinical-text-primary">{label}:</span>
      {renderStatus()}
    </div>
  );
}
