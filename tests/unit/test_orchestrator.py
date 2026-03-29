"""Runtime-path tests for the real OrchestratorAgent.

These tests exercise concrete orchestrator behavior while stubbing only
external service boundaries.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from cdss.agents.orchestrator import OrchestratorAgent
from cdss.core.models import AgentOutput, AgentTask, ClinicalQuery, ClinicalResponse


def _agent_task(to_agent: str, payload: dict | None = None) -> AgentTask:
    return AgentTask(
        from_agent="orchestrator",
        to_agent=to_agent,
        message_type="task_request",
        payload=payload or {"query": "test"},
        session_id="sess-test",
        trace_id="trace-test",
    )


class _ProcessOnlyAgent:
    """Legacy agent shape used by older call sites."""

    def __init__(self, result: AgentOutput) -> None:
        self.process = AsyncMock(return_value=result)


@pytest.mark.asyncio
async def test_execute_agent_uses_execute_contract(mock_settings) -> None:
    expected = AgentOutput(
        agent_name="patient_history",
        latency_ms=5,
        sources_retrieved=2,
        summary="Patient context loaded.",
        raw_data={"summary": "Patient context loaded.", "sources_retrieved": 2},
    )

    patient_history_agent = AsyncMock()
    patient_history_agent.execute = AsyncMock(return_value=expected)

    orchestrator = OrchestratorAgent(
        patient_history_agent=patient_history_agent,
        openai_client=AsyncMock(),
        cosmos_client=None,
        settings=mock_settings,
    )

    result = await orchestrator._execute_agent(
        agent_name="patient_history",
        task=_agent_task("patient_history", {"query": "patient context", "patient_id": "P-123"}),
        timeout=2,
    )

    patient_history_agent.execute.assert_called_once()
    assert result.summary == "Patient context loaded."
    assert result.sources_retrieved == 2


@pytest.mark.asyncio
async def test_execute_agent_supports_legacy_process_contract(mock_settings) -> None:
    expected = AgentOutput(
        agent_name="literature",
        latency_ms=7,
        sources_retrieved=1,
        summary="One paper found.",
        raw_data={"summary": "One paper found.", "sources_retrieved": 1},
    )

    legacy_agent = _ProcessOnlyAgent(expected)
    orchestrator = OrchestratorAgent(
        literature_agent=legacy_agent,
        openai_client=AsyncMock(),
        cosmos_client=None,
        settings=mock_settings,
    )

    result = await orchestrator._execute_agent(
        agent_name="literature",
        task=_agent_task("literature", {"query": "latest CKD evidence"}),
        timeout=2,
    )

    legacy_agent.process.assert_called_once()
    assert result.summary == "One paper found."


@pytest.mark.asyncio
async def test_validate_response_parses_guardrails_agent_output(mock_settings) -> None:
    guardrails_output = AgentOutput(
        agent_name="guardrails_agent",
        latency_ms=9,
        sources_retrieved=0,
        summary="Validation failed.",
        raw_data={
            "guardrails_result": {
                "is_valid": False,
                "hallucination_flags": ["unsupported dosing claim"],
                "safety_concerns": ["contraindicated combination"],
                "disclaimers": ["Manual physician verification required."],
            }
        },
    )

    guardrails_agent = AsyncMock()
    guardrails_agent.execute = AsyncMock(return_value=guardrails_output)

    orchestrator = OrchestratorAgent(
        guardrails_agent=guardrails_agent,
        openai_client=AsyncMock(),
        cosmos_client=None,
        settings=mock_settings,
    )

    response = ClinicalResponse(
        assessment="Test assessment",
        recommendation="Test recommendation",
        confidence_score=0.9,
    )

    validated = await orchestrator._validate_response(response=response, agent_outputs={})

    assert validated.confidence_score < 0.9
    assert any(d.startswith("SAFETY CONCERN:") for d in validated.disclaimers)
    assert any(d.startswith("VERIFICATION NEEDED:") for d in validated.disclaimers)
    assert "Manual physician verification required." in validated.disclaimers


@pytest.mark.asyncio
async def test_process_query_end_to_end_with_real_orchestrator_paths(mock_settings) -> None:
    openai_client = AsyncMock()
    openai_client.classify_query.return_value = {
        "query_type": "general",
        "entities": [],
        "required_agents": ["literature"],
    }
    openai_client.chat_completion.side_effect = [
        {
            "content": json.dumps(
                {
                    "query_type": "general",
                    "required_agents": ["literature"],
                    "sub_queries": {"literature": "metformin mechanism"},
                    "priority": "medium",
                    "parallel_dispatch": True,
                }
            )
        },
        {
            "content": json.dumps(
                {
                    "assessment": "Pharmacology overview requested.",
                    "recommendation": "Metformin lowers hepatic gluconeogenesis and improves insulin sensitivity.",
                    "evidence_summary": ["Mechanistic studies support reduced hepatic glucose output."],
                    "confidence_score": 0.78,
                    "citations": [],
                }
            )
        },
    ]

    literature_agent = AsyncMock()
    literature_agent.execute = AsyncMock(
        return_value=AgentOutput(
            agent_name="medical_literature_agent",
            latency_ms=20,
            sources_retrieved=3,
            summary="Mechanism papers retrieved.",
            raw_data={"summary": "Mechanism papers retrieved.", "sources_retrieved": 3},
        )
    )

    guardrails_agent = AsyncMock()
    guardrails_agent.execute = AsyncMock(
        return_value=AgentOutput(
            agent_name="guardrails_agent",
            latency_ms=8,
            sources_retrieved=0,
            summary="Validation passed.",
            raw_data={
                "guardrails_result": {
                    "is_valid": True,
                    "hallucination_flags": [],
                    "safety_concerns": [],
                    "disclaimers": ["Reviewed by automated guardrails."],
                }
            },
        )
    )

    orchestrator = OrchestratorAgent(
        literature_agent=literature_agent,
        guardrails_agent=guardrails_agent,
        openai_client=openai_client,
        cosmos_client=None,
        settings=mock_settings,
    )

    query = ClinicalQuery(text="How does metformin work?", session_id="sess-runtime-1")
    response = await orchestrator.process_query(query)

    assert response.assessment == "Pharmacology overview requested."
    assert "metformin" in response.recommendation.lower()
    assert "literature" in response.agent_outputs
    assert "Reviewed by automated guardrails." in response.disclaimers
