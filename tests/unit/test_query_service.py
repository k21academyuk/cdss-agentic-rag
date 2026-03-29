"""Tests for ClinicalQueryService runtime wiring and delegation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cdss.core.models import ClinicalQuery, ClinicalResponse
from cdss.services import query_service as query_service_module
from cdss.services.query_service import ClinicalQueryService


class _FakeOrchestrator:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.cosmos_client = None

    async def process_query(
        self,
        query: ClinicalQuery,
        clinician_id: str = "system",
    ) -> ClinicalResponse:
        return ClinicalResponse(
            assessment=f"Handled: {query.text}",
            recommendation="Stub recommendation",
            confidence_score=0.72,
        )


def test_default_service_builds_orchestrator_with_specialists(monkeypatch, mock_settings) -> None:
    monkeypatch.setattr(query_service_module, "PatientHistoryAgent", lambda settings: object())
    monkeypatch.setattr(query_service_module, "MedicalLiteratureAgent", lambda settings: object())
    monkeypatch.setattr(query_service_module, "ProtocolAgent", lambda settings: object())
    monkeypatch.setattr(query_service_module, "DrugSafetyAgent", lambda settings: object())
    monkeypatch.setattr(query_service_module, "GuardrailsAgent", lambda settings: object())
    monkeypatch.setattr(query_service_module, "OrchestratorAgent", _FakeOrchestrator)

    service = ClinicalQueryService(settings=mock_settings)

    assert isinstance(service.orchestrator, _FakeOrchestrator)
    assert service.orchestrator.kwargs["patient_history_agent"] is not None
    assert service.orchestrator.kwargs["literature_agent"] is not None
    assert service.orchestrator.kwargs["protocol_agent"] is not None
    assert service.orchestrator.kwargs["drug_safety_agent"] is not None
    assert service.orchestrator.kwargs["guardrails_agent"] is not None


@pytest.mark.asyncio
async def test_process_query_delegates_to_orchestrator(mock_settings) -> None:
    orchestrator = AsyncMock()
    orchestrator.process_query.return_value = ClinicalResponse(
        assessment="Delegated",
        recommendation="Delegated recommendation",
        confidence_score=0.8,
    )
    orchestrator.cosmos_client = None

    service = ClinicalQueryService(orchestrator=orchestrator, settings=mock_settings)

    result = await service.process_query(
        query_text="Evaluate CKD treatment options",
        patient_id="P-111",
        session_id="sess-111",
    )

    assert result.assessment == "Delegated"
    orchestrator.process_query.assert_called_once()
