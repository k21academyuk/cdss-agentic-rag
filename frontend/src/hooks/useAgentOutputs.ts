// src/hooks/useAgentOutputs.ts
// Zustand selector for current agent outputs.

import { useSessionStore, selectAgentOutputs } from "@/stores/sessionStore";
import type { AgentOutputs } from "@/types/cdss";

export function useAgentOutputs(): AgentOutputs {
  return useSessionStore(selectAgentOutputs);
}

export function useAgentStatus(): Record<keyof AgentOutputs, string> {
  return useSessionStore((state) => state.agentStatus);
}

export function useAgentLatencies(): Record<keyof AgentOutputs, number | null> {
  return useSessionStore((state) => state.agentLatencies);
}
