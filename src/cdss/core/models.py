"""Pydantic domain models for the Clinical Decision Support System.

This module defines every data structure used across the CDSS pipeline:
patient records, clinical queries/responses, agent coordination,
drug safety, literature evidence, and audit logging.
"""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Patient Models
# ═══════════════════════════════════════════════════════════════════════════════


class Demographics(BaseModel):
    """Core demographic information for a patient."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "age": 62,
                    "sex": "male",
                    "weight_kg": 85.0,
                    "height_cm": 175.0,
                    "blood_type": "A+",
                }
            ]
        }
    )

    age: int = Field(..., ge=0, le=150, description="Patient age in years.")
    sex: str = Field(..., description="Biological sex (male, female, other).")
    weight_kg: float = Field(..., gt=0, description="Body weight in kilograms.")
    height_cm: float = Field(..., gt=0, description="Height in centimeters.")
    blood_type: str | None = Field(
        default=None,
        description="ABO/Rh blood type (e.g., 'A+', 'O-').",
    )


class MedicalCondition(BaseModel):
    """A coded medical condition or diagnosis."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "E11.9",
                    "coding_system": "ICD-10",
                    "display": "Type 2 diabetes mellitus without complications",
                    "onset_date": "2019-03-15",
                    "status": "active",
                }
            ]
        }
    )

    code: str = Field(..., description="Condition code (e.g., ICD-10 or SNOMED-CT code).")
    coding_system: Literal["ICD-10", "SNOMED-CT"] = Field(
        ..., description="Coding system used."
    )
    display: str = Field(..., description="Human-readable condition name.")
    onset_date: date | None = Field(
        default=None, description="Date the condition was first diagnosed."
    )
    status: str = Field(
        default="active",
        description="Condition status (active, resolved, remission, etc.).",
    )


class Medication(BaseModel):
    """An active medication with dosing information."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rxcui": "860975",
                    "name": "Metformin 500 mg oral tablet",
                    "dose": "500 mg",
                    "frequency": "twice daily",
                    "start_date": "2020-01-10",
                    "prescriber": "Dr. Smith",
                }
            ]
        }
    )

    rxcui: str = Field(..., description="RxNorm Concept Unique Identifier.")
    name: str = Field(..., description="Medication name with strength.")
    dose: str = Field(..., description="Prescribed dose (e.g., '500 mg').")
    frequency: str = Field(..., description="Dosing frequency (e.g., 'twice daily').")
    start_date: date | None = Field(
        default=None, description="Date the medication was started."
    )
    prescriber: str | None = Field(
        default=None, description="Name of the prescribing clinician."
    )


class Allergy(BaseModel):
    """A recorded allergy or adverse reaction."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "substance": "Penicillin",
                    "reaction": "Anaphylaxis",
                    "severity": "severe",
                    "code": "91936005",
                    "coding_system": "SNOMED-CT",
                }
            ]
        }
    )

    substance: str = Field(..., description="Allergen substance name.")
    reaction: str = Field(..., description="Description of the allergic reaction.")
    severity: Literal["mild", "moderate", "severe"] = Field(
        ..., description="Severity classification."
    )
    code: str | None = Field(
        default=None, description="Coded identifier for the allergen."
    )
    coding_system: str | None = Field(
        default=None, description="Coding system for the allergen code."
    )


