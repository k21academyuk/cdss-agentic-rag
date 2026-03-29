// Clinical Decision Support System - TypeScript Types
// Matches backend Pydantic models from cdss.core.models

export interface Demographics {
  age: number;
  sex: string;
  weight_kg: number;
  height_cm: number;
  blood_type?: string;
}

export interface MedicalCondition {
  code: string;
  coding_system: 'ICD-10' | 'SNOMED-CT';
  display: string;
  onset_date?: string;
  status: string;
}

export interface Medication {
  rxcui: string;
  name: string;
  dose: string;
  frequency: string;
  start_date?: string;
  prescriber?: string;
}

export interface Allergy {
  substance: string;
  reaction: string;
  severity: 'mild' | 'moderate' | 'severe';
  code?: string;
  coding_system?: string;
}

export interface LabResult {
  code: string;
  coding_system: 'LOINC';
  display: string;
  value: number;
  unit: string;
  test_date: string;
  reference_range?: string;
}

export interface PatientProfile {
  id: string;
  patient_id: string;
  doc_type: string;
  demographics: Demographics;
  active_conditions: MedicalCondition[];
  active_medications: Medication[];
  allergies: Allergy[];
  recent_labs: LabResult[];
  patient_embedding?: number[];
  last_updated: string;
}

export interface ExtractedEntity {
  entity_type: 'condition' | 'medication' | 'lab_test' | 'procedure' | 'anatomical_site';
  value: string;
  code?: string;
}

export interface ClinicalQuery {
  text: string;
  patient_id?: string;
  session_id?: string;
  intent?: string;
  extracted_entities?: ExtractedEntity[];
}

export interface Citation {
  source_type: 'pubmed' | 'guideline' | 'patient_record' | 'drug_database';
  identifier: string;
  title: string;
  relevance_score: number;
  url?: string;
}

export interface DrugAlert {
  id?: string;
  severity: 'minor' | 'moderate' | 'major';
  description: string;
  source: string;
  evidence_level: number;
  clinical_significance?: string;
  alternatives: string[];
}

export interface AgentOutput {
  agent_name: string;
  latency_ms: number;
  sources_retrieved: number;
  summary: string;
  raw_data?: Record<string, unknown>;
}

export interface ClinicalResponse {
  assessment: string;
  recommendation: string;
  evidence_summary: string[];
  evidence?: {
    level: string;
    sources: string[];
    confidence: number;
  };
  drug_alerts: DrugAlert[];
  confidence_score: number;
  citations: Citation[];
  disclaimers: string[];
  agent_outputs: Record<string, AgentOutput>;
}

export interface QueryPlan {
  query_type: 'diagnosis' | 'treatment' | 'drug_check' | 'general' | 'emergency';
  required_agents: string[];
  sub_queries: Record<string, string>;
  priority: 'low' | 'medium' | 'high' | 'critical';
  parallel_dispatch: boolean;
}

export interface DrugInteraction {
  drug_a: string;
  drug_b: string;
  severity: 'minor' | 'moderate' | 'major';
  description: string;
  evidence_level: number;
  source: string;
  clinical_significance?: string;
}

export interface DrugSafetyReport {
  interactions: DrugInteraction[];
  adverse_events: Record<string, unknown>[];
  alternatives: string[];
  dosage_adjustments: string[];
}

export interface PubMedArticle {
  pmid: string;
  title: string;
  authors: string[];
  journal: string;
  publication_date: string;
  abstract: string;
  mesh_terms: string[];
  doi?: string;
  pmc_id?: string;
  // Optional relevance score used by search results
  relevance_score?: number;
}

export interface LiteratureEvidence {
  papers: PubMedArticle[];
  evidence_level: string;
  summary: string;
  contradictions: string[];
  consensus_strength: number;
}

export interface ProtocolMatch {
  guideline_name: string;
  version: string;
  recommendation: string;
  evidence_grade: 'A' | 'B' | 'C' | 'D' | 'expert_opinion';
  specialty: string;
  contraindications: string[];
  last_updated: string;
}

export interface AuditLogEntry {
  id: string;
  date_partition?: string;
  event_type?: string;
  type?: string;
  timestamp: string;
  actor?: Record<string, string>;
  action?: string;
  resource?: Record<string, string>;
  session_id?: string;
  justification?: string;
  outcome?: string;
  data_sent_to_llm?: boolean;
  phi_fields_sent?: string[];
  phi_fields_redacted?: string[];
  details?: Record<string, unknown>;
  patient_id?: string;
}

// API Response Types
export interface SearchLiteratureResponse {
  papers: PubMedArticle[];
  total: number;
  query: string;
  max_results: number;
}

export interface SearchProtocolsResponse {
  matches: ProtocolMatch[];
  total: number;
  query: string;
}

