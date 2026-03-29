"""Runtime-path tests for FastAPI routes.

These tests hit the real route handlers and request/response models while
stubbing only service-layer boundaries.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cdss.api.routes import _ingestion_status, router, set_query_service
from cdss.core.models import ClinicalResponse


class _StubIngestionService:
    def __init__(self) -> None:
        self.patient_ingest_calls: list[dict] = []
        self.protocol_ingest_calls: list[dict] = []

    async def ingest_patient_document(
        self,
        file_bytes: bytes,
        document_type: str,
        patient_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        self.patient_ingest_calls.append(
            {
                "bytes": len(file_bytes),
                "document_type": document_type,
                "patient_id": patient_id,
                "metadata": metadata or {},
            }
        )
        return {
            "document_id": "pipeline-patient-doc-1",
            "status": "completed",
            "message": "Patient document ingested.",
        }

    async def ingest_protocol(
        self,
        file_bytes: bytes,
        specialty: str,
        guideline_name: str,
        version: str,
        metadata: dict | None = None,
    ) -> dict:
        self.protocol_ingest_calls.append(
            {
                "bytes": len(file_bytes),
                "specialty": specialty,
                "guideline_name": guideline_name,
                "version": version,
                "metadata": metadata or {},
            }
        )
        return {
            "document_id": "pipeline-protocol-doc-1",
            "status": "completed",
            "message": "Protocol ingested.",
        }


class _StubCosmosClient:
    async def get_audit_trail(
        self,
        patient_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return [
            {
                "id": "audit-1",
                "patient_id": patient_id,
                "action": "query_processed",
                "limit": limit,
                "date_from": date_from,
                "date_to": date_to,
            }
        ]


class _StubQueryService:
    def __init__(self) -> None:
        self.ingestion_service = _StubIngestionService()
        self.cosmos_client = _StubCosmosClient()
        self.last_query_payload: dict | None = None
        self.last_search_payload: dict | None = None

    async def process_query(
        self,
        query_text: str,
        patient_id: str | None = None,
        session_id: str | None = None,
        clinician_id: str = "system",
    ) -> ClinicalResponse:
        self.last_query_payload = {
            "query_text": query_text,
            "patient_id": patient_id,
            "session_id": session_id,
            "clinician_id": clinician_id,
        }
        return ClinicalResponse(
            assessment="Assessment from stub service.",
            recommendation="Recommendation from stub service.",
            confidence_score=0.81,
        )

    async def search_patients(
        self,
        search: str | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> dict:
        self.last_search_payload = {
            "search": search,
            "page": page,
            "limit": limit,
        }
        return {
            "patients": [
                {
                    "id": "patient-1",
                    "patient_id": "P-12345",
                    "doc_type": "patient_profile",
                }
            ],
            "page": page,
            "page_size": limit,
            "limit": limit,
            "total": 1,
        }

    async def get_patient_profile(self, patient_id: str) -> dict | None:
        return {
            "id": patient_id,
            "patient_id": patient_id,
            "doc_type": "patient_profile",
        }

    async def update_patient_profile(self, patient_id: str, profile_data: dict) -> dict:
        output = dict(profile_data)
        output["patient_id"] = patient_id
        return output

    async def get_conversation_history(self, session_id: str, limit: int = 20) -> list[dict]:
        return [{"session_id": session_id, "id": "turn-1"}]

    async def submit_feedback(
        self,
        conversation_id: str,
        rating: int,
        correction: str | None = None,
    ) -> dict:
        return {
            "conversation_id": conversation_id,
            "rating": rating,
            "correction": correction,
            "status": "saved",
        }


@pytest.fixture
def stub_service() -> _StubQueryService:
    return _StubQueryService()


@pytest.fixture
def client(stub_service: _StubQueryService) -> TestClient:
    _ingestion_status.clear()
    set_query_service(stub_service)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_submit_query_uses_real_route_and_schema(client: TestClient, stub_service: _StubQueryService) -> None:
    response = client.post(
        "/api/v1/query",
        json={
            "text": "What is the mechanism of metformin?",
            "patient_id": "P-12345",
            "session_id": "sess-api-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["confidence_score"] == 0.81
    assert stub_service.last_query_payload == {
        "query_text": "What is the mechanism of metformin?",
        "patient_id": "P-12345",
        "session_id": "sess-api-1",
        "clinician_id": "system",
    }


def test_search_patients_calls_service_layer(client: TestClient, stub_service: _StubQueryService) -> None:
    response = client.get("/api/v1/patients?search=diabetes&page=2&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["patients"][0]["patient_id"] == "P-12345"
    assert stub_service.last_search_payload == {
        "search": "diabetes",
        "page": 2,
        "limit": 5,
    }


def test_document_ingestion_uses_service_instead_of_placeholder(
    client: TestClient, stub_service: _StubQueryService
) -> None:
    response = client.post(
        "/api/v1/documents/ingest?document_type=patient_record&patient_id=P-12345",
        files={"file": ("patient-note.txt", b"Patient has T2DM and CKD.", "text/plain")},
    )

    assert response.status_code == 200
    ingest = response.json()
    assert ingest["status"] == "pending"

    status_response = client.get(f"/api/v1/documents/{ingest['document_id']}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert stub_service.ingestion_service.patient_ingest_calls


def test_health_endpoint_real_route(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cdss-agentic-rag"


def test_audit_endpoint_uses_cosmos_client(client: TestClient) -> None:
    response = client.get("/api/v1/audit?patient_id=P-12345&limit=10")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["patient_id"] == "P-12345"
    assert data[0]["limit"] == 10
