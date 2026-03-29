// src/stores/sessionStore.ts
// Zustand store for active clinical session state.
// Manages streaming lifecycle for all 5 agents.

import { create } from "zustand";
import type {
  AgentOutputs,
  ClinicalResponse,
  GuardrailsResult,
  StreamingEvent,
  PatientHistoryOutput,
  LiteratureOutput,
  ProtocolOutput,
  DrugSafetyOutput,
} from "@/types/cdss";

type AgentStatus = "idle" | "running" | "completed" | "error";
type SynthesisStatus = "idle" | "streaming" | "completed" | "error";

interface AgentStatusMap {
  patient_history: AgentStatus;
  literature: AgentStatus;
  protocols: AgentStatus;
  drug_safety: AgentStatus;
}

interface SessionState {
  // Session metadata
  sessionId: string | null;
  patientId: string | null;
  traceId: string | null;

  // Agent status tracking
  agentStatus: AgentStatusMap;

  // Agent outputs (streaming updates)
  agentOutputs: AgentOutputs;

  // Synthesis state
  synthesisStatus: SynthesisStatus;
  synthesisChunks: string[];
  response: ClinicalResponse | null;

  // Guardrails
  guardrails: GuardrailsResult | null;

  // Latency tracking
  totalLatencyMs: number | null;
  agentLatencies: Record<keyof AgentOutputs, number | null>;

  // Error tracking
  errors: Record<string, string>;

  // Actions
  startSession: (sessionId: string, patientId: string, traceId: string) => void;
  handleStreamingEvent: (event: StreamingEvent) => void;
  resetSession: () => void;
}

const initialAgentStatus: AgentStatusMap = {
  patient_history: "idle",
  literature: "idle",
  protocols: "idle",
  drug_safety: "idle",
};

const initialAgentOutputs: AgentOutputs = {
  patient_history: null,
  literature: null,
  protocols: null,
  drug_safety: null,
};

const initialAgentLatencies: Record<keyof AgentOutputs, number | null> = {
  patient_history: null,
  literature: null,
  protocols: null,
  drug_safety: null,
};

export const useSessionStore = create<SessionState>((set, get) => ({
  // Initial state
  sessionId: null,
  patientId: null,
  traceId: null,

  agentStatus: { ...initialAgentStatus },
  agentOutputs: { ...initialAgentOutputs },

  synthesisStatus: "idle",
  synthesisChunks: [],
  response: null,

  guardrails: null,

  totalLatencyMs: null,
  agentLatencies: { ...initialAgentLatencies },

  errors: {},

  // Actions
  startSession: (sessionId: string, patientId: string, traceId: string) => {
    set({
      sessionId,
      patientId,
      traceId,
      agentStatus: { ...initialAgentStatus },
      agentOutputs: { ...initialAgentOutputs },
      synthesisStatus: "idle",
      synthesisChunks: [],
      response: null,
      guardrails: null,
      totalLatencyMs: null,
      agentLatencies: { ...initialAgentLatencies },
      errors: {},
    });
  },

  handleStreamingEvent: (event: StreamingEvent) => {
    const { agent, event_type, data } = event;

    switch (event_type) {
      case "agent_started": {
        if (!agent) return;
        set((state) => ({
          agentStatus: {
            ...state.agentStatus,
            [agent]: "running",
          },
        }));
        break;
      }

      case "agent_completed": {
        if (!agent) return;

        // Type-safe update based on which agent completed
        const updates: Partial<SessionState> = {
          agentStatus: {
            ...get().agentStatus,
            [agent]: "completed",
          },
        };

        // Update the appropriate agent output
        switch (agent) {
          case "patient_history": {
            const output = data as PatientHistoryOutput;
            updates.agentOutputs = {
              ...get().agentOutputs,
              patient_history: output,
            };
            updates.agentLatencies = {
              ...get().agentLatencies,
              patient_history: output.latency_ms,
            };
            break;
          }
          case "literature": {
            const output = data as LiteratureOutput;
            updates.agentOutputs = {
              ...get().agentOutputs,
              literature: output,
            };
            updates.agentLatencies = {
              ...get().agentLatencies,
              literature: output.latency_ms,
            };
            break;
          }
          case "protocols": {
            const output = data as ProtocolOutput;
            updates.agentOutputs = {
              ...get().agentOutputs,
              protocols: output,
            };
            updates.agentLatencies = {
              ...get().agentLatencies,
              protocols: output.latency_ms,
            };
            break;
          }
          case "drug_safety": {
            const output = data as DrugSafetyOutput;
            updates.agentOutputs = {
              ...get().agentOutputs,
              drug_safety: output,
            };
            updates.agentLatencies = {
              ...get().agentLatencies,
              drug_safety: output.latency_ms,
            };
            break;
          }
        }

        set(updates as SessionState);
        break;
      }

      case "agent_error": {
        if (!agent) return;
        const errorMessage = typeof data === "string" ? data : (data as { message?: string })?.message || "Agent error";
        set((state) => ({
          agentStatus: {
            ...state.agentStatus,
            [agent]: "error",
          },
          errors: {
            ...state.errors,
            [agent]: errorMessage,
          },
        }));
        break;
      }

      case "synthesis_started": {
        set({
          synthesisStatus: "streaming",
          synthesisChunks: [],
        });
        break;
      }

      case "synthesis_chunk": {
        const chunk = typeof data === "string" ? data : (data as { chunk?: string })?.chunk || "";
        set((state) => ({
          synthesisChunks: [...state.synthesisChunks, chunk],
        }));
        break;
      }

      case "synthesis_completed": {
        const responseData = data as ClinicalResponse;
        set({
          synthesisStatus: "completed",
          response: responseData,
          synthesisChunks: [],
        });
        break;
      }

      case "guardrails_completed": {
        const guardrailsData = data as GuardrailsResult;
        set({
          guardrails: guardrailsData,
        });
        break;
      }

      default:
        console.warn(`Unknown streaming event type: ${event_type}`);
    }
  },

  resetSession: () => {
    set({
      sessionId: null,
      patientId: null,
      traceId: null,
      agentStatus: { ...initialAgentStatus },
      agentOutputs: { ...initialAgentOutputs },
      synthesisStatus: "idle",
      synthesisChunks: [],
      response: null,
      guardrails: null,
      totalLatencyMs: null,
      agentLatencies: { ...initialAgentLatencies },
      errors: {},
    });
  },
}));

// Selectors for optimized re-renders
export const selectSessionId = (state: SessionState) => state.sessionId;
export const selectPatientId = (state: SessionState) => state.patientId;
export const selectAgentStatus = (state: SessionState) => state.agentStatus;
export const selectAgentOutputs = (state: SessionState) => state.agentOutputs;
export const selectSynthesisStatus = (state: SessionState) => state.synthesisStatus;
export const selectResponse = (state: SessionState) => state.response;
export const selectGuardrails = (state: SessionState) => state.guardrails;
export const selectErrors = (state: SessionState) => state.errors;
export const selectAgentLatencies = (state: SessionState) => state.agentLatencies;
