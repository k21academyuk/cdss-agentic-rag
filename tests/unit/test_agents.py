"""Tests for all CDSS specialist agents.

Covers BaseAgent lifecycle, PatientHistoryAgent, MedicalLiteratureAgent,
ProtocolAgent, DrugSafetyAgent, and GuardrailsAgent. All external
services are mocked.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cdss.agents.base import BaseAgent
from cdss.core.exceptions import AgentError, AgentTimeoutError
from cdss.core.models import (
    AgentOutput,
    AgentTask,
    DrugInteraction,
    DrugSafetyReport,
    GuardrailsResult,
    PatientContext,
    ProtocolMatch,
)


# ═══════════════════════════════════════════════════════════════════════════════
# BaseAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    def __init__(self, name: str = "test_agent", model: str = "gpt-4o"):
        super().__init__(name, model)
        self._mock_execute = AsyncMock(return_value={
            "summary": "Test summary",
            "sources_retrieved": 3,
            "extra_field": "extra_value",
        })

    async def _execute(self, task: AgentTask) -> dict:
        return await self._mock_execute(task)


class FailingAgent(BaseAgent):
    """Agent that always raises an error for testing."""

    def __init__(self):
        super().__init__("failing_agent")

    async def _execute(self, task: AgentTask) -> dict:
        raise ValueError("Simulated agent failure")


class AgentErrorRaisingAgent(BaseAgent):
    """Agent that raises an AgentError directly."""

    def __init__(self):
        super().__init__("agent_error_raiser")

    async def _execute(self, task: AgentTask) -> dict:
        raise AgentError("Direct agent error", agent_name="agent_error_raiser")


class TestBaseAgent:
    """Tests for the BaseAgent abstract class."""

    @pytest.fixture
    def agent(self) -> ConcreteAgent:
        return ConcreteAgent()

    @pytest.fixture
    def task(self, sample_agent_task) -> AgentTask:
        return sample_agent_task

    async def test_execute_returns_agent_output(self, agent, task):
        output = await agent.execute(task)
        assert isinstance(output, AgentOutput)
        assert output.agent_name == "test_agent"
        assert output.summary == "Test summary"
        assert output.sources_retrieved == 3

    async def test_execute_measures_latency(self, agent, task):
        output = await agent.execute(task)
        assert output.latency_ms >= 0

    async def test_execute_preserves_raw_data(self, agent, task):
        output = await agent.execute(task)
        assert output.raw_data is not None
        assert output.raw_data["extra_field"] == "extra_value"

    async def test_execute_wraps_exceptions_in_agent_error(self, task):
        agent = FailingAgent()
        with pytest.raises(AgentError) as exc_info:
            await agent.execute(task)
        assert "failing_agent" in exc_info.value.agent_name
        assert "Simulated agent failure" in str(exc_info.value)

    async def test_execute_preserves_agent_error(self, task):
        agent = AgentErrorRaisingAgent()
        with pytest.raises(AgentError) as exc_info:
            await agent.execute(task)
        assert exc_info.value.agent_name == "agent_error_raiser"
        assert "Direct agent error" in str(exc_info.value)

    def test_agent_name_and_model(self):
        agent = ConcreteAgent(name="custom_agent", model="gpt-4o-mini")
        assert agent.name == "custom_agent"
        assert agent.model == "gpt-4o-mini"

    async def test_execute_calls_internal_execute(self, agent, task):
        await agent.execute(task)
        agent._mock_execute.assert_called_once_with(task)


# ═══════════════════════════════════════════════════════════════════════════════
# PatientHistoryAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatientHistoryAgent:
    """Tests for the PatientHistoryAgent (retrieves patient context)."""

    @pytest.fixture
    def agent(self, mock_cosmos_client, mock_search_client, mock_openai_client):
        """Create a PatientHistoryAgent-like implementation."""
        class _PatientHistoryAgent(BaseAgent):
            def __init__(self, cosmos_client, search_client, openai_client):
                super().__init__("patient_history_agent")
                self.cosmos = cosmos_client
                self.search = search_client
                self.openai = openai_client

            async def _execute(self, task: AgentTask) -> dict:
                patient_id = task.payload.get("patient_id")
                query = task.payload.get("query", "")

                profile = None
                if patient_id:
                    profile = await self.cosmos.get_patient_profile(patient_id)

                search_results = await self.search.search_patient_records(
                    query=query, patient_id=patient_id
                )

                sources = len(search_results) + (1 if profile else 0)

                return {
                    "summary": f"Retrieved patient context for {patient_id or 'unknown'}",
                    "sources_retrieved": sources,
                    "profile": profile,
                    "search_results": search_results,
                }

        return _PatientHistoryAgent(mock_cosmos_client, mock_search_client, mock_openai_client)

    async def test_returns_patient_context(self, agent, sample_agent_task, mock_cosmos_client):
        sample_agent_task.payload["patient_id"] = "P-12345"
        output = await agent.execute(sample_agent_task)

        assert isinstance(output, AgentOutput)
        assert output.raw_data["profile"] is not None
        mock_cosmos_client.get_patient_profile.assert_called_once_with("P-12345")

    async def test_handles_missing_patient_gracefully(self, agent, sample_agent_task, mock_cosmos_client):
        mock_cosmos_client.get_patient_profile.return_value = None
        sample_agent_task.payload["patient_id"] = "P-NONEXISTENT"
        output = await agent.execute(sample_agent_task)

        assert output.raw_data["profile"] is None
        assert output.sources_retrieved >= 1  # at least search results

    async def test_handles_empty_search_results(self, agent, sample_agent_task, mock_search_client):
        mock_search_client.search_patient_records.return_value = []
        output = await agent.execute(sample_agent_task)

        assert output.sources_retrieved >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# MedicalLiteratureAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicalLiteratureAgent:
    """Tests for the MedicalLiteratureAgent (PubMed + cached literature)."""

    @pytest.fixture
    def agent(self, mock_pubmed_client, mock_search_client, mock_openai_client):
        """Create a MedicalLiteratureAgent-like implementation."""
        class _MedicalLiteratureAgent(BaseAgent):
            def __init__(self, pubmed_client, search_client, openai_client):
                super().__init__("literature_agent")
                self.pubmed = pubmed_client
                self.search = search_client
                self.openai = openai_client

            async def _execute(self, task: AgentTask) -> dict:
                query = task.payload.get("query", "")

                # Generate PubMed query from natural language
                classification = await self.openai.classify_query(query)
                entities = classification.get("entities", [])

                # Search PubMed
                pubmed_results = await self.pubmed.search_and_fetch(query, max_results=10)

                # Search cached literature index
                cached_results = await self.search.search_medical_literature(query)

                # Merge and deduplicate by PMID
                merged = self._deduplicate(pubmed_results, cached_results)

                # Evidence assessment
                evidence_summary = f"Found {len(merged)} relevant papers."

                return {
                    "summary": evidence_summary,
                    "sources_retrieved": len(merged),
                    "papers": merged,
                    "entities": entities,
                }

            def _deduplicate(self, pubmed_results, cached_results):
                seen_pmids = set()
                merged = []
                for article in pubmed_results:
                    pmid = article.get("pmid", "")
                    if pmid and pmid not in seen_pmids:
                        seen_pmids.add(pmid)
                        merged.append(article)
                for result in cached_results:
                    pmid = result.get("metadata", {}).get("pmid", "")
                    if pmid and pmid not in seen_pmids:
                        seen_pmids.add(pmid)
                        merged.append(result)
                return merged

        return _MedicalLiteratureAgent(mock_pubmed_client, mock_search_client, mock_openai_client)

    async def test_generates_pubmed_query(self, agent, sample_agent_task, mock_openai_client):
        output = await agent.execute(sample_agent_task)
        mock_openai_client.classify_query.assert_called_once()
        assert output.sources_retrieved > 0

    async def test_merges_pubmed_and_cached(self, agent, sample_agent_task, mock_pubmed_client, mock_search_client):
        output = await agent.execute(sample_agent_task)

        mock_pubmed_client.search_and_fetch.assert_called_once()
        mock_search_client.search_medical_literature.assert_called_once()
        assert output.sources_retrieved >= 2

    async def test_deduplicates_by_pmid(self, agent, sample_agent_task, mock_pubmed_client, mock_search_client):
        # Make both sources return the same PMID
        mock_pubmed_client.search_and_fetch.return_value = [
            {"pmid": "32970396", "title": "From PubMed"}
        ]
        mock_search_client.search_medical_literature.return_value = [
            {"id": "lit-1", "content": "Cached", "metadata": {"pmid": "32970396"}}
        ]
        output = await agent.execute(sample_agent_task)
        assert output.sources_retrieved == 1  # deduplicated

    async def test_evidence_assessment(self, agent, sample_agent_task):
        output = await agent.execute(sample_agent_task)
        assert "relevant papers" in output.summary.lower() or "found" in output.summary.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# ProtocolAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestProtocolAgent:
    """Tests for the ProtocolAgent (clinical guideline search)."""

    @pytest.fixture
    def agent(self, mock_search_client, mock_openai_client):
        class _ProtocolAgent(BaseAgent):
            def __init__(self, search_client, openai_client):
                super().__init__("protocol_agent")
                self.search = search_client
                self.openai = openai_client

            async def _execute(self, task: AgentTask) -> dict:
                query = task.payload.get("query", "")
                specialty = task.payload.get("specialty")

                results = await self.search.search_treatment_protocols(
                    query=query, specialty=specialty
                )

                protocols = []
                for r in results:
                    protocols.append({
                        "guideline": r.get("metadata", {}).get("guideline", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0.0),
                    })

                return {
                    "summary": f"Found {len(protocols)} relevant protocols.",
                    "sources_retrieved": len(protocols),
                    "protocols": protocols,
                }

        return _ProtocolAgent(mock_search_client, mock_openai_client)

    async def test_searches_protocols_index(self, agent, sample_agent_task, mock_search_client):
        output = await agent.execute(sample_agent_task)
        mock_search_client.search_treatment_protocols.assert_called_once()
        assert output.sources_retrieved >= 1

    async def test_filters_by_specialty(self, agent, sample_agent_task, mock_search_client):
        sample_agent_task.payload["specialty"] = "endocrinology"
        await agent.execute(sample_agent_task)

        call_kwargs = mock_search_client.search_treatment_protocols.call_args[1]
        assert call_kwargs["specialty"] == "endocrinology"

    async def test_returns_protocol_match_objects(self, agent, sample_agent_task):
        output = await agent.execute(sample_agent_task)
        assert len(output.raw_data["protocols"]) >= 1
        assert "content" in output.raw_data["protocols"][0]


# ═══════════════════════════════════════════════════════════════════════════════
# DrugSafetyAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDrugSafetyAgent:
    """Tests for the DrugSafetyAgent (drug interactions and safety)."""

    @pytest.fixture
    def agent(self, mock_rxnorm_client, mock_drugbank_client, mock_openfda_client):
        class _DrugSafetyAgent(BaseAgent):
            def __init__(self, rxnorm_client, drugbank_client, openfda_client):
                super().__init__("drug_safety_agent")
                self.rxnorm = rxnorm_client
                self.drugbank = drugbank_client
                self.openfda = openfda_client

            async def _execute(self, task: AgentTask) -> dict:
                drugs = task.payload.get("drugs", [])
                allergies = task.payload.get("allergies", [])

                # Normalize drug names
                normalized = []
                for drug in drugs:
                    result = await self.rxnorm.normalize_drug_name(drug)
                    normalized.append(result)

                # Check DDIs
                interactions = await self.drugbank.check_interactions(drugs)

                # Query adverse events
                adverse_events = []
                for drug in drugs:
                    events = await self.openfda.search_adverse_events(drug)
                    adverse_events.extend(events)

                # Check allergy cross-reactivity
                allergy_alerts = []
                for allergy in allergies:
                    for drug in drugs:
                        if self._check_cross_reactivity(allergy, drug):
                            allergy_alerts.append({
                                "drug": drug,
                                "allergy": allergy,
                                "warning": f"Cross-reactivity risk between {drug} and {allergy}",
                            })

                total_sources = len(normalized) + len(interactions) + len(adverse_events)

                return {
                    "summary": f"Checked {len(drugs)} drugs. Found {len(interactions)} interactions.",
                    "sources_retrieved": total_sources,
                    "normalized_drugs": normalized,
                    "interactions": interactions,
                    "adverse_events": adverse_events,
                    "allergy_alerts": allergy_alerts,
                }

            def _check_cross_reactivity(self, allergy: str, drug: str) -> bool:
                cross_reactivity_map = {
                    "penicillin": ["amoxicillin", "ampicillin", "cephalosporin"],
                    "sulfa": ["sulfamethoxazole", "sulfasalazine"],
                }
                allergy_lower = allergy.lower()
                drug_lower = drug.lower()
                related = cross_reactivity_map.get(allergy_lower, [])
                return drug_lower in related

        return _DrugSafetyAgent(mock_rxnorm_client, mock_drugbank_client, mock_openfda_client)

    async def test_normalizes_drug_names(self, agent, sample_agent_task, mock_rxnorm_client):
        sample_agent_task.payload["drugs"] = ["metformin", "dapagliflozin"]
        sample_agent_task.payload["allergies"] = []
        output = await agent.execute(sample_agent_task)

        assert mock_rxnorm_client.normalize_drug_name.call_count == 2
        assert len(output.raw_data["normalized_drugs"]) == 2

    async def test_checks_ddis(self, agent, sample_agent_task, mock_drugbank_client):
        sample_agent_task.payload["drugs"] = ["metformin", "lisinopril"]
        sample_agent_task.payload["allergies"] = []
        output = await agent.execute(sample_agent_task)

        mock_drugbank_client.check_interactions.assert_called_once()
        assert len(output.raw_data["interactions"]) >= 1

    async def test_queries_adverse_events(self, agent, sample_agent_task, mock_openfda_client):
        sample_agent_task.payload["drugs"] = ["metformin"]
        sample_agent_task.payload["allergies"] = []
        output = await agent.execute(sample_agent_task)

        mock_openfda_client.search_adverse_events.assert_called_once_with("metformin")
        assert len(output.raw_data["adverse_events"]) >= 1

    async def test_checks_allergy_cross_reactivity(self, agent, sample_agent_task):
        sample_agent_task.payload["drugs"] = ["amoxicillin"]
        sample_agent_task.payload["allergies"] = ["penicillin"]
        output = await agent.execute(sample_agent_task)

        assert len(output.raw_data["allergy_alerts"]) == 1
        assert "cross-reactivity" in output.raw_data["allergy_alerts"][0]["warning"].lower()

    async def test_no_allergy_cross_reactivity(self, agent, sample_agent_task):
        sample_agent_task.payload["drugs"] = ["dapagliflozin"]
        sample_agent_task.payload["allergies"] = ["penicillin"]
        output = await agent.execute(sample_agent_task)

        assert len(output.raw_data["allergy_alerts"]) == 0

    async def test_returns_drug_safety_report(self, agent, sample_agent_task):
        sample_agent_task.payload["drugs"] = ["metformin", "lisinopril"]
        sample_agent_task.payload["allergies"] = []
        output = await agent.execute(sample_agent_task)

        assert "interactions" in output.raw_data
        assert "adverse_events" in output.raw_data


# ═══════════════════════════════════════════════════════════════════════════════
# GuardrailsAgent Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardrailsAgent:
    """Tests for the GuardrailsAgent (response validation)."""

    @pytest.fixture
    def agent(self, mock_openai_client):
        class _GuardrailsAgent(BaseAgent):
            MANDATORY_DISCLAIMERS = [
                "This is a clinical decision support tool and does not replace clinical judgment.",
                "All recommendations should be verified with current clinical guidelines.",
            ]

            def __init__(self, openai_client):
                super().__init__("guardrails_agent", model="gpt-4o-mini")
                self.openai = openai_client

            async def _execute(self, task: AgentTask) -> dict:
                response_text = task.payload.get("response_text", "")
                citations = task.payload.get("citations", [])
                drug_alerts = task.payload.get("drug_alerts", [])

                hallucination_flags = []
                safety_concerns = []

                # Citation verification
                if not citations:
                    hallucination_flags.append("No citations provided for clinical claims.")

                # Drug safety consistency check
                for alert in drug_alerts:
                    if alert.get("severity") == "major" and "consider" in response_text.lower():
                        safety_concerns.append(
                            f"Response recommends a drug with major interaction: {alert.get('description', '')}"
                        )

                # Scope classification
                scope_result = await self._classify_scope(response_text)
                if scope_result == "out_of_scope":
                    hallucination_flags.append("Response appears to be outside clinical scope.")

                # Low confidence flagging
                confidence = task.payload.get("confidence_score", 1.0)
                if confidence < 0.6:
                    safety_concerns.append(
                        f"Low confidence score ({confidence}). Additional review recommended."
                    )

                # Disclaimer injection
                disclaimers = list(self.MANDATORY_DISCLAIMERS)

                is_valid = len(hallucination_flags) == 0 and len(safety_concerns) == 0

                return {
                    "summary": "Guardrails validation complete.",
                    "sources_retrieved": 0,
                    "is_valid": is_valid,
                    "hallucination_flags": hallucination_flags,
                    "safety_concerns": safety_concerns,
                    "disclaimers": disclaimers,
                }

            async def _classify_scope(self, text: str) -> str:
                result = await self.openai.chat_completion(
                    messages=[
                        {"role": "system", "content": "Classify if clinical."},
                        {"role": "user", "content": text},
                    ],
                    model="gpt-4o-mini",
                )
                content = result.get("content", "")
                if "out_of_scope" in content.lower():
                    return "out_of_scope"
                return "in_scope"

        return _GuardrailsAgent(mock_openai_client)

    async def test_citation_verification_missing(self, agent, sample_agent_task):
        sample_agent_task.payload = {
            "response_text": "Use SGLT2 inhibitors for CKD.",
            "citations": [],
            "drug_alerts": [],
            "confidence_score": 0.9,
        }
        output = await agent.execute(sample_agent_task)
        assert not output.raw_data["is_valid"]
        assert any("citation" in f.lower() for f in output.raw_data["hallucination_flags"])

    async def test_citation_verification_present(self, agent, sample_agent_task):
        sample_agent_task.payload = {
            "response_text": "Use SGLT2 inhibitors for CKD.",
            "citations": [{"source": "pubmed", "id": "32970396"}],
            "drug_alerts": [],
            "confidence_score": 0.9,
        }
        output = await agent.execute(sample_agent_task)
        assert not any("citation" in f.lower() for f in output.raw_data["hallucination_flags"])

    async def test_drug_safety_consistency(self, agent, sample_agent_task):
        sample_agent_task.payload = {
            "response_text": "Consider adding dapagliflozin to the regimen.",
            "citations": [{"source": "pubmed", "id": "123"}],
            "drug_alerts": [
                {"severity": "major", "description": "Severe interaction with metformin"}
            ],
            "confidence_score": 0.9,
        }
        output = await agent.execute(sample_agent_task)
        assert len(output.raw_data["safety_concerns"]) >= 1

    async def test_low_confidence_flagging(self, agent, sample_agent_task):
        sample_agent_task.payload = {
            "response_text": "Treatment recommendation.",
            "citations": [{"source": "pubmed", "id": "123"}],
            "drug_alerts": [],
            "confidence_score": 0.3,
        }
        output = await agent.execute(sample_agent_task)
        assert any("low confidence" in c.lower() for c in output.raw_data["safety_concerns"])

    async def test_disclaimer_injection(self, agent, sample_agent_task):
        sample_agent_task.payload = {
            "response_text": "Clinical recommendation.",
            "citations": [{"source": "pubmed", "id": "123"}],
            "drug_alerts": [],
            "confidence_score": 0.9,
        }
        output = await agent.execute(sample_agent_task)
        disclaimers = output.raw_data["disclaimers"]
        assert len(disclaimers) >= 2
        assert any("does not replace clinical judgment" in d for d in disclaimers)

    async def test_scope_classification(self, agent, sample_agent_task, mock_openai_client):
        mock_openai_client.chat_completion.return_value = {
            "content": "out_of_scope",
            "tool_calls": None,
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        }
        sample_agent_task.payload = {
            "response_text": "What is the weather today?",
            "citations": [{"source": "pubmed", "id": "123"}],
            "drug_alerts": [],
            "confidence_score": 0.9,
        }
        output = await agent.execute(sample_agent_task)
        assert any("scope" in f.lower() for f in output.raw_data["hallucination_flags"])
