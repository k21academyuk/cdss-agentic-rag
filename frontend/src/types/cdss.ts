// src/types/cdss.ts
// Typed interfaces for all CDSS backend agent outputs.
// These types are the SINGLE SOURCE OF TRUTH for frontend data shapes.
// If the backend changes its schema, this file changes first.

// ─── Medical Coding ──────────────────────────────────────────
export interface MedicalCode {
  code: string;
  system: "ICD-10" | "SNOMED-CT" | "LOINC" | "CPT" | "RxNorm";
  display: string;
}

export interface ExtractedEntity {
  type: "condition" | "medication" | "procedure" | "lab_test" | "anatomical_site";
  value: string;
  code: string;
}

// ─── Patient Context ─────────────────────────────────────────
export interface Demographics {
  age: number;
  sex: "M" | "F" | "Other";
  weight_kg: number;
  height_cm: number;
  blood_type: string;
}

export interface ActiveCondition {
  code: string;
  system: "ICD-10";
  display: string;
  onset_date: string;
  status: "active" | "resolved" | "remission";
}

export interface ActiveMedication {
  rxcui: string;
  name: string;
  dose: string;
  frequency: string;
  start_date: string;
  prescriber: string;
}

export interface Allergy {
  substance: string;
  reaction: string;
  severity: "mild" | "moderate" | "severe";
  code: string;
  system: "SNOMED-CT";
}

export interface LabResult {
  code: string;
  system: "LOINC";
  display: string;
  value: number;
  unit: string;
  date: string;
  reference_range: string;
}

export interface PatientProfile {
  id: string;
  patient_id: string;
  demographics: Demographics;
  active_conditions: ActiveCondition[];
  active_medications: ActiveMedication[];
  allergies: Allergy[];
  recent_labs: LabResult[];
  last_updated: string;
}

// ─── Agent Outputs ───────────────────────────────────────────
export interface PatientHistoryOutput {
  agent: "patient_history_agent";
  latency_ms: number;
  sources_retrieved: number;
  summary: string;
}

export interface LiteratureOutput {
  agent: "medical_literature_agent";
  latency_ms: number;
  papers_retrieved: number;
  top_citations: string[];
}

export interface ProtocolOutput {
  agent: "protocol_agent";
  latency_ms: number;
  guidelines_matched: string[];
}

export type DrugAlertSeverity = "minor" | "moderate" | "major";

export interface DrugAlert {
  severity: DrugAlertSeverity;
  description: string;
  source: "DrugBank" | "OpenFDA" | "RxNorm";
  evidence_level: number;
}

export interface DrugSafetyOutput {
  agent: "drug_safety_agent";
  latency_ms: number;
  interactions_found: number;
  alerts: DrugAlert[];
}

export interface AgentOutputs {
  patient_history: PatientHistoryOutput | null;
  literature: LiteratureOutput | null;
  protocols: ProtocolOutput | null;
  drug_safety: DrugSafetyOutput | null;
}

// ─── Citations ───────────────────────────────────────────────
export interface PubMedCitation {
  pmid: string;
  title: string;
  relevance: number;
}

export interface GuidelineCitation {
  guideline: string;
  section: string;
  relevance: number;
}

export type Citation = PubMedCitation | GuidelineCitation;

// Type guards for citations
export function isPubMedCitation(citation: Citation): citation is PubMedCitation {
  return "pmid" in citation;
}

export function isGuidelineCitation(citation: Citation): citation is GuidelineCitation {
  return "guideline" in citation;
}

// ─── Guardrails ──────────────────────────────────────────────
export type GuardrailStatus = "passed" | "failed" | "warning";

export interface GuardrailsResult {
  hallucination_check: GuardrailStatus;
  safety_check: GuardrailStatus;
  scope_check: GuardrailStatus;
}

// ─── Synthesized Response ────────────────────────────────────
export interface ClinicalResponse {
  recommendation: string;
  confidence_score: number;
  citations: Citation[];
  drug_alerts: DrugAlert[];
  disclaimers: string[];
}

// ─── Clinician Feedback ──────────────────────────────────────
export interface ClinicalFeedback {
  clinician_rating: number | null;
  clinician_correction: string | null;
  rated_at: string | null;
}

// ─── Full Conversation Turn ──────────────────────────────────
export interface ConversationTurn {
  id: string;
  session_id: string;
  patient_id: string;
  turn_number: number;
  timestamp: string;
  clinician_id: string;
  query: {
    text: string;
    intent: string;
    extracted_entities: ExtractedEntity[];
  };
  agent_outputs: AgentOutputs;
  response: ClinicalResponse;
  guardrails: GuardrailsResult;
  feedback: ClinicalFeedback;
  total_latency_ms: number;
  tokens_used: {
    input: number;
    output: number;
    embedding: number;
  };
}

// ─── Streaming Event Types ───────────────────────────────────
export type StreamingEventType =
  | "agent_started"
  | "agent_completed"
  | "agent_error"
  | "synthesis_started"
  | "synthesis_chunk"
  | "synthesis_completed"
  | "guardrails_completed";

export interface StreamingEvent<T = unknown> {
  event_type: StreamingEventType;
  agent?: keyof AgentOutputs;
  data: T;
  timestamp: string;
  trace_id: string;
}

// ─── Agent Names for Type Safety ─────────────────────────────
export const AGENT_NAMES = {
  patient_history: "patient_history",
  literature: "literature",
  protocols: "protocols",
  drug_safety: "drug_safety",
} as const;

export type AgentName = keyof typeof AGENT_NAMES;

// ─── API Request/Response Types ───────────────────────────────
export interface ClinicalQuery {
  session_id: string;
  query: string;
  patient_id: string;
  context?: Record<string, unknown>;
}

export interface QueryResponse {
  query_id: string;
  status: "pending" | "processing" | "completed" | "error";
  clinical_response?: ClinicalResponse;
  error?: string;
}

export interface ApiError {
  code?: string;
  message?: string;
  details?: unknown;
  status?: number;
  status_code?: number;
}
