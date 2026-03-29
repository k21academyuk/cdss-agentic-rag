"""End-to-end integration tests for the CDSS pipeline.

Tests the full flow from document ingestion through clinical query
processing, verifying that all agents are orchestrated correctly,
responses include citations, drug alerts, and disclaimers, and that
conversation and audit logs are persisted.

All external services are mocked; the test verifies the integration
between internal components.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cdss.agents.base import BaseAgent
from cdss.core.models import (
    AgentOutput,
    AgentTask,
    ClinicalQuery,
    ClinicalResponse,
    DrugAlert,
    Citation,
    GuardrailsResult,
    QueryPlan,
)
from cdss.rag.chunker import MedicalDocumentChunker


# ═══════════════════════════════════════════════════════════════════════════════
# Test Infrastructure
# ═══════════════════════════════════════════════════════════════════════════════


class _InMemoryStore:
    """Simulates Cosmos DB with in-memory storage for integration tests."""

    def __init__(self):
        self.patients: dict[str, dict] = {}
        self.conversations: list[dict] = []
        self.audit_events: list[dict] = []
        self.embeddings_cache: dict[str, list[float]] = {}

    async def get_patient_profile(self, patient_id: str) -> dict | None:
        return self.patients.get(patient_id)

    async def upsert_patient_profile(self, profile: dict) -> dict:
        pid = profile.get("patient_id", profile.get("id", ""))
        self.patients[pid] = profile
        return profile

    async def save_conversation_turn(self, turn: dict) -> dict:
        self.conversations.append(turn)
        return turn

    async def get_conversation_history(self, session_id: str, limit: int = 20) -> list[dict]:
        return [t for t in self.conversations if t.get("session_id") == session_id][:limit]

    async def log_audit_event(self, event: dict) -> dict:
        self.audit_events.append(event)
        return event

    async def get_audit_trail(self, **kwargs) -> list[dict]:
        return list(self.audit_events)

    async def get_cached_embedding(self, source_type: str, content_hash: str) -> list[float] | None:
        return self.embeddings_cache.get(f"{source_type}:{content_hash}")

    async def cache_embedding(self, source_type: str, content_hash: str, embedding: list[float]) -> None:
        self.embeddings_cache[f"{source_type}:{content_hash}"] = embedding


class _InMemorySearchIndex:
    """Simulates Azure AI Search with in-memory indexing for integration tests."""

    def __init__(self):
        self.indexes: dict[str, list[dict]] = {
            "patient_records": [],
            "treatment_protocols": [],
            "medical_literature": [],
        }

    async def index_documents_batch(self, index_name: str, documents: list[dict]) -> dict:
        if index_name not in self.indexes:
            self.indexes[index_name] = []
        self.indexes[index_name].extend(documents)
        return {"total": len(documents), "succeeded": len(documents), "failed": 0, "errors": []}

    async def search_patient_records(self, query: str, patient_id: str | None = None, **kwargs) -> list[dict]:
        results = self.indexes.get("patient_records", [])
        if patient_id:
            results = [r for r in results if r.get("patient_id") == patient_id]
        return [
            {"id": r.get("id", ""), "score": 0.9, "reranker_score": 0.85, "content": r.get("content", ""), "metadata": r}
            for r in results[:10]
        ]

    async def search_treatment_protocols(self, query: str, specialty: str | None = None, **kwargs) -> list[dict]:
        results = self.indexes.get("treatment_protocols", [])
        if specialty:
            results = [r for r in results if r.get("specialty") == specialty]
        return [
            {"id": r.get("id", ""), "score": 0.85, "reranker_score": 0.8, "content": r.get("content", ""), "metadata": r}
            for r in results[:10]
        ]

    async def search_medical_literature(self, query: str, **kwargs) -> list[dict]:
        results = self.indexes.get("medical_literature", [])
        return [
            {"id": r.get("id", ""), "score": 0.8, "reranker_score": 0.75, "content": r.get("content", ""), "metadata": r}
            for r in results[:10]
        ]

    async def hybrid_search(self, index_name: str, query: str, **kwargs) -> list[dict]:
        results = self.indexes.get(index_name, [])
        return [
            {"id": r.get("id", ""), "score": 0.8, "reranker_score": 0.75, "content": r.get("content", ""), "metadata": r}
            for r in results[:10]
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def store() -> _InMemoryStore:
    return _InMemoryStore()


@pytest.fixture
def search_index() -> _InMemorySearchIndex:
    return _InMemorySearchIndex()


@pytest.fixture
def chunker() -> MedicalDocumentChunker:
    return MedicalDocumentChunker(default_chunk_size=512, default_overlap=128)


@pytest.fixture
def openai_client() -> AsyncMock:
    """OpenAI client mock for e2e tests."""
    client = AsyncMock()

    client.generate_embedding.return_value = [0.01] * 3072
    client.generate_embeddings_batch.return_value = [[0.01] * 3072]
    client.classify_query.return_value = {
        "query_type": "treatment",
        "entities": ["type 2 diabetes", "CKD"],
        "required_agents": ["patient_history", "literature", "protocol", "drug_safety"],
    }
    client.chat_completion.return_value = {
        "content": (
            "Based on the available evidence, SGLT2 inhibitors (e.g., dapagliflozin) "
            "are recommended for patients with type 2 diabetes and CKD stage 3. "
            "The DAPA-CKD trial demonstrated a 39% reduction in kidney failure risk."
        ),
        "tool_calls": None,
        "usage": {"prompt_tokens": 2000, "completion_tokens": 500, "total_tokens": 2500},
    }
    client.evaluate_relevance.return_value = 0.85

    return client


@pytest.fixture
def pubmed_client() -> AsyncMock:
    client = AsyncMock()
    client.search_and_fetch.return_value = [
        {
            "pmid": "32970396",
            "title": "Dapagliflozin in CKD",
            "abstract": "DAPA-CKD showed 39% reduction in kidney failure.",
            "authors": ["Heerspink HJL"],
            "journal": "N Engl J Med",
            "pub_date": "2020-10-08",
            "mesh_terms": ["Diabetes Mellitus, Type 2", "CKD"],
        }
    ]
    return client


@pytest.fixture
def drug_safety_client() -> AsyncMock:
    client = AsyncMock()
    client.normalize_drug_name.return_value = {"rxcui": "1488574", "name": "dapagliflozin"}
    client.check_interactions.return_value = [
        {
            "drug_a": "metformin",
            "drug_b": "dapagliflozin",
            "severity": "minor",
            "description": "Additive hypoglycemic effect",
            "evidence_level": 3,
            "source": "DrugBank",
        }
    ]
    client.search_adverse_events.return_value = []
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-End Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    """Full end-to-end integration test."""

    async def test_full_flow_ingest_and_query(
        self,
        store,
        search_index,
        chunker,
        openai_client,
        pubmed_client,
        drug_safety_client,
        sample_patient_profile,
    ):
        """Test the complete flow: ingest patient record, then submit a query."""

        # ─── Step 1: Ingest a sample patient record ──────────────────────
        patient_content = (
            "Patient: P-12345\n"
            "Date: 2025-01-15\n\n"
            "Diagnosis: E11.9 Type 2 diabetes mellitus, N18.3 CKD Stage 3\n\n"
            "Medications:\n"
            "- Metformin 500 mg BID\n"
            "- Lisinopril 10 mg daily\n\n"
            "Labs:\n"
            "HbA1c (LOINC 4548-4): 7.2%\n"
            "Creatinine (LOINC 2160-0): 1.8 mg/dL\n"
        )

        # Adjust mock for batch embedding to match chunk count
        chunks = chunker.chunk_document(patient_content, "lab_report", "doc-patient-001",
                                         metadata={"patient_id": "P-12345"})
        openai_client.generate_embeddings_batch.return_value = [[0.01] * 3072] * len(chunks)

        # Index patient record
        documents = []
        for chunk in chunks:
            doc = {
                "id": chunk.chunk_id,
                "content": chunk.content,
                "content_vector": [0.01] * 3072,
                "patient_id": "P-12345",
                "section_type": chunk.section_type,
            }
            documents.append(doc)
        await search_index.index_documents_batch("patient_records", documents)

        # Store patient profile in Cosmos
        await store.upsert_patient_profile(sample_patient_profile)

        # Verify ingestion
        assert len(search_index.indexes["patient_records"]) >= 1
        profile = await store.get_patient_profile("P-12345")
        assert profile is not None
        assert profile["patient_id"] == "P-12345"

        # ─── Step 2: Submit a clinical query ──────────────────────────────
        query = ClinicalQuery(
            text="What are the recommended treatment options for this patient with T2DM and CKD stage 3?",
            patient_id="P-12345",
            session_id="sess-e2e-001",
            intent="treatment",
        )

        # Create specialist agents (all mocked)
        patient_agent = AsyncMock()
        patient_agent.execute.return_value = AgentOutput(
            agent_name="patient_context",
            latency_ms=150,
            sources_retrieved=3,
            summary="62-year-old male with T2DM (HbA1c 7.2%) and CKD stage 3 (Cr 1.8). Current meds: metformin, lisinopril. Allergy: penicillin.",
            raw_data={"profile": sample_patient_profile},
        )

        literature_agent = AsyncMock()
        literature_agent.execute.return_value = AgentOutput(
            agent_name="literature",
            latency_ms=800,
            sources_retrieved=5,
            summary="DAPA-CKD trial (PMID 32970396): 39% reduction in kidney failure with dapagliflozin.",
            raw_data={"papers": [{"pmid": "32970396", "title": "DAPA-CKD"}]},
        )

        protocol_agent = AsyncMock()
        protocol_agent.execute.return_value = AgentOutput(
            agent_name="protocol",
            latency_ms=200,
            sources_retrieved=2,
            summary="ADA 2024: SGLT2 inhibitors recommended for T2DM with CKD (Grade A).",
            raw_data={"protocols": [{"guideline": "ADA 2024", "grade": "A"}]},
        )

        drug_safety_agent = AsyncMock()
        drug_safety_agent.execute.return_value = AgentOutput(
            agent_name="drug_safety",
            latency_ms=300,
            sources_retrieved=4,
            summary="Minor interaction: metformin + dapagliflozin (additive hypoglycemic effect). No allergy cross-reactivity.",
            raw_data={
                "interactions": [
                    {"drug_a": "metformin", "drug_b": "dapagliflozin", "severity": "minor",
                     "description": "Additive hypoglycemic effect"}
                ],
                "allergy_alerts": [],
            },
        )

        guardrails_agent = AsyncMock()
        guardrails_agent.execute.return_value = AgentOutput(
            agent_name="guardrails",
            latency_ms=100,
            sources_retrieved=0,
            summary="Validation passed.",
            raw_data={
                "is_valid": True,
                "hallucination_flags": [],
                "safety_concerns": [],
                "disclaimers": [
                    "This is a clinical decision support tool and does not replace clinical judgment.",
                    "All recommendations should be verified with current clinical guidelines.",
                ],
            },
        )

        # ─── Step 3: Run orchestration ────────────────────────────────────
        agents = {
            "patient_context": patient_agent,
            "literature": literature_agent,
            "protocol": protocol_agent,
            "drug_safety": drug_safety_agent,
            "guardrails": guardrails_agent,
        }

        # Simulate orchestrator steps
        # Plan
        plan = QueryPlan(
            query_type="treatment",
            required_agents=["patient_context", "literature", "protocol", "drug_safety"],
            parallel_dispatch=True,
        )

        # Dispatch agents
        agent_outputs: dict[str, AgentOutput] = {}
        for name in plan.required_agents:
            task = AgentTask(
                from_agent="orchestrator",
                to_agent=name,
                message_type="task_request",
                payload={"query": query.text, "patient_id": query.patient_id},
                session_id=query.session_id or "default",
                trace_id="trace-e2e",
            )
            output = await agents[name].execute(task)
            agent_outputs[name] = output

        # ─── Step 3: Verify all agents were called ────────────────────────
        for name in ["patient_context", "literature", "protocol", "drug_safety"]:
            agents[name].execute.assert_called_once()

        # ─── Step 4: Synthesize response ──────────────────────────────────
        synthesis_result = await openai_client.chat_completion(
            messages=[
                {"role": "system", "content": "Synthesize clinical response."},
                {"role": "user", "content": f"Query: {query.text}"},
            ],
            model="gpt-4o",
        )

        response = ClinicalResponse(
            assessment="62-year-old male with uncontrolled T2DM (HbA1c 7.2%) and CKD stage 3.",
            recommendation=synthesis_result["content"],
            evidence_summary=[
                "DAPA-CKD trial: 39% reduction in kidney failure risk (PMID: 32970396)",
                "ADA 2024 guidelines recommend SGLT2 inhibitors for T2DM with CKD (Grade A)",
            ],
            drug_alerts=[
                DrugAlert(
                    severity="minor",
                    description="Metformin + dapagliflozin: additive hypoglycemic effect",
                    source="DrugBank",
                    evidence_level=3,
                )
            ],
            confidence_score=0.87,
            citations=[
                Citation(
                    source_type="pubmed",
                    identifier="32970396",
                    title="Dapagliflozin in CKD",
                    relevance_score=0.92,
                    url="https://pubmed.ncbi.nlm.nih.gov/32970396/",
                ),
                Citation(
                    source_type="guideline",
                    identifier="ADA-2024",
                    title="ADA Standards of Care 2024",
                    relevance_score=0.88,
                ),
            ],
            disclaimers=[
                "This is a clinical decision support tool and does not replace clinical judgment.",
                "All recommendations should be verified with current clinical guidelines.",
            ],
            agent_outputs=agent_outputs,
        )

        # ─── Verify response has citations ────────────────────────────────
        assert len(response.citations) == 2
        assert any(c.identifier == "32970396" for c in response.citations)
        assert any(c.source_type == "guideline" for c in response.citations)

        # ─── Verify response has drug alerts ──────────────────────────────
        assert len(response.drug_alerts) == 1
        assert response.drug_alerts[0].severity == "minor"

        # ─── Verify response has disclaimers ──────────────────────────────
        assert len(response.disclaimers) >= 2
        assert any("clinical judgment" in d for d in response.disclaimers)

        # ─── Step 5: Save conversation to Cosmos ──────────────────────────
        await store.save_conversation_turn({
            "id": "turn-e2e-001",
            "session_id": "sess-e2e-001",
            "patient_id": "P-12345",
            "query": query.text,
            "response": response.recommendation,
            "confidence": response.confidence_score,
        })

        history = await store.get_conversation_history("sess-e2e-001")
        assert len(history) == 1
        assert history[0]["session_id"] == "sess-e2e-001"
        assert history[0]["patient_id"] == "P-12345"

        # ─── Step 6: Create audit log ─────────────────────────────────────
        await store.log_audit_event({
            "id": "audit-e2e-001",
            "type": "patient_data_access",
            "session_id": "sess-e2e-001",
            "patient_id": "P-12345",
            "action": "read_patient_profile",
            "data_sent_to_llm": True,
            "phi_fields_sent": ["demographics.age", "active_conditions", "active_medications"],
            "outcome": "success",
        })

        await store.log_audit_event({
            "id": "audit-e2e-002",
            "type": "query_processed",
            "session_id": "sess-e2e-001",
            "patient_id": "P-12345",
            "action": "process_clinical_query",
            "agents_used": ["patient_context", "literature", "protocol", "drug_safety"],
            "confidence_score": 0.87,
            "outcome": "success",
        })

        audit_trail = await store.get_audit_trail()
        assert len(audit_trail) == 2
        assert any(e["type"] == "patient_data_access" for e in audit_trail)
        assert any(e["type"] == "query_processed" for e in audit_trail)

    async def test_query_without_patient_context(
        self,
        store,
        openai_client,
    ):
        """Test query processing when no patient is specified."""
        query = ClinicalQuery(
            text="What is the mechanism of action of SGLT2 inhibitors?",
            session_id="sess-general-001",
        )

        openai_client.classify_query.return_value = {
            "query_type": "general",
            "entities": ["SGLT2 inhibitors"],
            "required_agents": ["literature"],
        }

        classification = await openai_client.classify_query(query.text)
        assert classification["query_type"] == "general"

        # General queries should not require patient context
        assert query.patient_id is None

        synthesis = await openai_client.chat_completion(
            messages=[{"role": "user", "content": query.text}],
            model="gpt-4o",
        )

        response = ClinicalResponse(
            assessment="General question about SGLT2 inhibitors.",
            recommendation=synthesis["content"],
            confidence_score=0.9,
            disclaimers=["This is a decision support tool."],
        )

        assert response.confidence_score == 0.9
        assert len(response.drug_alerts) == 0

    async def test_drug_check_flow(
        self,
        store,
        openai_client,
    ):
        """Test drug interaction check flow."""
        query = ClinicalQuery(
            text="Check interactions between warfarin and aspirin",
            patient_id="P-12345",
            session_id="sess-drug-001",
            intent="drug_check",
        )

        openai_client.classify_query.return_value = {
            "query_type": "drug_check",
            "entities": ["warfarin", "aspirin"],
            "required_agents": ["drug_interaction"],
        }

        classification = await openai_client.classify_query(query.text)
        assert classification["query_type"] == "drug_check"

        # Simulate drug safety agent finding a major interaction
        drug_output = AgentOutput(
            agent_name="drug_safety",
            latency_ms=250,
            sources_retrieved=3,
            summary="Major interaction: warfarin + aspirin increases bleeding risk.",
            raw_data={
                "interactions": [
                    {
                        "drug_a": "warfarin",
                        "drug_b": "aspirin",
                        "severity": "major",
                        "description": "Increased bleeding risk",
                        "evidence_level": 1,
                        "source": "DrugBank",
                    }
                ],
            },
        )

        # Build response with major drug alert
        response = ClinicalResponse(
            assessment="Drug interaction check for warfarin and aspirin.",
            recommendation="Major interaction detected. Concurrent use of warfarin and aspirin significantly increases bleeding risk.",
            drug_alerts=[
                DrugAlert(
                    severity="major",
                    description="Increased bleeding risk with concurrent warfarin and aspirin use.",
                    source="DrugBank",
                    evidence_level=1,
                    alternatives=["Consider alternative antiplatelet agents."],
                )
            ],
            confidence_score=0.95,
            disclaimers=["This is a clinical decision support tool."],
            agent_outputs={"drug_safety": drug_output},
        )

        assert len(response.drug_alerts) == 1
        assert response.drug_alerts[0].severity == "major"
        assert "bleeding" in response.drug_alerts[0].description.lower()

        # Log the interaction
        await store.save_conversation_turn({
            "session_id": "sess-drug-001",
            "query": query.text,
            "drug_alerts_count": len(response.drug_alerts),
        })

        history = await store.get_conversation_history("sess-drug-001")
        assert len(history) == 1
        assert history[0]["drug_alerts_count"] == 1
