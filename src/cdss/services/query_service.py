"""Service layer for processing clinical queries.

Sits between the FastAPI routes and the OrchestratorAgent, providing a
clean interface for query processing, conversation management, feedback
submission, and patient profile retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from cdss.agents.drug_safety import DrugSafetyAgent
from cdss.agents.guardrails import GuardrailsAgent
from cdss.agents.medical_literature import MedicalLiteratureAgent
from cdss.agents.orchestrator import OrchestratorAgent
from cdss.agents.patient_history import PatientHistoryAgent
from cdss.agents.protocol_agent import ProtocolAgent
from cdss.clients.blob_storage_client import BlobStorageClient
from cdss.clients.document_intelligence_client import DocumentIntelligenceClient
from cdss.clients.search_client import AzureSearchClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError, ValidationError
from cdss.core.logging import get_logger
from cdss.core.models import ClinicalQuery, ClinicalResponse
from cdss.ingestion.pipeline import DocumentIngestionPipeline
from cdss.services.ingestion_service import DocumentIngestionService

logger = get_logger(__name__)


class ClinicalQueryService:
    """Service layer for processing clinical queries.

    Encapsulates orchestrator invocation, conversation history retrieval,
    clinician feedback, and patient profile access.  The service is the
    single point of contact for all API route handlers.

    Attributes:
        orchestrator: The orchestrator agent responsible for query processing.
        cosmos_client: The Cosmos DB client for data persistence.
        settings: Application settings.
    """

    def __init__(
        self,
        orchestrator: OrchestratorAgent | None = None,
        cosmos_client: object | None = None,
        ingestion_service: DocumentIngestionService | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the query service.

        If an orchestrator is not provided, a default instance is created.
        The Cosmos DB client is either explicitly provided, obtained from
        the orchestrator, or lazily initialized from settings.

        Args:
            orchestrator: Pre-configured orchestrator agent.
            cosmos_client: Pre-configured Cosmos DB client.
            settings: Application settings instance.
        """
        self.settings = settings or get_settings()

        if orchestrator is not None:
            self.orchestrator = orchestrator
        else:
            self.orchestrator = self._build_default_orchestrator()

        if cosmos_client is not None:
            self.cosmos_client = cosmos_client
        elif hasattr(self.orchestrator, "cosmos_client"):
            self.cosmos_client = self.orchestrator.cosmos_client
        else:
            self.cosmos_client = None

        self.ingestion_service = ingestion_service or self._build_default_ingestion_service()

        logger.info("ClinicalQueryService initialized")

    def _build_default_orchestrator(self) -> OrchestratorAgent:
        """Build an orchestrator with concrete specialist agents.

        Each specialist is initialized independently so a single failing
        dependency does not prevent the service from starting.
        """
        patient_history_agent = self._safe_create_agent(
            "patient_history",
            lambda: PatientHistoryAgent(settings=self.settings),
        )
        literature_agent = self._safe_create_agent(
            "literature",
            lambda: MedicalLiteratureAgent(settings=self.settings),
        )
        protocol_agent = self._safe_create_agent(
            "protocol",
            lambda: ProtocolAgent(settings=self.settings),
        )
        drug_safety_agent = self._safe_create_agent(
            "drug_safety",
            lambda: DrugSafetyAgent(settings=self.settings),
        )
        guardrails_agent = self._safe_create_agent(
            "guardrails",
            lambda: GuardrailsAgent(settings=self.settings),
        )

        return OrchestratorAgent(
            patient_history_agent=patient_history_agent,
            literature_agent=literature_agent,
            protocol_agent=protocol_agent,
            drug_safety_agent=drug_safety_agent,
            guardrails_agent=guardrails_agent,
            settings=self.settings,
        )

    def _safe_create_agent(
        self,
        agent_name: str,
        factory: Callable[[], Any],
    ) -> object | None:
        """Create an agent and degrade gracefully if dependencies are unavailable."""
        try:
            return factory()
        except Exception as exc:
            logger.warning(
                "Failed to initialize specialist agent; continuing without it",
                extra={"agent": agent_name, "error": str(exc)},
            )
            return None

    def _build_default_ingestion_service(self) -> DocumentIngestionService:
        """Build ingestion service with concrete Azure-backed clients when available."""
        search_client: AzureSearchClient | None = None
        blob_client: BlobStorageClient | None = None
        doc_intel_client: DocumentIntelligenceClient | None = None
        embedding_service: Any | None = None

        try:
            search_client = AzureSearchClient(settings=self.settings)
        except Exception as exc:
            logger.warning(
                "Failed to initialize ingestion search client; ingestion indexing will run in fallback mode",
                extra={"error": str(exc)},
            )

        try:
            blob_client = BlobStorageClient(settings=self.settings)
        except Exception as exc:
            logger.warning(
                "Failed to initialize ingestion blob client; blob upload will run in fallback mode",
                extra={"error": str(exc)},
            )

        try:
            doc_intel_client = DocumentIntelligenceClient(settings=self.settings)
        except Exception as exc:
            logger.warning(
                "Failed to initialize ingestion document intelligence client; OCR will run in fallback mode",
                extra={"error": str(exc)},
            )

        # Reuse orchestrator OpenAI client for embeddings when available.
        embedding_service = getattr(self.orchestrator, "openai_client", None)

        pipeline_settings = {
            "search_index": self.settings.azure_search_patient_records_index,
            "protocols_index": self.settings.azure_search_treatment_protocols_index,
            "literature_index": self.settings.azure_search_medical_literature_index,
            "cosmos_database": self.settings.azure_cosmos_database_name,
            "cosmos_embeddings_container": self.settings.azure_cosmos_embedding_cache_container,
            "embedding_model": self.settings.azure_openai_embedding_deployment,
            "embedding_dimensions": 3072,
        }

        pipeline = DocumentIngestionPipeline(
            doc_intelligence_client=doc_intel_client,
            blob_client=blob_client,
            search_client=search_client,
            cosmos_client=self.cosmos_client,
            embedding_service=embedding_service,
            settings=pipeline_settings,
        )
        return DocumentIngestionService(
            pipeline=pipeline,
            settings=self.settings,
        )

    # ------------------------------------------------------------------
    # Query processing
    # ------------------------------------------------------------------

    async def process_query(
        self,
        query_text: str,
        patient_id: str | None = None,
        session_id: str | None = None,
        clinician_id: str = "system",
    ) -> ClinicalResponse:
        """Process a clinical query and return an evidence-based response.

        Creates a ``ClinicalQuery`` model from the raw inputs and delegates
        processing to the orchestrator agent.

        Args:
            query_text: The clinical question in natural language.
            patient_id: Optional patient identifier for context enrichment.
            session_id: Optional session identifier for conversation continuity.
                A new session ID is generated when not provided.
            clinician_id: Identifier of the clinician submitting the query.

        Returns:
            A ``ClinicalResponse`` containing the assessment, recommendation,
            evidence summary, drug alerts, citations, and disclaimers.

        Raises:
            ValidationError: If the query text is empty or invalid.
            CDSSError: If query processing fails.
        """
        # Validate input
        if not query_text or not query_text.strip():
            raise ValidationError(
                message="Query text must not be empty.",
                field_errors={"query_text": "This field is required and must not be blank."},
            )

        effective_session_id = session_id or str(uuid4())

        query = ClinicalQuery(
            text=query_text.strip(),
            patient_id=patient_id,
            session_id=effective_session_id,
        )

        logger.info(
            "Processing clinical query via service",
            extra={
                "query_text_length": len(query_text),
                "patient_id": patient_id,
                "session_id": effective_session_id,
                "clinician_id": clinician_id,
            },
        )

        response = await self.orchestrator.process_query(
            query=query,
            clinician_id=clinician_id,
        )

        return response

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """Retrieve conversation history for a given session.

        Args:
            session_id: The session identifier.
            limit: Maximum number of conversation turns to return.

        Returns:
            A list of conversation turn dictionaries ordered by timestamp
            descending (most recent first).

        Raises:
            ValidationError: If the session_id is empty.
            AzureServiceError: If the Cosmos DB query fails.
        """
        if not session_id or not session_id.strip():
            raise ValidationError(
                message="Session ID must not be empty.",
                field_errors={"session_id": "This field is required."},
            )

        if self.cosmos_client is None:
            logger.warning("Cosmos DB client not available; returning empty conversation history")
            return []

        logger.debug(
            "Fetching conversation history",
            extra={"session_id": session_id, "limit": limit},
        )

        history = await self.cosmos_client.get_conversation_history(
            session_id=session_id,
            limit=limit,
        )

        logger.info(
            "Conversation history retrieved",
            extra={"session_id": session_id, "turns_count": len(history)},
        )

        return history

    async def search_patients(
        self,
        search: str | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> dict:
        """Search patient profiles with optional text filtering and pagination."""
        if page < 1:
            raise ValidationError(
                message="Page must be greater than or equal to 1.",
                field_errors={"page": "Minimum value is 1."},
            )
        if limit < 1:
            raise ValidationError(
                message="Limit must be greater than or equal to 1.",
                field_errors={"limit": "Minimum value is 1."},
            )

        if self.cosmos_client is None:
            logger.warning("Cosmos DB client not available; returning empty patient search results")
            return {
                "patients": [],
                "page": page,
                "page_size": limit,
                "limit": limit,
                "total": 0,
            }

        if not hasattr(self.cosmos_client, "search_patient_profiles"):
            logger.warning("Cosmos client does not implement search_patient_profiles; returning empty results")
            return {
                "patients": [],
                "page": page,
                "page_size": limit,
                "limit": limit,
                "total": 0,
            }

        profiles = await self.cosmos_client.search_patient_profiles(
            search=search,
            limit=max(limit * page, limit),
        )

        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paged_profiles = profiles[start_idx:end_idx]
        normalized_profiles = [self._normalize_patient_profile(profile) for profile in paged_profiles]

        return {
            "patients": normalized_profiles,
            "page": page,
            "page_size": limit,
            "limit": limit,
            "total": len(profiles),
        }

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def submit_feedback(
        self,
        conversation_id: str,
        rating: int,
        correction: str | None = None,
    ) -> dict:
        """Submit clinician feedback on a clinical response.

        Feedback is stored as an update to the corresponding conversation
        turn document in Cosmos DB and also recorded as an audit event.

        Args:
            conversation_id: The conversation turn document ID.
            rating: Clinician rating from 1 (poor) to 5 (excellent).
            correction: Optional free-text correction or comment.

        Returns:
            A dictionary confirming the feedback submission with keys:
            ``conversation_id``, ``rating``, ``status``.

        Raises:
            ValidationError: If the rating is out of range or ID is empty.
            AzureServiceError: If the Cosmos DB write fails.
        """
        if not conversation_id or not conversation_id.strip():
            raise ValidationError(
                message="Conversation ID must not be empty.",
                field_errors={"conversation_id": "This field is required."},
            )

        if not (1 <= rating <= 5):
            raise ValidationError(
                message="Rating must be between 1 and 5.",
                field_errors={"rating": "Value must be between 1 and 5 inclusive."},
            )

        if self.cosmos_client is None:
            logger.warning("Cosmos DB client not available; feedback cannot be saved")
            return {
                "conversation_id": conversation_id,
                "rating": rating,
                "status": "not_saved",
                "reason": "Persistence layer unavailable",
            }

        feedback_data = {
            "rating": rating,
            "correction": correction,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Log as audit event
        try:
            audit_event = {
                "id": str(uuid4()),
                "event_type": "feedback_submission",
                "action": "submit_feedback",
                "conversation_id": conversation_id,
                "rating": rating,
                "has_correction": correction is not None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self.cosmos_client.log_audit_event(audit_event)
        except Exception as exc:
            logger.warning(
                "Failed to log feedback audit event",
                extra={"error": str(exc)},
            )

        logger.info(
            "Clinician feedback submitted",
            extra={
                "conversation_id": conversation_id,
                "rating": rating,
                "has_correction": correction is not None,
            },
        )

        return {
            "conversation_id": conversation_id,
            "rating": rating,
            "status": "saved",
            "feedback": feedback_data,
        }

    # ------------------------------------------------------------------
    # Patient profile
    # ------------------------------------------------------------------

    async def get_patient_profile(self, patient_id: str) -> dict | None:
        """Retrieve a patient profile from Cosmos DB.

        Args:
            patient_id: The unique patient identifier.

        Returns:
            The patient profile dictionary, or ``None`` if the patient is
            not found.

        Raises:
            ValidationError: If the patient_id is empty.
            AzureServiceError: If the Cosmos DB read fails.
        """
        if not patient_id or not patient_id.strip():
            raise ValidationError(
                message="Patient ID must not be empty.",
                field_errors={"patient_id": "This field is required."},
            )

        if self.cosmos_client is None:
            logger.warning("Cosmos DB client not available; cannot retrieve patient profile")
            return None

        logger.debug(
            "Fetching patient profile",
            extra={"patient_id": patient_id},
        )

        profile = await self.cosmos_client.get_patient_profile(patient_id)

        if profile is not None:
            profile = self._normalize_patient_profile(profile)
            logger.info(
                "Patient profile retrieved",
                extra={"patient_id": patient_id},
            )
        else:
            logger.info(
                "Patient profile not found",
                extra={"patient_id": patient_id},
            )

        return profile

    @staticmethod
    def _normalize_patient_profile(profile: dict[str, Any]) -> dict[str, Any]:
        """Normalize legacy patient document variants to the canonical API shape."""
        if not isinstance(profile, dict):
            return profile

        def _normalize_demographics(data: dict[str, Any]) -> dict[str, Any]:
            demographics = data.get("demographics")
            demographics = demographics if isinstance(demographics, dict) else {}

            vital_signs = data.get("vital_signs")
            vital_signs = vital_signs if isinstance(vital_signs, dict) else {}

            weight_kg = demographics.get("weight_kg")
            if weight_kg is None:
                weight_obj = vital_signs.get("weight")
                if isinstance(weight_obj, dict):
                    weight_kg = weight_obj.get("value")

            height_cm = demographics.get("height_cm")
            if height_cm is None:
                height_obj = vital_signs.get("height")
                if isinstance(height_obj, dict):
                    height_cm = height_obj.get("value")

            return {
                "age": demographics.get("age", 0),
                "sex": demographics.get("sex", "unknown"),
                "weight_kg": weight_kg if weight_kg is not None else 0,
                "height_cm": height_cm if height_cm is not None else 0,
                "blood_type": demographics.get("blood_type"),
            }

        def _normalize_conditions(data: dict[str, Any]) -> list[dict[str, Any]]:
            canonical = data.get("active_conditions")
            if isinstance(canonical, list):
                return [c for c in canonical if isinstance(c, dict)]

            legacy = data.get("conditions")
            if not isinstance(legacy, list):
                return []

            normalized: list[dict[str, Any]] = []
            for condition in legacy:
                if isinstance(condition, str):
                    normalized.append(
                        {
                            "code": "unknown",
                            "coding_system": "ICD-10",
                            "display": condition,
                            "onset_date": None,
                            "status": "active",
                        }
                    )
                    continue
                if not isinstance(condition, dict):
                    continue
                icd_code = condition.get("icd10_code")
                snomed_code = condition.get("snomed_ct_code")
                code = condition.get("code") or icd_code or snomed_code or "unknown"
                coding_system = "ICD-10" if icd_code else "SNOMED-CT"
                normalized.append(
                    {
                        "code": code,
                        "coding_system": condition.get("coding_system", coding_system),
                        "display": condition.get("display")
                        or condition.get("description")
                        or condition.get("snomed_ct_display")
                        or "Unknown condition",
                        "onset_date": condition.get("onset_date"),
                        "status": condition.get("status") or condition.get("clinical_status") or "active",
                    }
                )
            return normalized

        def _normalize_medications(data: dict[str, Any]) -> list[dict[str, Any]]:
            canonical = data.get("active_medications")
            if isinstance(canonical, list):
                return [m for m in canonical if isinstance(m, dict)]

            legacy = data.get("medications")
            if not isinstance(legacy, list):
                return []

            normalized: list[dict[str, Any]] = []
            for medication in legacy:
                if isinstance(medication, str):
                    normalized.append(
                        {
                            "rxcui": "unknown",
                            "name": medication,
                            "dose": "unknown",
                            "frequency": "unknown",
                            "start_date": None,
                            "prescriber": None,
                        }
                    )
                    continue
                if not isinstance(medication, dict):
                    continue
                dose = medication.get("dose")
                dose_unit = medication.get("dose_unit")
                if isinstance(dose, str) and dose_unit and dose_unit not in dose:
                    dose = f"{dose} {dose_unit}"
                normalized.append(
                    {
                        "rxcui": str(
                            medication.get("rxcui")
                            or medication.get("rxnorm_cui")
                            or medication.get("rxnorm")
                            or "unknown"
                        ),
                        "name": medication.get("name") or medication.get("generic_name") or "Unknown medication",
                        "dose": dose or "unknown",
                        "frequency": medication.get("frequency_display")
                        or medication.get("frequency")
                        or "unknown",
                        "start_date": medication.get("start_date"),
                        "prescriber": medication.get("prescriber"),
                    }
                )
            return normalized

        def _normalize_allergies(data: dict[str, Any]) -> list[dict[str, Any]]:
            allergies = data.get("allergies")
            if not isinstance(allergies, list):
                return []

            normalized: list[dict[str, Any]] = []
            for allergy in allergies:
                if isinstance(allergy, str):
                    normalized.append(
                        {
                            "substance": allergy,
                            "reaction": "Unknown reaction",
                            "severity": "mild",
                        }
                    )
                    continue

                if not isinstance(allergy, dict):
                    continue

                reactions = allergy.get("reactions")
                reactions = reactions if isinstance(reactions, list) else []
                first_reaction = reactions[0] if reactions and isinstance(reactions[0], dict) else {}
                severity = (
                    allergy.get("severity")
                    or first_reaction.get("severity")
                    or allergy.get("criticality")
                    or "mild"
                )
                if severity == "high":
                    severity = "severe"
                elif severity == "low":
                    severity = "mild"
                if severity not in {"mild", "moderate", "severe"}:
                    severity = "mild"

                normalized.append(
                    {
                        "substance": allergy.get("substance") or "Unknown substance",
                        "reaction": allergy.get("reaction")
                        or first_reaction.get("manifestation")
                        or "Unknown reaction",
                        "severity": severity,
                        "code": allergy.get("code") or allergy.get("snomed_ct_code"),
                        "coding_system": allergy.get("coding_system")
                        or ("SNOMED-CT" if allergy.get("snomed_ct_code") else None),
                    }
                )
            return normalized

        def _normalize_labs(data: dict[str, Any]) -> list[dict[str, Any]]:
            canonical = data.get("recent_labs")
            if isinstance(canonical, list):
                return [lab for lab in canonical if isinstance(lab, dict)]

            legacy = data.get("lab_results")
            if isinstance(legacy, dict):
                normalized_from_map: list[dict[str, Any]] = []
                for key, value in legacy.items():
                    parsed_value: float = 0
                    if isinstance(value, (int, float)):
                        parsed_value = float(value)
                    elif isinstance(value, str):
                        try:
                            parsed_value = float(value)
                        except ValueError:
                            parsed_value = 0
                    normalized_from_map.append(
                        {
                            "code": "unknown",
                            "coding_system": "LOINC",
                            "display": str(key),
                            "value": parsed_value,
                            "unit": "",
                            "test_date": last_updated,
                            "reference_range": None,
                        }
                    )
                return normalized_from_map

            if not isinstance(legacy, list):
                # Older seed payloads used "labs" as a simple key/value map.
                legacy_map = data.get("labs")
                if not isinstance(legacy_map, dict):
                    return []

                normalized_from_legacy_map: list[dict[str, Any]] = []
                for key, value in legacy_map.items():
                    parsed_value: float = 0
                    if isinstance(value, (int, float)):
                        parsed_value = float(value)
                    elif isinstance(value, str):
                        try:
                            parsed_value = float(value)
                        except ValueError:
                            parsed_value = 0

                    normalized_from_legacy_map.append(
                        {
                            "code": "unknown",
                            "coding_system": "LOINC",
                            "display": str(key).upper(),
                            "value": parsed_value,
                            "unit": "",
                            "test_date": last_updated,
                            "reference_range": None,
                        }
                    )
                return normalized_from_legacy_map

            normalized: list[dict[str, Any]] = []
            for lab in legacy:
                if not isinstance(lab, dict):
                    continue
                reference = lab.get("reference_range")
                if isinstance(reference, dict):
                    reference = reference.get("text")
                normalized.append(
                    {
                        "code": lab.get("code") or lab.get("loinc_code") or "unknown",
                        "coding_system": lab.get("coding_system") or "LOINC",
                        "display": lab.get("display") or lab.get("test_name") or "Unknown lab",
                        "value": lab.get("value", 0),
                        "unit": lab.get("unit", ""),
                        "test_date": lab.get("test_date") or lab.get("effective_date"),
                        "reference_range": reference if isinstance(reference, str) else None,
                    }
                )
            return normalized

        last_updated = (
            profile.get("last_updated")
            or profile.get("updated_at")
            or profile.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        )

        return {
            **profile,
            "id": profile.get("id") or profile.get("patient_id"),
            "patient_id": profile.get("patient_id") or profile.get("id"),
            "doc_type": profile.get("doc_type", "patient_profile"),
            "demographics": _normalize_demographics(profile),
            "active_conditions": _normalize_conditions(profile),
            "active_medications": _normalize_medications(profile),
            "allergies": _normalize_allergies(profile),
            "recent_labs": _normalize_labs(profile),
            "last_updated": last_updated,
        }

    async def update_patient_profile(
        self,
        patient_id: str,
        profile_data: dict,
    ) -> dict:
        """Create or update a patient profile in Cosmos DB.

        Args:
            patient_id: The unique patient identifier.
            profile_data: Dictionary containing the profile fields to upsert.

        Returns:
            The upserted patient profile dictionary.

        Raises:
            ValidationError: If the patient_id is empty.
            AzureServiceError: If the Cosmos DB upsert fails.
        """
        if not patient_id or not patient_id.strip():
            raise ValidationError(
                message="Patient ID must not be empty.",
                field_errors={"patient_id": "This field is required."},
            )

        if self.cosmos_client is None:
            raise AzureServiceError("Cosmos DB client is not available. Cannot update patient profile.")

        # Ensure the profile contains the required identifiers
        profile_data["patient_id"] = patient_id
        if "id" not in profile_data:
            profile_data["id"] = patient_id

        logger.info(
            "Updating patient profile",
            extra={"patient_id": patient_id},
        )

        result = await self.cosmos_client.upsert_patient_profile(profile_data)

        logger.info(
            "Patient profile updated",
            extra={"patient_id": patient_id},
        )

        return result
