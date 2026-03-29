"""FastAPI route definitions for the Clinical Decision Support System.

Defines all HTTP endpoints grouped by domain: clinical queries, patients,
conversations, document ingestion, drug safety, search, and admin/health.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cdss.agents.drug_safety import DrugSafetyAgent
from cdss.clients.search_client import (
    INDEX_MEDICAL_LITERATURE,
    INDEX_PATIENT_RECORDS,
    INDEX_TREATMENT_PROTOCOLS,
    AzureSearchClient,
)
from cdss.core.exceptions import (
    AzureServiceError,
    CDSSError,
    DrugSafetyError,
    ValidationError,
)
from cdss.core.logging import get_logger
from cdss.core.models import AgentTask, ClinicalResponse
from cdss.services.query_service import ClinicalQueryService

logger = get_logger(__name__)


# ==========================================================================
# Request / Response Models
# ==========================================================================


class ClinicalQueryRequest(BaseModel):
    """Request body for submitting a clinical query."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The clinical question in natural language.",
    )
    patient_id: str | None = Field(
        default=None,
        description="Optional patient identifier for context enrichment.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for conversation continuity.",
    )


class FeedbackRequest(BaseModel):
    """Request body for submitting clinician feedback."""

    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Clinician rating from 1 (poor) to 5 (excellent).",
    )
    correction: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional free-text correction or comment.",
    )


class MedicationNameRequest(BaseModel):
    """Medication input payload supporting name-only objects."""

    name: str = Field(..., min_length=1, description="Medication display name.")
    rxcui: str | None = Field(default=None, description="Optional RxNorm CUI.")


class DrugInteractionRequest(BaseModel):
    """Request body for checking drug interactions."""

    medications: list[str | MedicationNameRequest] = Field(
        ...,
        min_length=1,
        description="List of current medication names.",
    )
    proposed_medications: list[str | MedicationNameRequest] | None = Field(
        default=None,
        description="Optional list of proposed new medications to check against.",
    )


class LiteratureSearchRequest(BaseModel):
    """Request body for searching medical literature."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Search query for medical literature.",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of results to return.",
    )
    date_from: str | None = Field(
        default=None,
        description="Optional start date filter (YYYY/MM/DD format).",
    )
    date_range: dict[str, str] | None = Field(
        default=None,
        description="Optional date range filter with start/end ISO dates.",
    )
    article_types: list[str] | None = Field(
        default=None,
        description="Optional article type filters.",
    )


class ProtocolSearchRequest(BaseModel):
    """Request body for searching clinical protocols."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Search query for clinical protocols and guidelines.",
    )
    specialty: str | None = Field(
        default=None,
        description="Optional medical specialty filter.",
    )
    evidence_grade: str | None = Field(
        default=None,
        description="Optional evidence grade filter (A, B, C, D, expert_opinion).",
    )


class DocumentVerificationRequest(BaseModel):
    """Request body for document index and retrieval verification."""

    phrase: str | None = Field(
        default=None,
        max_length=500,
        description="Optional phrase to verify retrieval from the indexed chunks.",
    )
    top: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of matching chunks to return.",
    )


