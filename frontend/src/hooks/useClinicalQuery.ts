// src/hooks/useClinicalQuery.ts
// TanStack Query wrapper for CDSS API calls.
// Handles: session creation, patient profile fetch, conversation history.
// Does NOT handle streaming — that's the WebSocket layer.

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  PatientProfile,
  ConversationTurn,
  ClinicalQuery,
  QueryResponse,
  ApiError,
} from "@/types/cdss";
import { getAccessToken } from "@/lib/auth";
import { runtimeConfig } from "@/config/runtime";

const API_BASE = runtimeConfig.apiBaseUrl;

async function buildAuthHeaders(): Promise<HeadersInit> {
  const token = await getAccessToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// API Error handler
async function handleApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorData = (await response.json()) as ApiError;
      errorMessage = errorData.message || errorData.details?.toString() || errorMessage;
    } catch {
      // Failed to parse error response, use default message
    }
    throw new Error(errorMessage);
  }
  return response.json() as Promise<T>;
}

// Patient Profile Query
export function usePatientProfile(patientId: string | null) {
  return useQuery<PatientProfile, Error>({
    queryKey: ["patient-profile", patientId],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/v1/patients/${patientId}`, {
        headers: await buildAuthHeaders(),
      });
      return handleApiResponse<PatientProfile>(response);
    },
    enabled: !!patientId,
    staleTime: 5 * 60 * 1000, // Patient data refreshes every 5 minutes
    gcTime: 30 * 60 * 1000, // Keep in cache for 30 minutes
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}

// Conversation History Query
export function useConversationHistory(sessionId: string | null) {
  return useQuery<ConversationTurn[], Error>({
    queryKey: ["conversation", sessionId],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/v1/sessions/${sessionId}/turns`, {
        headers: await buildAuthHeaders(),
      });
      return handleApiResponse<ConversationTurn[]>(response);
    },
    enabled: !!sessionId,
    refetchInterval: false, // Only refetch on explicit invalidation
    retry: 1,
  });
}

// Submit Query Mutation
export function useSubmitQuery() {
  const queryClient = useQueryClient();

  return useMutation<QueryResponse, Error, ClinicalQuery>({
    mutationFn: async (payload: ClinicalQuery) => {
      const response = await fetch(`${API_BASE}/v1/query`, {
        method: "POST",
        headers: await buildAuthHeaders(),
        body: JSON.stringify(payload),
      });
      return handleApiResponse<QueryResponse>(response);
    },
    onSuccess: (_data, variables) => {
      // Invalidate conversation history for this session
      if (variables.session_id) {
        queryClient.invalidateQueries({
          queryKey: ["conversation", variables.session_id],
        });
      }
    },
  });
}

// Session Creation Mutation
export function useCreateSession() {
  return useMutation<
    { session_id: string; patient_id: string },
    Error,
    { patient_id: string }
  >({
    mutationFn: async ({ patient_id }) => {
      const response = await fetch(`${API_BASE}/v1/sessions`, {
        method: "POST",
        headers: await buildAuthHeaders(),
        body: JSON.stringify({ patient_id }),
      });
      return handleApiResponse<{ session_id: string; patient_id: string }>(response);
    },
  });
}

// Clinician Feedback Mutation
export function useSubmitFeedback() {
  return useMutation<
    { success: boolean },
    Error,
    { turnId: string; rating: number; correction?: string }
  >({
    mutationFn: async ({ turnId, rating, correction }) => {
      const response = await fetch(`${API_BASE}/v1/turns/${turnId}/feedback`, {
        method: "POST",
        headers: await buildAuthHeaders(),
        body: JSON.stringify({
          clinician_rating: rating,
          clinician_correction: correction || null,
        }),
      });
      return handleApiResponse<{ success: boolean }>(response);
    },
  });
}