class LabResult(BaseModel):
    """A laboratory test result with reference range."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "4548-4",
                    "coding_system": "LOINC",
                    "display": "Hemoglobin A1c",
                    "value": 7.2,
                    "unit": "%",
                    "test_date": "2025-11-01",
                    "reference_range": "4.0-5.6",
                }
            ]
        }
    )

    code: str = Field(..., description="Lab test code (e.g., LOINC code).")
    coding_system: Literal["LOINC"] = Field(
        default="LOINC", description="Coding system for the lab test."
    )
    display: str = Field(..., description="Human-readable lab test name.")
    value: float = Field(..., description="Numeric result value.")
    unit: str = Field(..., description="Unit of measurement (e.g., 'mg/dL', '%').")
    test_date: date = Field(..., description="Date the lab was collected.")
    reference_range: str | None = Field(
        default=None,
        description="Normal reference range (e.g., '4.0-5.6').",
    )


class PatientProfile(BaseModel):
    """Complete patient profile stored in Cosmos DB.

    This is the primary patient document containing demographics,
    active conditions, medications, allergies, and recent lab results.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "prof-001",
                    "patient_id": "P-12345",
                    "doc_type": "patient_profile",
                    "demographics": {
                        "age": 62,
                        "sex": "male",
                        "weight_kg": 85.0,
                        "height_cm": 175.0,
                        "blood_type": "A+",
                    },
                    "active_conditions": [],
                    "active_medications": [],
                    "allergies": [],
                    "recent_labs": [],
                    "patient_embedding": None,
                    "last_updated": "2025-12-01T10:30:00Z",
                }
            ]
        }
    )

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique document ID.",
    )
    patient_id: str = Field(..., description="External patient identifier.")
    doc_type: str = Field(
        default="patient_profile",
        description="Document type discriminator for Cosmos DB.",
    )
    demographics: Demographics = Field(..., description="Patient demographics.")
    active_conditions: list[MedicalCondition] = Field(
        default_factory=list,
        description="Currently active medical conditions.",
    )
    active_medications: list[Medication] = Field(
        default_factory=list,
        description="Currently prescribed medications.",
    )
    allergies: list[Allergy] = Field(
        default_factory=list,
        description="Known allergies and adverse reactions.",
    )
    recent_labs: list[LabResult] = Field(
        default_factory=list,
        description="Recent laboratory results.",
    )
    patient_embedding: list[float] | None = Field(
        default=None,
        description="Embedding vector representing the patient profile for similarity search.",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the last profile update.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Query / Response Models
# ═══════════════════════════════════════════════════════════════════════════════


class ExtractedEntity(BaseModel):
    """A clinical entity extracted from the query text via NER."""

    entity_type: Literal[
        "condition", "medication", "lab_test", "procedure", "anatomical_site"
    ] = Field(..., description="Entity type category.")
    value: str = Field(..., description="Extracted entity text.")
    code: str | None = Field(
        default=None,
        description="Normalized code (ICD-10, RxNorm, LOINC, etc.) if resolved.",
    )


class ClinicalQuery(BaseModel):
    """A clinical question submitted by a clinician."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "What are the recommended treatment options for a 62-year-old male with type 2 diabetes and CKD stage 3?",
                    "patient_id": "P-12345",
                    "session_id": "sess-abc123",
                    "intent": "treatment",
                    "extracted_entities": [
                        {"entity_type": "condition", "value": "type 2 diabetes", "code": "E11.9"},
                        {"entity_type": "condition", "value": "CKD stage 3", "code": "N18.3"},
                    ],
                }
            ]
        }
    )

    text: str = Field(
        ..., min_length=1, description="The clinical question in natural language."
    )
    patient_id: str | None = Field(
        default=None,
        description="Patient ID to load context from the patient profile.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID for conversation continuity.",
    )
    intent: str | None = Field(
        default=None,
        description="Classified intent (diagnosis, treatment, drug_check, general, emergency).",
    )
    extracted_entities: list[ExtractedEntity] | None = Field(
        default=None,
        description="Clinical entities extracted from the query text.",
    )


class Citation(BaseModel):
    """A source citation backing a clinical recommendation."""

    source_type: Literal["pubmed", "guideline", "patient_record", "drug_database"] = (
        Field(..., description="Category of the source.")
    )
    identifier: str = Field(
        ..., description="Unique identifier (PMID, guideline ID, record ID, etc.)."
    )
    title: str = Field(..., description="Title of the cited source.")
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score from retrieval (0.0 to 1.0).",
    )
    url: str | None = Field(
        default=None, description="URL to the source, if available."
    )


class DrugAlert(BaseModel):
    """An alert about a drug interaction or safety concern."""

    severity: Literal["minor", "moderate", "major"] = Field(
        ..., description="Alert severity level."
    )
    description: str = Field(
        ..., description="Human-readable description of the drug alert."
    )
    source: str = Field(
        ..., description="Source of the alert (e.g., 'DrugBank', 'OpenFDA')."
    )
    evidence_level: int = Field(
        ...,
        ge=1,
        le=5,
        description="Evidence level (1=established, 5=theoretical).",
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Suggested alternative medications.",
    )


class AgentOutput(BaseModel):
    """Output from a single specialist agent."""

    agent_name: str = Field(..., description="Name of the agent that produced this output.")
    latency_ms: int = Field(
        ..., ge=0, description="Execution time of the agent in milliseconds."
    )
    sources_retrieved: int = Field(
        ..., ge=0, description="Number of sources retrieved by this agent."
    )
    summary: str = Field(..., description="Agent's summarized findings.")
    raw_data: dict | None = Field(
        default=None,
        description="Raw structured data returned by the agent, if applicable.",
    )


class ClinicalResponse(BaseModel):
    """Complete clinical response returned to the clinician."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment": "Patient presents with uncontrolled type 2 diabetes and stage 3 CKD.",
                    "recommendation": "Consider SGLT2 inhibitor (e.g., dapagliflozin) which provides both glycemic and renal benefits.",
                    "evidence_summary": [
                        "DAPA-CKD trial showed 39% reduction in kidney failure risk.",
                    ],
                    "drug_alerts": [],
                    "confidence_score": 0.87,
                    "citations": [],
                    "disclaimers": [
                        "This is a clinical decision support tool and does not replace clinical judgment.",
                    ],
                    "agent_outputs": {},
                }
            ]
        }
    )

    assessment: str = Field(
        ..., description="Clinical assessment based on the query and patient context."
    )
    recommendation: str = Field(
        ..., description="Evidence-based clinical recommendation."
    )
    evidence_summary: list[str] = Field(
        default_factory=list,
        description="Key evidence points supporting the recommendation.",
    )
    drug_alerts: list[DrugAlert] = Field(
        default_factory=list,
        description="Drug interaction or safety alerts, if any.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score for the recommendation (0.0 to 1.0).",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Sources cited in the response.",
    )
    disclaimers: list[str] = Field(
        default_factory=list,
        description="Required medical disclaimers.",
    )
    agent_outputs: dict[str, AgentOutput] = Field(
        default_factory=dict,
        description="Outputs from each specialist agent, keyed by agent name.",
    )