class DocumentGroundedPreviewRequest(BaseModel):
    """Request body for grounded answer preview from indexed chunks."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Clinical question to answer using retrieved chunks.",
    )
    top: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of chunks to retrieve for grounding.",
    )
    timeout_seconds: int = Field(
        default=25,
        ge=5,
        le=90,
        description="Timeout for grounded answer generation.",
    )
    max_tokens: int = Field(
        default=700,
        ge=128,
        le=2000,
        description="Token cap for grounded answer generation.",
    )
    use_cache: bool = Field(
        default=True,
        description="When true, return a cached response for identical inputs when available.",
    )


# ==========================================================================
# Dependency injection
# ==========================================================================

# Singleton service instance, initialized in the application lifespan.
_query_service_instance: ClinicalQueryService | None = None


def set_query_service(service: ClinicalQueryService) -> None:
    """Set the module-level query service singleton.

    Called during application startup to inject the fully configured service.

    Args:
        service: The configured ClinicalQueryService instance.
    """
    global _query_service_instance
    _query_service_instance = service


def get_query_service() -> ClinicalQueryService:
    """FastAPI dependency that returns the query service singleton.

    Returns:
        The configured ClinicalQueryService instance.

    Raises:
        HTTPException: If the service has not been initialized.
    """
    if _query_service_instance is None:
        raise HTTPException(
            status_code=503,
            detail="Service not initialized. The application is starting up.",
        )
    return _query_service_instance


# ==========================================================================
# Router
# ==========================================================================

router = APIRouter()


def _build_audit_actor(http_request: Request | None) -> dict[str, str]:
    if http_request is None:
        return {"clinician_id": "system", "role": "service"}

    claims = getattr(http_request.state, "auth_claims", {}) or {}
    subject = getattr(http_request.state, "auth_subject", None)
    actor_id = (
        str(claims.get("preferred_username") or "")
        or str(claims.get("oid") or "")
        or str(subject or "")
        or "system"
    )
    role = "clinician" if actor_id != "system" else "service"
    return {"clinician_id": actor_id, "role": role}


async def _log_audit_event(
    service: ClinicalQueryService,
    *,
    event_type: str,
    action: str,
    outcome: str = "success",
    http_request: Request | None = None,
    resource_type: str = "system",
    resource_id: str | None = None,
    session_id: str | None = None,
    patient_id: str | None = None,
    justification: str = "",
    details: dict[str, Any] | None = None,
    data_sent_to_llm: bool = False,
    phi_fields_sent: list[str] | None = None,
    phi_fields_redacted: list[str] | None = None,
) -> None:
    if service.cosmos_client is None or not hasattr(service.cosmos_client, "log_audit_event"):
        return

    now = datetime.now(timezone.utc)
    audit_event: dict[str, Any] = {
        "id": str(uuid4()),
        "date_partition": now.strftime("%Y-%m-%d"),
        "event_type": event_type,
        "timestamp": now.isoformat(),
        "actor": _build_audit_actor(http_request),
        "action": action,
        "resource": {
            "type": resource_type,
            "id": resource_id or "unknown",
        },
        "session_id": session_id or str(uuid4()),
        "justification": justification or action.replace("_", " "),
        "outcome": outcome,
        "data_sent_to_llm": data_sent_to_llm,
        "phi_fields_sent": phi_fields_sent or [],
        "phi_fields_redacted": phi_fields_redacted or [],
    }

    if patient_id:
        audit_event["patient_id"] = patient_id
    if details:
        audit_event["details"] = details

    try:
        await service.cosmos_client.log_audit_event(audit_event)
    except Exception as exc:
        logger.warning(
            "Failed to persist audit event",
            extra={
                "event_type": event_type,
                "action": action,
                "error": str(exc),
            },
        )


# ==========================================================================
# Clinical Query Endpoints
# ==========================================================================


@router.post(
    "/api/v1/query",
    response_model=ClinicalResponse,
    tags=["Clinical"],
    summary="Submit a clinical query",
    description=(
        "Submit a clinical query for AI-powered decision support. "
        "Processes the query through multi-agent orchestration:\n"
        "1. Patient History Agent searches records\n"
        "2. Medical Literature Agent queries PubMed\n"
        "3. Protocol Agent finds matching guidelines\n"
        "4. Drug Safety Agent checks interactions\n"
        "5. Guardrails Agent validates output"
    ),
)
async def submit_clinical_query(
    http_request: Request,
    request: ClinicalQueryRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> ClinicalResponse:
    """Submit a clinical query for AI-powered decision support."""
    effective_session_id = request.session_id or str(uuid4())
    try:
        response = await service.process_query(
            query_text=request.text,
            patient_id=request.patient_id,
            session_id=effective_session_id,
        )
        return response

    except ValidationError as exc:
        await _log_audit_event(
            service,
            event_type="clinical_query",
            action="process_clinical_query",
            outcome="failure",
            http_request=http_request,
            resource_type="clinical_query",
            resource_id=effective_session_id,
            session_id=effective_session_id,
            patient_id=request.patient_id,
            justification="Clinical query validation failed",
            details={"error": exc.message},
            data_sent_to_llm=False,
        )
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        await _log_audit_event(
            service,
            event_type="clinical_query",
            action="process_clinical_query",
            outcome="failure",
            http_request=http_request,
            resource_type="clinical_query",
            resource_id=effective_session_id,
            session_id=effective_session_id,
            patient_id=request.patient_id,
            justification="Clinical query upstream service failure",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        logger.error(
            "Azure service error during query processing",
            extra={"error": exc.message},
        )
        raise HTTPException(
            status_code=502,
            detail="An upstream service error occurred. Please try again later.",
        ) from exc
    except CDSSError as exc:
        await _log_audit_event(
            service,
            event_type="clinical_query",
            action="process_clinical_query",
            outcome="failure",
            http_request=http_request,
            resource_type="clinical_query",
            resource_id=effective_session_id,
            session_id=effective_session_id,
            patient_id=request.patient_id,
            justification="Clinical query processing failed",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        logger.error(
            "CDSS error during query processing",
            extra={"error": exc.message},
        )
        raise HTTPException(status_code=500, detail=exc.message) from exc


@router.get(
    "/api/v1/query/stream",
    tags=["Clinical"],
    summary="Stream clinical query response via GET",
    description="Stream clinical query response via Server-Sent Events using GET with query parameters. Compatible with EventSource API.",
)
async def stream_clinical_query_get(
    http_request: Request,
    query: str = Query(..., min_length=1, max_length=5000, description="The clinical query text."),
    patient_id: str | None = Query(None, description="Optional patient ID for context."),
    session_id: str | None = Query(None, description="Optional session ID for conversation continuity."),
    service: ClinicalQueryService = Depends(get_query_service),
) -> StreamingResponse:
    """Stream clinical query response via Server-Sent Events using GET.

    This endpoint accepts query parameters instead of JSON body to support
    EventSource API which only supports GET requests.

    Returns a streaming response where each event is a JSON-encoded
    progress update or partial result.
    """

    async def event_generator():
        effective_session_id = session_id or str(uuid4())
        try:
            yield _sse_event(
                "processing",
                {
                    "status": "started",
                    "message": "Processing clinical query...",
                    "session_id": effective_session_id,
                },
            )

            yield _sse_event(
                "progress",
                {
                    "phase": "planning",
                    "message": "Analyzing query and creating execution plan...",
                },
            )

            response = await service.process_query(
                query_text=query,
                patient_id=patient_id,
                session_id=effective_session_id,
            )

            for agent_name, agent_output in response.agent_outputs.items():
                yield _sse_event(
                    "agent_result",
                    {
                        "agent": agent_name,
                        "summary": agent_output.summary,
                        "sources_retrieved": agent_output.sources_retrieved,
                        "latency_ms": agent_output.latency_ms,
                    },
                )

            if response.drug_alerts:
                yield _sse_event(
                    "drug_alerts",
                    {
                        "alerts": [
                            {
                                "severity": alert.severity,
                                "description": alert.description,
                                "source": alert.source,
                            }
                            for alert in response.drug_alerts
                        ]
                    },
                )

            yield _sse_event(
                "complete",
                response.model_dump(mode="json"),
            )

        except CDSSError as exc:
            await _log_audit_event(
                service,
                event_type="clinical_query_stream",
                action="stream_clinical_query",
                outcome="failure",
                http_request=http_request,
                resource_type="clinical_query",
                resource_id=effective_session_id,
                session_id=effective_session_id,
                patient_id=patient_id,
                justification="Streaming clinical query failed",
                details={"error": exc.message},
                data_sent_to_llm=True,
            )
            yield _sse_event(
                "error",
                {"message": exc.message, "type": type(exc).__name__},
            )
        except Exception as exc:
            await _log_audit_event(
                service,
                event_type="clinical_query_stream",
                action="stream_clinical_query",
                outcome="failure",
                http_request=http_request,
                resource_type="clinical_query",
                resource_id=effective_session_id,
                session_id=effective_session_id,
                patient_id=patient_id,
                justification="Streaming clinical query raised unexpected exception",
                details={"error": str(exc)},
                data_sent_to_llm=True,
            )
            logger.error("Stream error", extra={"error": str(exc)}, exc_info=True)
            yield _sse_event(
                "error",
                {"message": "An unexpected error occurred.", "type": "InternalError"},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/api/v1/query/stream",
    tags=["Clinical"],
    summary="Stream clinical query response",
    description="Stream clinical query response via Server-Sent Events.",
)
async def stream_clinical_query(
    http_request: Request,
    request: ClinicalQueryRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> StreamingResponse:
    """Stream clinical query response via Server-Sent Events.

    Returns a streaming response where each event is a JSON-encoded
    progress update or partial result.
    """

    async def event_generator():
        """Generate SSE events for the clinical query."""
        effective_session_id = request.session_id or str(uuid4())
        try:
            yield _sse_event(
                "processing",
                {
                    "status": "started",
                    "message": "Processing clinical query...",
                    "session_id": effective_session_id,
                },
            )

            yield _sse_event(
                "progress",
                {
                    "phase": "planning",
                    "message": "Analyzing query and creating execution plan...",
                },
            )

            response = await service.process_query(
                query_text=request.text,
                patient_id=request.patient_id,
                session_id=effective_session_id,
            )

            for agent_name, agent_output in response.agent_outputs.items():
                yield _sse_event(
                    "agent_result",
                    {
                        "agent": agent_name,
                        "summary": agent_output.summary,
                        "sources_retrieved": agent_output.sources_retrieved,
                        "latency_ms": agent_output.latency_ms,
                    },
                )

            if response.drug_alerts:
                yield _sse_event(
                    "drug_alerts",
                    {
                        "alerts": [
                            {
                                "severity": alert.severity,
                                "description": alert.description,
                                "source": alert.source,
                            }
                            for alert in response.drug_alerts
                        ]
                    },
                )

            yield _sse_event(
                "complete",
                response.model_dump(mode="json"),
            )

        except CDSSError as exc:
            await _log_audit_event(
                service,
                event_type="clinical_query_stream",
                action="stream_clinical_query",
                outcome="failure",
                http_request=http_request,
                resource_type="clinical_query",
                resource_id=effective_session_id,
                session_id=effective_session_id,
                patient_id=request.patient_id,
                justification="Streaming clinical query failed",
                details={"error": exc.message},
                data_sent_to_llm=True,
            )
            yield _sse_event(
                "error",
                {"message": exc.message, "type": type(exc).__name__},
            )
        except Exception as exc:
            await _log_audit_event(
                service,
                event_type="clinical_query_stream",
                action="stream_clinical_query",
                outcome="failure",
                http_request=http_request,
                resource_type="clinical_query",
                resource_id=effective_session_id,
                session_id=effective_session_id,
                patient_id=request.patient_id,
                justification="Streaming clinical query raised unexpected exception",
                details={"error": str(exc)},
                data_sent_to_llm=True,
            )
            logger.error("Stream error", extra={"error": str(exc)}, exc_info=True)
            yield _sse_event(
                "error",
                {"message": "An unexpected error occurred.", "type": "InternalError"},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    json_data = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {json_data}\n\n"


# ==========================================================================
# Patient Endpoints
# ==========================================================================


@router.get(
    "/api/v1/patients",
    tags=["Patients"],
    summary="Search patients",
)
async def search_patients(
    search: str | None = Query(None, description="Search query string."),
    page: int = Query(1, ge=1, le=100, description="Page number."),
    limit: int = Query(100, description="Maximum results per page."),
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Search patients by name and other criteria.

    Args:
        search: Search query string.
        page: Page number.
        limit: Maximum results per page.
        service: Injected query service.

    Returns:
        Dictionary with pagination metadata and patient list.
    """
    try:
        return await service.search_patients(
            search=search,
            page=page,
            limit=limit,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


@router.get(
    "/api/v1/patients/{patient_id}",
    tags=["Patients"],
    summary="Get patient profile",
)
async def get_patient_profile(
    patient_id: str,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Retrieve a patient profile by ID.

    Args:
        patient_id: The unique patient identifier.
        service: Injected query service.

    Returns:
        The patient profile data.
    """
    try:
        profile = await service.get_patient_profile(patient_id)
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Patient '{patient_id}' not found.",
            )
        return profile

    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


@router.put(
    "/api/v1/patients/{patient_id}",
    tags=["Patients"],
    summary="Update patient profile",
)
async def update_patient_profile(
    patient_id: str,
    profile: dict,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Create or update a patient profile.

    Args:
        patient_id: The unique patient identifier.
        profile: The profile data to upsert.
        service: Injected query service.

    Returns:
        The upserted patient profile data.
    """
    try:
        result = await service.update_patient_profile(patient_id, profile)
        return result

    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


# ==========================================================================
# Conversation Endpoints
# ==========================================================================


@router.get(
    "/api/v1/conversations/{session_id}",
    tags=["Conversations"],
    summary="Get conversation history",
)
async def get_conversation_history(
    session_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max turns to return."),
    service: ClinicalQueryService = Depends(get_query_service),
) -> list[dict]:
    """Retrieve conversation history for a session.

    Args:
        session_id: The session identifier.
        limit: Maximum number of conversation turns.
        service: Injected query service.

    Returns:
        List of conversation turn dictionaries.
    """
    try:
        history = await service.get_conversation_history(
            session_id=session_id,
            limit=limit,
        )
        return history

    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


@router.post(
    "/api/v1/conversations/{conversation_id}/feedback",
    tags=["Conversations"],
    summary="Submit feedback",
)
async def submit_feedback(
    conversation_id: str,
    feedback: FeedbackRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Submit clinician feedback on a response.

    Args:
        conversation_id: The conversation turn ID to provide feedback for.
        feedback: The feedback data (rating and optional correction).
        service: Injected query service.

    Returns:
        Confirmation of the feedback submission.
    """
    try:
        result = await service.submit_feedback(
            conversation_id=conversation_id,
            rating=feedback.rating,
            correction=feedback.correction,
        )
        return result

    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


# ==========================================================================
# Document Ingestion Endpoints
# ==========================================================================

# Process-local fallback store for ingestion status. Primary persistence for
# production runs is Cosmos DB via ClinicalQueryService.cosmos_client.
_ingestion_status: dict[str, dict] = {}
_INGESTION_STATUS_PARTITION_KEY = "ingestion_status"
_INGESTION_STATUS_DOC_TYPE = "ingestion_status"
_grounded_preview_cache: dict[str, dict] = {}
_GROUNDED_PREVIEW_CACHE_MAX_ITEMS = 128


def _build_grounded_preview_cache_key(
    *,
    document_id: str,
    pipeline_document_id: str,
    logical_index_name: str,
    question: str,
    top: int,
    max_tokens: int,
) -> str:
    raw_key = "|".join(
        [
            document_id,
            pipeline_document_id,
            logical_index_name,
            question.strip().lower(),
            str(top),
            str(max_tokens),
        ]
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _get_grounded_preview_cache_entry(cache_key: str) -> dict | None:
    entry = _grounded_preview_cache.pop(cache_key, None)
    if entry is None:
        return None
    # Move to end to keep recently used items.
    _grounded_preview_cache[cache_key] = entry
    return entry


def _put_grounded_preview_cache_entry(cache_key: str, payload: dict) -> None:
    _grounded_preview_cache[cache_key] = payload
    while len(_grounded_preview_cache) > _GROUNDED_PREVIEW_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_grounded_preview_cache))
        _grounded_preview_cache.pop(oldest_key, None)


def _resolve_ingestion_status_client(query_service: ClinicalQueryService) -> object | None:
    cosmos_client = getattr(query_service, "cosmos_client", None)
    if cosmos_client is None:
        return None
    if not hasattr(cosmos_client, "upsert_ingestion_status"):
        return None
    if not hasattr(cosmos_client, "get_ingestion_status"):
        return None
    return cosmos_client


async def _persist_ingestion_status(
    query_service: ClinicalQueryService,
    document_id: str,
    status_payload: dict,
) -> None:
    _ingestion_status[document_id] = status_payload

    cosmos_client = _resolve_ingestion_status_client(query_service)
    if cosmos_client is None:
        return

    try:
        await cosmos_client.upsert_ingestion_status(
            document_id=document_id,
            status=status_payload,
            partition_key=_INGESTION_STATUS_PARTITION_KEY,
            doc_type=_INGESTION_STATUS_DOC_TYPE,
        )
    except Exception as exc:
        logger.warning(
            "Failed to persist ingestion status to Cosmos DB; using in-memory fallback",
            extra={
                "document_id": document_id,
                "error": str(exc),
            },
        )


async def _update_ingestion_status(
    query_service: ClinicalQueryService,
    document_id: str,
    **updates: object,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    current = dict(_ingestion_status.get(document_id, {"document_id": document_id}))
    current.update(updates)
    current["document_id"] = document_id
    current["updated_at"] = str(updates.get("updated_at", now))
    if not current.get("created_at"):
        current["created_at"] = now

    await _persist_ingestion_status(query_service, document_id, current)
    return current


async def _get_ingestion_status_record(
    query_service: ClinicalQueryService,
    document_id: str,
) -> dict | None:
    cosmos_client = _resolve_ingestion_status_client(query_service)
    if cosmos_client is not None:
        try:
            persisted = await cosmos_client.get_ingestion_status(
                document_id=document_id,
                partition_key=_INGESTION_STATUS_PARTITION_KEY,
            )
            if persisted is not None:
                _ingestion_status[document_id] = persisted
                return persisted
        except Exception as exc:
            logger.warning(
                "Failed to read ingestion status from Cosmos DB; using in-memory fallback",
                extra={
                    "document_id": document_id,
                    "error": str(exc),
                },
            )

    return _ingestion_status.get(document_id)


async def _delete_ingestion_status_record(
    query_service: ClinicalQueryService,
    document_id: str,
) -> None:
    _ingestion_status.pop(document_id, None)

    cosmos_client = getattr(query_service, "cosmos_client", None)
    if cosmos_client is None:
        return
    if not hasattr(cosmos_client, "delete_ingestion_status"):
        return

    try:
        await cosmos_client.delete_ingestion_status(
            document_id=document_id,
            partition_key=_INGESTION_STATUS_PARTITION_KEY,
        )
    except Exception as exc:
        logger.warning(
            "Failed to delete ingestion status from Cosmos DB; local status removed",
            extra={
                "document_id": document_id,
                "error": str(exc),
            },
        )


def _resolve_logical_index_for_document_type(normalized_document_type: str) -> str:
    if normalized_document_type == "clinical_guideline":
        return INDEX_TREATMENT_PROTOCOLS
    if normalized_document_type == "pubmed_abstract":
        return INDEX_MEDICAL_LITERATURE
    return INDEX_PATIENT_RECORDS


def _resolve_workspace_target(normalized_document_type: str) -> str:
    if normalized_document_type == "clinical_guideline":
        return "protocol"
    if normalized_document_type == "pubmed_abstract":
        return "literature"
    return "query_patient_context"


async def _resolve_index_with_document_hits(
    search_client: AzureSearchClient,
    *,
    pipeline_document_id: str,
    preferred_index_name: str,
    top: int,
) -> tuple[str, list[dict], bool]:
    """Resolve an index that actually contains chunks for this document.

    Supports compatibility with legacy uploads that may have been indexed into
    a different logical index than their normalized document type.
    """
    candidate_indexes = [
        preferred_index_name,
        *[
            idx
            for idx in (INDEX_PATIENT_RECORDS, INDEX_TREATMENT_PROTOCOLS, INDEX_MEDICAL_LITERATURE)
            if idx != preferred_index_name
        ],
    ]

    for idx in candidate_indexes:
        indexed_hits = await search_client.search_document_chunks(
            index_name=idx,
            document_id=pipeline_document_id,
            search_text="*",
            top=top,
        )
        if indexed_hits:
            return idx, indexed_hits, idx != preferred_index_name

    return preferred_index_name, [], False


def _build_content_preview(content: str, max_len: int = 180) -> str:
    compact = " ".join(content.split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 3]}..."


def _parse_json_object_from_text(content: str) -> dict[str, Any] | None:
    """Best-effort parser for model outputs that should be JSON objects."""
    raw = (content or "").strip()
    if not raw:
        return {}

    def _try_load(candidate: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        # Some models wrap the JSON object as a JSON string; unwrap once.
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                return None

        return parsed if isinstance(parsed, dict) else None

    direct = _try_load(raw)
    if direct is not None:
        return direct

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    for block in fenced_blocks:
        parsed = _try_load(block.strip())
        if parsed is not None:
            return parsed

    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        parsed = _try_load(raw[first_brace : last_brace + 1])
        if parsed is not None:
            return parsed

    return None


def _tokenize_question_keywords(question: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", question.lower())
    return [token for token in tokens if len(token) >= 4]


def _select_quote_from_content(content: str, question: str, max_len: int = 260) -> str:
    text = " ".join(content.split())
    if not text:
        return ""

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return text[:max_len]

    keywords = _tokenize_question_keywords(question)
    if not keywords:
        return sentences[0][:max_len]

    best_sentence = sentences[0]
    best_score = -1
    for sentence in sentences:
        lowered = sentence.lower()
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_score = score
            best_sentence = sentence

    return best_sentence[:max_len]


def _build_extractive_grounded_fallback(
    *,
    retrieved_hits: list[dict[str, Any]],
    question: str,
    max_citations: int = 3,
) -> dict[str, Any]:
    citations: list[dict[str, Any]] = []
    answer_parts: list[str] = []

    for hit in retrieved_hits[:max_citations]:
        chunk_id = str(hit.get("id") or "").strip()
        content = str(hit.get("content") or "")
        if not chunk_id or not content:
            continue

        quote = _select_quote_from_content(content, question)
        if not quote:
            continue

        citations.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": hit.get("chunk_index"),
                "quote": quote,
                "score": hit.get("score", 0.0),
                "content_preview": _build_content_preview(content),
            }
        )
        answer_parts.append(quote)

    if not citations:
        return {
            "status": "no_supporting_evidence",
            "answer": "No supporting evidence found in indexed chunks for this question.",
            "confidence": 0.0,
            "citations": [],
        }

    fallback_answer = " ".join(answer_parts)
    return {
        "status": "ok",
        "answer": fallback_answer,
        "confidence": 0.35,
        "citations": citations,
    }


def _extract_literature_articles(response: ClinicalResponse) -> list[dict]:
    literature_output = response.agent_outputs.get("literature")
    articles: list[dict] = []
    if literature_output and literature_output.raw_data:
        raw = literature_output.raw_data
        if isinstance(raw.get("papers"), list):
            articles = raw.get("papers", [])
        elif isinstance(raw.get("articles"), list):
            articles = raw.get("articles", [])
        elif isinstance(raw.get("literature_evidence"), dict):
            evidence = raw.get("literature_evidence", {})
            papers = evidence.get("papers", [])
            if isinstance(papers, list):
                articles = papers
    return articles


@router.post(
    "/api/v1/documents/ingest",
    tags=["Documents"],
    summary="Ingest a medical document",
)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    document_type: str | None = Form(
        default=None,
        description="Document type: 'protocol', 'patient_record', 'literature'.",
    ),
    patient_id: str | None = Form(
        default=None,
        description="Optional patient ID to associate the document with.",
    ),
    metadata: str | None = Form(
        default=None,
        description="Optional JSON metadata payload as string.",
    ),
    background_tasks: BackgroundTasks = None,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Ingest a medical document (PDF) for processing.

    The document is validated, assigned an ID, and submitted for
    background processing.  Use the ``/documents/{document_id}/status``
    endpoint to track progress.

    Args:
        file: The uploaded file.
        document_type: Type classification for the document.
        patient_id: Optional patient association.
        background_tasks: FastAPI background task manager.

    Returns:
        A dictionary with the assigned ``document_id`` and initial status.
    """
    # Validate file type
    valid_content_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    content_type = file.content_type or ""
    if content_type not in valid_content_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{content_type}'. Accepted types: {', '.join(sorted(valid_content_types))}."
            ),
        )

    # Query parameter fallback for backward compatibility.
    if document_type is None:
        document_type = request.query_params.get("document_type")
    if patient_id is None:
        patient_id = request.query_params.get("patient_id")

    if document_type is None:
        raise HTTPException(
            status_code=422,
            detail="Missing required document_type. Provide it in multipart form or as query parameter.",
        )

    metadata_payload: dict[str, object] | None = None
    if metadata:
        try:
            parsed = json.loads(metadata)
            metadata_payload = parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    document_type_map = {
        "patient_record": "generic",
        "protocol": "clinical_guideline",
        "literature": "pubmed_abstract",
        "lab_report": "lab_report",
        "prescription": "prescription",
        "discharge_summary": "discharge_summary",
        "radiology_report": "radiology_report",
        "clinical_guideline": "clinical_guideline",
        "pubmed_abstract": "pubmed_abstract",
        "generic": "generic",
    }
    if document_type not in document_type_map:
        raise HTTPException(
            status_code=400,
            detail=(f"Invalid document_type '{document_type}'. Valid types: {', '.join(sorted(document_type_map))}."),
        )
    normalized_document_type = document_type_map[document_type]

    document_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Read file content
    try:
        file_content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    # Initialize ingestion status (durable in Cosmos DB, in-memory fallback)
    await _persist_ingestion_status(
        service,
        document_id,
        {
            "document_id": document_id,
            "filename": file.filename,
            "document_type": document_type,
            "normalized_document_type": normalized_document_type,
            "patient_id": patient_id,
            "metadata": metadata_payload or {},
            "status": "pending",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "error": None,
        },
    )

    await _log_audit_event(
        service,
        event_type="document_ingest",
        action="ingest_document",
        outcome="success",
        http_request=request,
        resource_type="document",
        resource_id=document_id,
        session_id=str(uuid4()),
        patient_id=patient_id,
        justification=f"Document ingest requested: {document_type}",
        details={
            "filename": file.filename or "unknown",
            "document_type": document_type,
            "normalized_document_type": normalized_document_type,
        },
        data_sent_to_llm=False,
    )

    # Schedule background processing
    if background_tasks is not None:
        background_tasks.add_task(
            _process_document_background,
            query_service=service,
            document_id=document_id,
            file_content=file_content,
            filename=file.filename or "unknown",
            document_type=document_type,
            normalized_document_type=normalized_document_type,
            patient_id=patient_id,
            metadata=metadata_payload,
        )
        return {
            "document_id": document_id,
            "status": "pending",
            "message": "Document accepted for processing.",
        }

    await _process_document_background(
        query_service=service,
        document_id=document_id,
        file_content=file_content,
        filename=file.filename or "unknown",
        document_type=document_type,
        normalized_document_type=normalized_document_type,
        patient_id=patient_id,
        metadata=metadata_payload,
    )

    final_status = await _get_ingestion_status_record(service, document_id) or {
        "status": "unknown"
    }
    return {
        "document_id": document_id,
        "status": final_status["status"],
        "message": final_status.get("message", "Document processing finished."),
    }


async def _process_document_background(
    query_service: ClinicalQueryService,
    document_id: str,
    file_content: bytes,
    filename: str,
    document_type: str,
    normalized_document_type: str,
    patient_id: str | None,
    metadata: dict[str, object] | None,
) -> None:
    """Background task that processes an ingested document.

    Performs PDF text extraction, chunking, embedding generation, and
    indexing into Azure AI Search.

    Args:
        document_id: The assigned document identifier.
        file_content: Raw file bytes.
        filename: Original filename.
        document_type: Document type classification.
        patient_id: Optional associated patient ID.
    """
    try:
        await _update_ingestion_status(
            query_service,
            document_id,
            status="processing",
            progress=10,
        )

        ingestion_service = query_service.ingestion_service

        if document_type == "protocol":
            metadata_dict = metadata or {}
            specialty = str(metadata_dict.get("specialty", "general"))
            guideline_name = str(metadata_dict.get("guideline_name") or metadata_dict.get("guideline") or filename)
            version = str(metadata_dict.get("version", "1.0"))

            result = await ingestion_service.ingest_protocol(
                file_bytes=file_content,
                specialty=specialty,
                guideline_name=guideline_name,
                version=version,
                metadata=metadata,
            )
        else:
            result = await ingestion_service.ingest_patient_document(
                file_bytes=file_content,
                document_type=normalized_document_type,
                patient_id=patient_id,
                metadata=metadata,
            )

        result_status = str(result.get("status", "completed"))
        await _update_ingestion_status(
            query_service,
            document_id,
            status=result_status,
            progress=100,
            pipeline_document_id=result.get("document_id"),
            message=str(result.get("message", "Document processing completed.")),
            details=result,
            error=None,
        )

        logger.info(
            "Document processing completed",
            extra={
                "document_id": document_id,
                "source_filename": filename,
                "document_type": document_type,
                "metadata_keys": sorted((metadata or {}).keys()),
                "pipeline_document_id": result.get("document_id"),
            },
        )
        await _log_audit_event(
            query_service,
            event_type="document_ingestion_completed",
            action="process_document_ingestion",
            outcome="success",
            resource_type="document",
            resource_id=document_id,
            session_id=str(uuid4()),
            patient_id=patient_id,
            justification=f"Document ingestion completed for {document_type}",
            details={
                "filename": filename,
                "document_type": document_type,
                "normalized_document_type": normalized_document_type,
                "pipeline_document_id": str(result.get("document_id") or ""),
                "status": result_status,
            },
            data_sent_to_llm=False,
        )

    except Exception as exc:
        await _update_ingestion_status(
            query_service,
            document_id,
            status="failed",
            progress=100,
            error=str(exc),
        )

        logger.error(
            "Document processing failed",
            extra={"document_id": document_id, "error": str(exc)},
        )
        await _log_audit_event(
            query_service,
            event_type="document_ingestion_completed",
            action="process_document_ingestion",
            outcome="failure",
            resource_type="document",
            resource_id=document_id,
            session_id=str(uuid4()),
            patient_id=patient_id,
            justification=f"Document ingestion failed for {document_type}",
            details={
                "filename": filename,
                "document_type": document_type,
                "normalized_document_type": normalized_document_type,
                "error": str(exc),
            },
            data_sent_to_llm=False,
        )


@router.get(
    "/api/v1/documents/{document_id}/status",
    tags=["Documents"],
    summary="Check document ingestion status",
)
async def get_ingestion_status(
    document_id: str,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Check the status of a document ingestion job.

    Args:
        document_id: The document identifier returned by the ingest endpoint.

    Returns:
        A dictionary with status, progress percentage, and any errors.
    """
    status = await _get_ingestion_status_record(service, document_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found.",
        )
    return status


@router.post(
    "/api/v1/documents/{document_id}/verify",
    tags=["Documents"],
    summary="Verify indexed chunks and phrase retrieval for an ingested document",
)
async def verify_document_index_and_retrieval(
    document_id: str,
    request: DocumentVerificationRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Verify that a document was indexed and can be retrieved by phrase.

    This endpoint is intended for UI-native validation flows and returns
    index proof (chunk presence by document_id) plus optional retrieval proof
    for a provided phrase.
    """
    status = await _get_ingestion_status_record(service, document_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    normalized_document_type = str(
        status.get("normalized_document_type")
        or status.get("document_type")
        or "generic"
    )
    pipeline_document_id = str(status.get("pipeline_document_id") or document_id)

    logical_index_name = _resolve_logical_index_for_document_type(normalized_document_type)
    workspace_target = _resolve_workspace_target(normalized_document_type)

    try:
        search_client = AzureSearchClient(settings=service.settings)

        resolved_logical_index_name, indexed_hits, resolved_by_fallback = await _resolve_index_with_document_hits(
            search_client,
            pipeline_document_id=pipeline_document_id,
            preferred_index_name=logical_index_name,
            top=request.top,
        )
        if resolved_by_fallback:
            logger.warning(
                "Document verification index fallback used",
                extra={
                    "document_id": document_id,
                    "pipeline_document_id": pipeline_document_id,
                    "preferred_index": logical_index_name,
                    "resolved_index": resolved_logical_index_name,
                },
            )
        logical_index_name = resolved_logical_index_name

        phrase = (request.phrase or "").strip()
        phrase_hits: list[dict] = []
        if phrase:
            phrase_hits = await search_client.search_document_chunks(
                index_name=logical_index_name,
                document_id=pipeline_document_id,
                search_text=phrase,
                top=request.top,
            )

        def normalize_hit(hit: dict) -> dict:
            return {
                "id": hit.get("id", ""),
                "chunk_index": hit.get("chunk_index"),
                "score": hit.get("score", 0.0),
                "content_preview": _build_content_preview(str(hit.get("content", ""))),
            }

        return {
            "document_id": document_id,
            "pipeline_document_id": pipeline_document_id,
            "document_type": str(status.get("document_type", "unknown")),
            "normalized_document_type": normalized_document_type,
            "workspace_target": workspace_target,
            "logical_index_name": logical_index_name,
            "physical_index_name": search_client.resolve_index_name(logical_index_name),
            "resolved_by_index_fallback": resolved_by_fallback,
            "indexed_chunks_count": len(indexed_hits),
            "indexed_chunks": [normalize_hit(hit) for hit in indexed_hits],
            "phrase": phrase or None,
            "phrase_hits_count": len(phrase_hits),
            "phrase_hits": [normalize_hit(hit) for hit in phrase_hits],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Document verification failed: {exc}",
        ) from exc


@router.post(
    "/api/v1/documents/{document_id}/grounded-preview",
    tags=["Documents"],
    summary="Generate grounded answer preview from indexed chunks",
)
async def generate_grounded_answer_preview(
    document_id: str,
    request: DocumentGroundedPreviewRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Generate an answer strictly grounded in indexed chunks for a document.

    This endpoint intentionally stays separate from deterministic index
    verification to keep retrieval diagnostics and LLM synthesis isolated.
    """
    status = await _get_ingestion_status_record(service, document_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    status_value = str(status.get("status", "")).lower()
    if status_value not in {"completed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Document '{document_id}' is not ready for grounded preview. Current status: {status_value}.",
        )

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty.")

    normalized_document_type = str(
        status.get("normalized_document_type")
        or status.get("document_type")
        or "generic"
    )
    pipeline_document_id = str(status.get("pipeline_document_id") or document_id)
    logical_index_name = _resolve_logical_index_for_document_type(normalized_document_type)
    workspace_target = _resolve_workspace_target(normalized_document_type)

    cache_key = _build_grounded_preview_cache_key(
        document_id=document_id,
        pipeline_document_id=pipeline_document_id,
        logical_index_name=logical_index_name,
        question=question,
        top=request.top,
        max_tokens=request.max_tokens,
    )

    if request.use_cache:
        cached = _get_grounded_preview_cache_entry(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

    search_client = AzureSearchClient(settings=service.settings)
    search_timeout = max(3, min(request.timeout_seconds - 2, 30))
    retrieval_strategy = "question_search_any"
    resolved_by_fallback = False
    retrieved_hits: list[dict] = []

    try:
        resolved_logical_index_name, indexed_hits, resolved_by_fallback = await _resolve_index_with_document_hits(
            search_client,
            pipeline_document_id=pipeline_document_id,
            preferred_index_name=logical_index_name,
            top=request.top,
        )
        logical_index_name = resolved_logical_index_name

        retrieved_hits = await asyncio.wait_for(
            search_client.search_document_chunks(
                index_name=logical_index_name,
                document_id=pipeline_document_id,
                search_text=question,
                top=request.top,
                search_mode="any",
            ),
            timeout=search_timeout,
        )

        if not retrieved_hits:
            retrieval_strategy = "document_scope_fallback_wildcard"
            retrieved_hits = indexed_hits
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Timed out retrieving indexed chunks for grounded preview.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Grounded preview retrieval failed: {exc}",
        ) from exc

    base_response = {
        "document_id": document_id,
        "pipeline_document_id": pipeline_document_id,
        "normalized_document_type": normalized_document_type,
        "workspace_target": workspace_target,
        "logical_index_name": logical_index_name,
        "physical_index_name": search_client.resolve_index_name(logical_index_name),
        "resolved_by_index_fallback": resolved_by_fallback,
        "question": question,
        "retrieval_strategy": retrieval_strategy,
        "retrieved_chunks_count": len(retrieved_hits),
    }

    if not retrieved_hits:
        payload = {
            **base_response,
            "status": "no_supporting_evidence",
            "answer": "No supporting evidence found in indexed chunks for this question.",
            "confidence": 0.0,
            "citations": [],
            "cached": False,
        }
        if request.use_cache:
            _put_grounded_preview_cache_entry(cache_key, {k: v for k, v in payload.items() if k != "cached"})
        return payload

    openai_client = getattr(getattr(service, "orchestrator", None), "openai_client", None)
    if openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="Grounded preview is unavailable because the OpenAI client is not configured.",
        )

    grounding_context = [
        {
            "chunk_id": str(hit.get("id", "")),
            "chunk_index": hit.get("chunk_index"),
            "content": str(hit.get("content", "")),
        }
        for hit in retrieved_hits
        if hit.get("id")
    ]

    system_prompt = (
        "You are a clinical evidence assistant. Answer ONLY from provided chunk context. "
        "If evidence is insufficient, set no_supporting_evidence=true and return no citations. "
        "Return strict JSON: {\"answer\": string, \"confidence\": number, "
        "\"no_supporting_evidence\": boolean, \"citations\": [{\"chunk_id\": string, \"quote\": string}]}. "
        "Every citation quote must be verbatim text from the cited chunk."
    )
    user_payload = {
        "question": question,
        "chunks": grounding_context,
    }

    try:
        llm_response = await asyncio.wait_for(
            openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
                model="gpt-4o-mini",
                temperature=0.0,
                max_tokens=request.max_tokens,
                response_format={"type": "json_object"},
            ),
            timeout=request.timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Timed out generating grounded answer preview.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Grounded preview synthesis failed: {exc}",
        ) from exc

    llm_content = str(llm_response.get("content") or "")
    llm_payload = _parse_json_object_from_text(llm_content)
    if llm_payload is None:
        logger.warning(
            "Grounded preview model output was not valid JSON",
            extra={
                "document_id": document_id,
                "pipeline_document_id": pipeline_document_id,
                "logical_index_name": logical_index_name,
                "content_preview": _build_content_preview(llm_content, max_len=240),
            },
        )
        fallback = _build_extractive_grounded_fallback(
            retrieved_hits=retrieved_hits,
            question=question,
        )
        payload = {
            **base_response,
            "status": fallback["status"],
            "answer": fallback["answer"],
            "confidence": fallback["confidence"],
            "citations": fallback["citations"],
            "cached": False,
        }
        if request.use_cache:
            _put_grounded_preview_cache_entry(cache_key, {k: v for k, v in payload.items() if k != "cached"})
        return payload

    raw_answer = str(llm_payload.get("answer") or "").strip()
    if not raw_answer:
        raw_answer = "No supporting evidence found in indexed chunks for this question."

    raw_confidence = llm_payload.get("confidence", 0.0)
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    hit_by_id = {
        str(hit.get("id")): hit
        for hit in retrieved_hits
        if hit.get("id")
    }
    valid_citations: list[dict] = []
    for item in llm_payload.get("citations", []):
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not chunk_id or not quote:
            continue
        hit = hit_by_id.get(chunk_id)
        if hit is None:
            continue
        content = str(hit.get("content", ""))
        if quote.lower() not in content.lower():
            continue
        valid_citations.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": hit.get("chunk_index"),
                "quote": quote,
                "score": hit.get("score", 0.0),
                "content_preview": _build_content_preview(content),
            }
        )

    no_supporting_evidence = bool(llm_payload.get("no_supporting_evidence")) or not valid_citations
    answer = raw_answer
    if no_supporting_evidence:
        answer = "No supporting evidence found in indexed chunks for this question."
        confidence = 0.0

    payload = {
        **base_response,
        "status": "no_supporting_evidence" if no_supporting_evidence else "ok",
        "answer": answer,
        "confidence": confidence,
        "citations": valid_citations,
        "cached": False,
    }
    if request.use_cache:
        _put_grounded_preview_cache_entry(cache_key, {k: v for k, v in payload.items() if k != "cached"})
    return payload


@router.delete(
    "/api/v1/documents/{document_id}",
    tags=["Documents"],
    summary="Delete an ingested document and its indexed chunks",
)
async def delete_ingested_document(
    http_request: Request,
    document_id: str,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Delete indexed chunks and ingestion status for an uploaded document."""
    status = await _get_ingestion_status_record(service, document_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    current_status = str(status.get("status", "")).lower()
    if current_status in {"pending", "queued", "processing"}:
        raise HTTPException(
            status_code=409,
            detail="Document is still processing. Wait until completion before deletion.",
        )

    normalized_document_type = str(
        status.get("normalized_document_type")
        or status.get("document_type")
        or "generic"
    )
    pipeline_document_id = str(status.get("pipeline_document_id") or document_id)
    logical_index_name = _resolve_logical_index_for_document_type(normalized_document_type)

    try:
        search_client = AzureSearchClient(settings=service.settings)
        delete_summary = await search_client.delete_document_chunks(
            index_name=logical_index_name,
            document_id=pipeline_document_id,
        )

        if int(delete_summary.get("failed_count", 0)) > 0:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Document deletion was only partially successful. "
                    "Some indexed chunks failed to delete; retry the operation."
                ),
            )

        await _delete_ingestion_status_record(service, document_id)

        response_payload = {
            "document_id": document_id,
            "pipeline_document_id": pipeline_document_id,
            "normalized_document_type": normalized_document_type,
            "logical_index_name": logical_index_name,
            "physical_index_name": search_client.resolve_index_name(logical_index_name),
            "deleted_chunks_count": int(delete_summary.get("deleted_count", 0)),
            "status": "deleted",
        }
        await _log_audit_event(
            service,
            event_type="document_delete",
            action="delete_ingested_document",
            outcome="success",
            http_request=http_request,
            resource_type="document",
            resource_id=document_id,
            session_id=str(uuid4()),
            patient_id=str(status.get("patient_id") or "") or None,
            justification="Delete ingested document",
            details={
                "pipeline_document_id": pipeline_document_id,
                "deleted_chunks_count": int(delete_summary.get("deleted_count", 0)),
                "normalized_document_type": normalized_document_type,
            },
            data_sent_to_llm=False,
        )
        return response_payload
    except HTTPException:
        raise
    except Exception as exc:
        await _log_audit_event(
            service,
            event_type="document_delete",
            action="delete_ingested_document",
            outcome="failure",
            http_request=http_request,
            resource_type="document",
            resource_id=document_id,
            session_id=str(uuid4()),
            patient_id=str(status.get("patient_id") or "") or None,
            justification="Delete ingested document failed",
            details={"error": str(exc)},
            data_sent_to_llm=False,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Document deletion failed: {exc}",
        ) from exc


# ==========================================================================
# Drug Safety Endpoints
# ==========================================================================


@router.post(
    "/api/v1/drugs/interactions",
    tags=["Drug Safety"],
    summary="Check drug interactions",
)
async def check_drug_interactions(
    http_request: Request,
    request: DrugInteractionRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Check drug-drug interactions for a list of medications.

    Normalizes incoming medication names and runs the dedicated
    ``DrugSafetyAgent`` directly to produce deterministic interaction output.

    Args:
        request: The drug interaction check request.
        service: Injected query service.

    Returns:
        Drug interaction results including alerts and alternatives.
    """
    def normalize_medication_names(items: list[str | MedicationNameRequest]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            raw_name = item if isinstance(item, str) else item.name
            name = raw_name.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(name)
        return normalized

    current_medications = normalize_medication_names(list(request.medications))
    proposed_medications = normalize_medication_names(list(request.proposed_medications or []))
    all_medications = [*current_medications, *proposed_medications]

    if len(all_medications) < 2:
        raise HTTPException(
            status_code=422,
            detail="At least two medication names are required for interaction analysis.",
        )

    try:
        drug_safety_agent = DrugSafetyAgent(settings=service.settings)
        task = AgentTask(
            from_agent="api",
            to_agent="drug_safety",
            message_type="task_request",
            payload={
                "query": (
                    "Check drug-drug interactions for the following medications: "
                    f"{', '.join(all_medications)}."
                ),
                "medications": current_medications,
                "proposed_medications": proposed_medications,
                "conditions": [],
                "allergies": [],
            },
            session_id=str(uuid4()),
            trace_id=str(uuid4()),
        )
        output = await drug_safety_agent.execute(task)
        interactions_data = output.raw_data or {}
        report_data = interactions_data.get("drug_safety_report", {})
        raw_alerts = interactions_data.get("drug_alerts", interactions_data.get("alerts", []))
        interactions = report_data.get("interactions", interactions_data.get("interactions", []))

        response_payload = {
            "medications_checked": current_medications,
            "proposed_medications": proposed_medications,
            "interactions": interactions,
            "alerts": [
                {
                    "severity": alert.get("severity", "moderate"),
                    "description": alert.get("description", ""),
                    "source": alert.get("source", "unknown"),
                    "evidence_level": int(alert.get("evidence_level", 2) or 2),
                    "alternatives": alert.get("alternatives", []),
                }
                for alert in raw_alerts
            ],
            "adverse_events": report_data.get("adverse_events", []),
            "alternatives": report_data.get("alternatives", []),
            "dosage_adjustments": report_data.get("dosage_adjustments", []),
            "summary": interactions_data.get("summary", "Interaction analysis completed."),
        }
        severity_counts = {"major": 0, "moderate": 0, "minor": 0}
        for item in interactions:
            severity = str(item.get("severity", "")).lower()
            if severity in severity_counts:
                severity_counts[severity] += 1
        await _log_audit_event(
            service,
            event_type="drug_interaction_analysis",
            action="check_drug_interactions",
            outcome="success",
            http_request=http_request,
            resource_type="drug_safety",
            resource_id=str(uuid4()),
            session_id=str(task.session_id),
            justification="Drug interaction analysis completed",
            details={
                "medications_checked": len(current_medications),
                "proposed_medications": len(proposed_medications),
                "interactions_found": len(interactions),
                "major_interactions": severity_counts["major"],
                "moderate_interactions": severity_counts["moderate"],
                "minor_interactions": severity_counts["minor"],
            },
            data_sent_to_llm=True,
        )
        return response_payload

    except DrugSafetyError as exc:
        await _log_audit_event(
            service,
            event_type="drug_interaction_analysis",
            action="check_drug_interactions",
            outcome="failure",
            http_request=http_request,
            resource_type="drug_safety",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Drug interaction analysis failed",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except CDSSError as exc:
        await _log_audit_event(
            service,
            event_type="drug_interaction_analysis",
            action="check_drug_interactions",
            outcome="failure",
            http_request=http_request,
            resource_type="drug_safety",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Drug interaction analysis failed",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        raise HTTPException(status_code=500, detail=exc.message) from exc


@router.get(
    "/api/v1/drugs/{drug_name}/info",
    tags=["Drug Safety"],
    summary="Get drug information",
)
async def get_drug_info(
    drug_name: str,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Get drug information and known interactions.

    Args:
        drug_name: The name of the drug to look up.
        service: Injected query service.

    Returns:
        Drug information including known interactions and safety data.
    """
    query_text = (
        f"Provide comprehensive drug information for {drug_name}, "
        f"including known interactions, contraindications, and common side effects."
    )

    try:
        response = await service.process_query(query_text=query_text)
        return {
            "drug_name": drug_name,
            "information": response.recommendation,
            "alerts": [
                {
                    "severity": alert.severity,
                    "description": alert.description,
                    "source": alert.source,
                }
                for alert in response.drug_alerts
            ],
            "citations": [
                {
                    "source_type": c.source_type,
                    "identifier": c.identifier,
                    "title": c.title,
                    "url": c.url,
                }
                for c in response.citations
            ],
        }

    except CDSSError as exc:
        raise HTTPException(status_code=500, detail=exc.message) from exc


# ==========================================================================
# Search Endpoints
# ==========================================================================


@router.post(
    "/api/v1/search/literature",
    tags=["Search"],
    summary="Search medical literature",
)
async def search_literature(
    http_request: Request,
    request: LiteratureSearchRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Search PubMed and cached medical literature.

    Routes the search query through the orchestrator's literature agent
    for a comprehensive search across cached indexes and live PubMed.

    Args:
        request: The literature search request.
        service: Injected query service.

    Returns:
        Search results with articles and relevance scores.
    """
    try:
        base_query_text = request.query.strip()
        strict_query_text = base_query_text
        if request.date_from:
            strict_query_text += f" (date_from: {request.date_from})"
        if request.date_range:
            start = request.date_range.get("start", "").strip()
            end = request.date_range.get("end", "").strip()
            if start or end:
                strict_query_text += f" (publication_date_range: {start or 'any'} to {end or 'any'})"
        if request.article_types:
            filtered_types = [t.strip() for t in request.article_types if t and t.strip()]
            if filtered_types:
                strict_query_text += f" (article_types: {', '.join(filtered_types)})"

        response = await service.process_query(query_text=strict_query_text)
        articles = _extract_literature_articles(response)
        used_fallback = False

        # If strict/filter-enriched query produced no evidence, retry with base query.
        # This prevents LLM query-planning over-constraint from wiping valid results.
        if not articles and strict_query_text != base_query_text:
            fallback_response = await service.process_query(query_text=base_query_text)
            fallback_articles = _extract_literature_articles(fallback_response)
            if fallback_articles:
                response = fallback_response
                articles = fallback_articles
                used_fallback = True

        response_payload = {
            "query": request.query,
            "query_mode": "fallback_broadened" if used_fallback else "strict",
            "total_results": len(articles),
            "articles": articles[: request.max_results],
            "papers": articles[: request.max_results],
            "evidence_summary": response.evidence_summary,
            "citations": [c.model_dump(mode="json") for c in response.citations],
        }
        await _log_audit_event(
            service,
            event_type="literature_search",
            action="search_literature",
            outcome="success",
            http_request=http_request,
            resource_type="literature",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Literature search completed",
            details={
                "query_length": len(request.query),
                "query_mode": response_payload["query_mode"],
                "total_results": len(articles),
                "returned_results": len(response_payload["articles"]),
            },
            data_sent_to_llm=True,
        )
        return response_payload

    except CDSSError as exc:
        await _log_audit_event(
            service,
            event_type="literature_search",
            action="search_literature",
            outcome="failure",
            http_request=http_request,
            resource_type="literature",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Literature search failed",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        raise HTTPException(status_code=500, detail=exc.message) from exc


@router.post(
    "/api/v1/search/protocols",
    tags=["Search"],
    summary="Search clinical protocols",
)
async def search_protocols(
    http_request: Request,
    request: ProtocolSearchRequest,
    service: ClinicalQueryService = Depends(get_query_service),
) -> dict:
    """Search treatment protocols and clinical guidelines.

    Routes the search through the orchestrator's protocol agent.

    Args:
        request: The protocol search request.
        service: Injected query service.

    Returns:
        Matching protocols with evidence grades and recommendations.
    """
    query_text = request.query
    if request.specialty:
        query_text += f" (specialty: {request.specialty})"
    if request.evidence_grade:
        query_text += f" (evidence grade: {request.evidence_grade})"

    try:
        response = await service.process_query(query_text=query_text)

        protocol_output = response.agent_outputs.get("protocol")
        protocols = []
        if protocol_output and protocol_output.raw_data:
            protocols = protocol_output.raw_data.get("protocols", [])

        response_payload = {
            "query": request.query,
            "specialty": request.specialty,
            "evidence_grade": request.evidence_grade,
            "total_results": len(protocols),
            "protocols": protocols,
            "summary": response.recommendation,
        }
        await _log_audit_event(
            service,
            event_type="protocol_search",
            action="search_protocols",
            outcome="success",
            http_request=http_request,
            resource_type="protocol",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Protocol search completed",
            details={
                "query_length": len(request.query),
                "total_results": len(protocols),
            },
            data_sent_to_llm=True,
        )
        return response_payload

    except CDSSError as exc:
        await _log_audit_event(
            service,
            event_type="protocol_search",
            action="search_protocols",
            outcome="failure",
            http_request=http_request,
            resource_type="protocol",
            resource_id=str(uuid4()),
            session_id=str(uuid4()),
            justification="Protocol search failed",
            details={"error": exc.message},
            data_sent_to_llm=True,
        )
        raise HTTPException(status_code=500, detail=exc.message) from exc


# ==========================================================================
# Admin / Health Endpoints
# ==========================================================================


@router.get(
    "/api/v1/health",
    tags=["System"],
    summary="Health check",
)
async def health_check() -> dict:
    """Health check endpoint.

    Returns basic service health information including version and status.

    Returns:
        Service health status dictionary.
    """
    service = get_query_service()
    orchestrator = getattr(service, "orchestrator", None)
    ingestion_service = getattr(service, "ingestion_service", None)
    pipeline = getattr(ingestion_service, "pipeline", None)

    services = {
        "orchestrator": "healthy" if orchestrator is not None else "degraded",
        "azure_openai": "healthy" if getattr(orchestrator, "openai_client", None) is not None else "degraded",
        "cosmos_db": "healthy" if service.cosmos_client is not None else "degraded",
        "ingestion_pipeline": "healthy" if ingestion_service is not None else "degraded",
        "azure_search": "healthy" if getattr(pipeline, "search_client", None) is not None else "degraded",
        "document_intelligence": (
            "healthy" if getattr(pipeline, "doc_intelligence_client", None) is not None else "degraded"
        ),
        "blob_storage": "healthy" if getattr(pipeline, "blob_client", None) is not None else "degraded",
    }
    overall_status = "healthy" if all(status == "healthy" for status in services.values()) else "degraded"

    return {
        "status": overall_status,
        "version": "0.1.0",
        "service": "cdss-agentic-rag",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


@router.get(
    "/api/v1/audit",
    tags=["Admin"],
    summary="Get audit trail",
)
async def get_audit_trail(
    patient_id: str | None = Query(None, description="Filter by patient ID."),
    date_from: str | None = Query(None, description="Start date filter (ISO 8601)."),
    date_to: str | None = Query(None, description="End date filter (ISO 8601)."),
    limit: int = Query(100, ge=1, le=1000, description="Max events to return."),
    service: ClinicalQueryService = Depends(get_query_service),
) -> list[dict]:
    """Retrieve the audit trail with optional filtering.

    Provides access to HIPAA-compliant audit log entries. In production,
    this endpoint should be restricted to admin roles.

    Args:
        patient_id: Optional patient ID filter.
        date_from: Optional start date.
        date_to: Optional end date.
        limit: Maximum number of entries.
        service: Injected query service.

    Returns:
        List of audit log entry dictionaries.
    """
    if service.cosmos_client is None:
        raise HTTPException(
            status_code=503,
            detail="Audit logging is not available (Cosmos DB not configured).",
        )

    try:
        trail = await service.cosmos_client.get_audit_trail(
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return trail

    except AzureServiceError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