export interface DrugInteractionsResponse {
  interactions: DrugInteraction[];
  alternatives: string[];
  dosage_adjustments: string[];
  patient_context?: {
    conditions: string[];
    medications: string[];
  };
}

export interface QueryResponse {
  query_id: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  clinical_response?: ClinicalResponse;
  error?: string;
}

export interface StreamingQueryUpdate {
  type: 'agent_start' | 'agent_progress' | 'agent_complete' | 'synthesis_start' | 'synthesis_complete' | 'validation_start' | 'validation_complete' | 'error';
  agent?: string;
  progress?: number;
  message?: string;
  response?: ClinicalResponse;
}

export interface PatientListResponse {
  patients: PatientProfile[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentIngestResponse {
  document_id: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  message: string;
  estimated_completion_seconds?: number;
  chunks_count?: number;
}

export interface DocumentIngestionStatusResponse {
  document_id: string;
  filename?: string;
  document_type?: string;
  patient_id?: string | null;
  status: 'queued' | 'pending' | 'processing' | 'completed' | 'failed' | 'error' | 'not_found';
  progress: number;
  created_at?: string;
  updated_at?: string;
  error?: string | null;
  message?: string;
}

export interface DocumentSearchVerificationRequest {
  phrase?: string;
  top?: number;
}

export interface DocumentGroundedPreviewRequest {
  question: string;
  top?: number;
  timeout_seconds?: number;
  max_tokens?: number;
  use_cache?: boolean;
}

export interface DocumentSearchVerificationHit {
  id: string;
  chunk_index?: number;
  content_preview?: string;
  score?: number;
}

export interface DocumentSearchVerificationResponse {
  document_id: string;
  pipeline_document_id: string;
  document_type: string;
  normalized_document_type: string;
  workspace_target: string;
  logical_index_name: string;
  physical_index_name: string;
  indexed_chunks_count: number;
  indexed_chunks: DocumentSearchVerificationHit[];
  phrase?: string;
  phrase_hits_count: number;
  phrase_hits: DocumentSearchVerificationHit[];
}

export interface GroundedPreviewCitation {
  chunk_id: string;
  chunk_index?: number;
  quote: string;
  score?: number;
  content_preview?: string;
}

export interface DocumentGroundedPreviewResponse {
  document_id: string;
  pipeline_document_id: string;
  normalized_document_type: string;
  workspace_target: string;
  logical_index_name: string;
  physical_index_name: string;
  question: string;
  retrieved_chunks_count: number;
  status: "ok" | "no_supporting_evidence";
  answer: string;
  confidence: number;
  citations: GroundedPreviewCitation[];
  cached: boolean;
}

export interface DocumentDeleteResponse {
  document_id: string;
  pipeline_document_id: string;
  normalized_document_type: string;
  logical_index_name: string;
  physical_index_name: string;
  deleted_chunks_count: number;
  status: "deleted";
}

export interface HealthCheckResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  services: Record<string, 'healthy' | 'degraded' | 'unhealthy'>;
  timestamp: string;
}

// Generic API error object used across API clients
export interface ApiError {
  code?: string;
  message?: string;
  details?: unknown;
  status?: number;
  status_code?: number;
}

// User representation used in auth/store layers
export interface User {
  id: string;
  username?: string;
  name?: string;
  email?: string;
  roles?: string[];
  [key: string]: unknown;
}

// ============================================================================
// PubMed Article - for Literature Search
// =================================================================

// (Removed duplicate PubMedArticle definition to avoid declaration conflicts.)

export interface LiteratureSearchResponse {
  papers: PubMedArticle[];
  total: number;
  page: number;
  page_size: number;
}

export interface LiteratureSearchRequest {
  query: string;
  max_results?: number;
  date_range?: { start: string; end: string };
  article_types?: string[];
}

export interface ProtocolSearchRequest {
  query: string;
  specialty?: string;
  max_results?: number;
}

export interface protocolSearchResponse {
  protocols: ProtocolMatch[];
  total: number;
  page: number;
  page_size: number;
}

// ============================================================================
// Drug Interaction Response types
// =================================================================
export interface MedicationInput {
  name: string;
  rxcui?: string;
  dose: string;
  frequency: string;
}

export interface DrugInteractionCheckRequest {
  medications: MedicationInput[];
  patient_id?: string;
}

export interface DrugInteractionCheckResponse {
  interactions: DrugInteraction[];
  adverse_events: Record<string, unknown>[];
  alternatives: string[];
  dosage_adjustments: string[];
}

// ============================================================================
// Document Inyestion response
// =================================================================
export interface DocumentIngestRequest {
  file: File;
  document_type: string;
  metadata?: Record<string, unknown>;
}

export interface DocumentIngestResponse {
  document_id: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  message: string;
  estimated_completion_seconds?: number;
  chunks_count?: number;
}

// ============================================================================
// System Health Check
// ============================================================================
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency_ms: number;
  last_check: string;
}