class GuardrailsResult(BaseModel):
    """Result of the guardrails validation pipeline."""

    is_valid: bool = Field(
        ..., description="Whether the response passed all guardrails checks."
    )
    hallucination_flags: list[str] = Field(
        default_factory=list,
        description="Potential hallucinations detected in the response.",
    )
    safety_concerns: list[str] = Field(
        default_factory=list,
        description="Safety issues identified (e.g., dangerous dosing, contraindications).",
    )
    disclaimers: list[str] = Field(
        default_factory=list,
        description="Disclaimers that must be appended to the response.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Conversation / Audit Models
# ═══════════════════════════════════════════════════════════════════════════════


class ConversationTurn(BaseModel):
    """A single turn in a clinical conversation, stored in Cosmos DB."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique document ID for this conversation turn.",
    )
    session_id: str = Field(
        ..., description="Session ID grouping related conversation turns."
    )
    patient_id: str = Field(
        ..., description="Patient ID associated with this conversation."
    )
    doc_type: str = Field(
        default="conversation_turn",
        description="Document type discriminator for Cosmos DB.",
    )
    turn_number: int = Field(
        ..., ge=1, description="Sequential turn number within the session."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this turn was processed.",
    )
    clinician_id: str = Field(
        ..., description="ID of the clinician who submitted the query."
    )
    query: ClinicalQuery = Field(
        ..., description="The clinical query for this turn."
    )
    agent_outputs: dict[str, AgentOutput] = Field(
        default_factory=dict,
        description="Raw outputs from each specialist agent.",
    )
    response: ClinicalResponse = Field(
        ..., description="The final clinical response generated."
    )
    guardrails: GuardrailsResult = Field(
        ..., description="Guardrails validation result for this turn."
    )
    feedback: dict | None = Field(
        default=None,
        description="Clinician feedback on the response (rating, comments).",
    )
    total_latency_ms: int = Field(
        ..., ge=0, description="Total end-to-end latency in milliseconds."
    )
    tokens_used: dict[str, int] = Field(
        default_factory=dict,
        description="Token usage breakdown (e.g., {'prompt': 1500, 'completion': 800}).",
    )


class AuditLogEntry(BaseModel):
    """HIPAA-compliant audit log entry stored in Cosmos DB.

    Tracks all access to patient data, LLM interactions,
    and system events for regulatory compliance.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "audit-001",
                    "date_partition": "2025-12-01",
                    "event_type": "patient_data_access",
                    "timestamp": "2025-12-01T10:30:00Z",
                    "actor": {"clinician_id": "C-001", "role": "physician"},
                    "action": "read_patient_profile",
                    "resource": {"resource_type": "patient_profile", "id": "P-12345"},
                    "session_id": "sess-abc123",
                    "justification": "Clinical query about treatment options",
                    "outcome": "success",
                    "data_sent_to_llm": True,
                    "phi_fields_sent": ["demographics.age", "active_conditions"],
                    "phi_fields_redacted": ["demographics.name", "demographics.ssn"],
                }
            ]
        }
    )

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique audit log entry ID.",
    )
    date_partition: str = Field(
        ...,
        description="Date partition key for Cosmos DB (format: YYYY-MM-DD).",
    )
    event_type: str = Field(
        ...,
        description="Audit event type (e.g., 'patient_data_access', 'llm_interaction', 'agent_execution').",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the audited event.",
    )
    actor: dict[str, str] = Field(
        ...,
        description="Identity of the actor (clinician_id, role, system component).",
    )
    action: str = Field(
        ...,
        description="Action performed (e.g., 'read_patient_profile', 'generate_response').",
    )
    resource: dict[str, str] = Field(
        ...,
        description="Resource accessed (resource_type, id).",
    )
    session_id: str = Field(
        ..., description="Session ID for correlating related audit events."
    )
    justification: str = Field(
        ..., description="Clinical justification for accessing the data."
    )
    outcome: str = Field(
        ..., description="Outcome of the action (success, failure, denied)."
    )
    data_sent_to_llm: bool = Field(
        ..., description="Whether patient data was sent to the LLM."
    )
    phi_fields_sent: list[str] = Field(
        default_factory=list,
        description="List of PHI fields that were sent to the LLM.",
    )
    phi_fields_redacted: list[str] = Field(
        default_factory=list,
        description="List of PHI fields that were redacted before sending to the LLM.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Models
# ═══════════════════════════════════════════════════════════════════════════════


class AgentTask(BaseModel):
    """Inter-agent communication message for task dispatch and responses."""

    message_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique message identifier.",
    )
    from_agent: str = Field(
        ..., description="Name of the sending agent."
    )
    to_agent: str = Field(
        ..., description="Name of the receiving agent."
    )
    message_type: Literal["task_request", "task_response", "error"] = Field(
        ..., description="Message type."
    )
    payload: dict = Field(
        ..., description="Task payload data (query, parameters, results, or error details)."
    )
    session_id: str = Field(
        ..., description="Session ID for correlating agent interactions."
    )
    trace_id: str = Field(
        ..., description="Distributed trace ID for end-to-end observability."
    )


class QueryPlan(BaseModel):
    """Execution plan generated by the orchestrator for a clinical query.

    Determines which agents to invoke, how to decompose the query,
    and whether agents can run in parallel.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query_type": "treatment",
                    "required_agents": ["patient_context", "literature", "protocol", "drug_safety"],
                    "sub_queries": {
                        "literature": "SGLT2 inhibitors for type 2 diabetes with CKD stage 3",
                        "protocol": "ADA 2024 guidelines for diabetes with renal impairment",
                        "drug_safety": "Check interactions: metformin, lisinopril, dapagliflozin",
                    },
                    "priority": "high",
                    "parallel_dispatch": True,
                }
            ]
        }
    )

    query_type: Literal["diagnosis", "treatment", "drug_check", "general", "emergency"] = Field(
        ..., description="Classified query type driving agent selection."
    )
    required_agents: list[str] = Field(
        ..., description="Ordered list of agent names to invoke."
    )
    sub_queries: dict[str, str] = Field(
        default_factory=dict,
        description="Decomposed sub-queries mapped to target agents.",
    )
    priority: Literal["low", "medium", "high", "critical"] = Field(
        default="medium", description="Query priority level."
    )
    parallel_dispatch: bool = Field(
        default=True,
        description="Whether agents can be dispatched in parallel.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Drug Models
# ═══════════════════════════════════════════════════════════════════════════════


class DrugInteraction(BaseModel):
    """A drug-drug interaction record from safety databases."""

    drug_a: str = Field(..., description="First drug name.")
    drug_b: str = Field(..., description="Second drug name.")
    severity: Literal["minor", "moderate", "major"] = Field(
        ..., description="Interaction severity level."
    )
    description: str = Field(
        ..., description="Clinical description of the interaction."
    )
    evidence_level: int = Field(
        ...,
        ge=1,
        le=5,
        description="Evidence level (1=established, 5=theoretical).",
    )
    source: str = Field(
        ..., description="Source database (DrugBank, OpenFDA, RxNorm)."
    )
    clinical_significance: str | None = Field(
        default=None,
        description="Clinical significance assessment.",
    )


class DrugSafetyReport(BaseModel):
    """Complete drug safety analysis report."""

    interactions: list[DrugInteraction] = Field(
        default_factory=list,
        description="Detected drug-drug interactions.",
    )
    adverse_events: list[dict] = Field(
        default_factory=list,
        description="Known adverse events from FDA reporting data.",
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Suggested alternative medications.",
    )
    dosage_adjustments: list[str] = Field(
        default_factory=list,
        description="Recommended dosage adjustments based on patient factors.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Literature Models
# ═══════════════════════════════════════════════════════════════════════════════


class PubMedArticle(BaseModel):
    """A PubMed article retrieved via NCBI Entrez."""

    pmid: str = Field(..., description="PubMed ID.")
    title: str = Field(..., description="Article title.")
    authors: list[str] = Field(
        default_factory=list, description="List of author names."
    )
    journal: str = Field(..., description="Journal name.")
    publication_date: str = Field(
        ..., description="Publication date (format varies: YYYY, YYYY-MM, YYYY-MM-DD)."
    )
    abstract: str = Field(
        default="", description="Article abstract text."
    )
    mesh_terms: list[str] = Field(
        default_factory=list, description="MeSH descriptor terms."
    )
    doi: str | None = Field(
        default=None, description="Digital Object Identifier."
    )
    pmc_id: str | None = Field(
        default=None, description="PubMed Central ID for full-text access."
    )


class LiteratureEvidence(BaseModel):
    """Aggregated literature evidence from PubMed searches."""

    papers: list[PubMedArticle] = Field(
        default_factory=list,
        description="Retrieved PubMed articles.",
    )
    evidence_level: str = Field(
        ...,
        description="Overall evidence level (e.g., 'Level I - Systematic Review', 'Level III - Case Series').",
    )
    summary: str = Field(
        ..., description="Synthesized summary of the literature evidence."
    )
    contradictions: list[str] = Field(
        default_factory=list,
        description="Contradictory findings across papers.",
    )
    consensus_strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of consensus across retrieved papers (0.0 to 1.0).",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Protocol Models
# ═══════════════════════════════════════════════════════════════════════════════


class ProtocolMatch(BaseModel):
    """A matched clinical protocol or guideline recommendation."""

    guideline_name: str = Field(
        ..., description="Name of the clinical guideline (e.g., 'ADA Standards of Care 2024')."
    )
    version: str = Field(
        ..., description="Guideline version or year."
    )
    recommendation: str = Field(
        ..., description="Specific recommendation text from the guideline."
    )
    evidence_grade: Literal["A", "B", "C", "D", "expert_opinion"] = Field(
        ..., description="Evidence grade assigned by the guideline body."
    )
    specialty: str = Field(
        ..., description="Medical specialty (e.g., 'endocrinology', 'nephrology')."
    )
    contraindications: list[str] = Field(
        default_factory=list,
        description="Known contraindications for this recommendation.",
    )
    last_updated: date = Field(
        ..., description="Date the guideline was last updated."
    )


class PatientContext(BaseModel):
    """Assembled patient context passed to specialist agents.

    This is the unified patient data bundle that agents receive
    alongside the clinical query for context-aware reasoning.
    """

    demographics: Demographics = Field(
        ..., description="Patient demographic information."
    )
    conditions: list[MedicalCondition] = Field(
        default_factory=list, description="Active medical conditions."
    )
    medications: list[Medication] = Field(
        default_factory=list, description="Current medications."
    )
    allergies: list[Allergy] = Field(
        default_factory=list, description="Known allergies."
    )
    recent_labs: list[LabResult] = Field(
        default_factory=list, description="Recent laboratory results."
    )
    timeline_summary: str | None = Field(
        default=None,
        description="Natural language summary of the patient's clinical timeline.",
    )
