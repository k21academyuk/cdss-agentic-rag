"""Shared pytest fixtures for the CDSS test suite.

Provides reusable mock objects for Azure services, external API clients,
and sample domain data used across all test modules.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cdss.core.config import Settings
from cdss.core.models import (
    AgentOutput,
    AgentTask,
    Allergy,
    AuditLogEntry,
    Citation,
    ClinicalQuery,
    ClinicalResponse,
    ConversationTurn,
    Demographics,
    DrugAlert,
    DrugInteraction,
    DrugSafetyReport,
    ExtractedEntity,
    GuardrailsResult,
    LabResult,
    MedicalCondition,
    Medication,
    PatientContext,
    PatientProfile,
    ProtocolMatch,
    PubMedArticle,
    QueryPlan,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Settings Fixture
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_settings() -> Settings:
    """Return a Settings instance with test values (no real credentials)."""
    return Settings(
        azure_openai_endpoint="https://test-openai.openai.azure.com/",
        azure_openai_api_key="test-openai-key-000",
        azure_openai_deployment_name="gpt-4o",
        azure_openai_mini_deployment_name="gpt-4o-mini",
        azure_openai_embedding_deployment="text-embedding-3-large",
        azure_openai_api_version="2024-12-01-preview",
        azure_search_endpoint="https://test-search.search.windows.net",
        azure_search_api_key="test-search-key-000",
        azure_search_patient_records_index="patient-records",
        azure_search_treatment_protocols_index="treatment-protocols",
        azure_search_medical_literature_index="medical-literature",
        azure_cosmos_endpoint="https://test-cosmos.documents.azure.com:443/",
        azure_cosmos_key="test-cosmos-key-000",
        azure_cosmos_database_name="cdss_test_db",
        azure_document_intelligence_endpoint="https://test-docint.cognitiveservices.azure.com/",
        azure_document_intelligence_key="test-docint-key-000",
        azure_key_vault_url="https://test-vault.vault.azure.net/",
        azure_blob_connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
        pubmed_api_key="test-pubmed-key",
        pubmed_email="test@cdss.dev",
        openfda_base_url="https://api.fda.gov",
        rxnorm_base_url="https://rxnav.nlm.nih.gov/REST",
        drugbank_api_key="test-drugbank-key",
        drugbank_base_url="https://api.drugbank.com/v1",
        redis_url="redis://localhost:6379/15",
        debug=True,
        log_level="DEBUG",
        cors_origins=["http://localhost:3000"],
        max_concurrent_agents=5,
        response_timeout_seconds=10,
        confidence_threshold=0.6,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Azure Service Client Mocks
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_openai_client() -> AsyncMock:
    """AsyncMock of AzureOpenAIClient with realistic return values."""
    client = AsyncMock()

    # chat_completion returns a dict with content, tool_calls, and usage
    client.chat_completion.return_value = {
        "content": '{"query_type": "treatment", "entities": ["diabetes"], "required_agents": ["patient_history", "literature"]}',
        "tool_calls": None,
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 450,
            "total_tokens": 1650,
        },
    }

    # generate_embedding returns a 3072-dim vector
    client.generate_embedding.return_value = [0.01] * 3072

    # generate_embeddings_batch returns list of vectors
    client.generate_embeddings_batch.return_value = [[0.01] * 3072, [0.02] * 3072]

    # classify_query returns classification dict
    client.classify_query.return_value = {
        "query_type": "treatment",
        "entities": ["type 2 diabetes", "CKD stage 3"],
        "required_agents": ["patient_history", "literature", "protocol", "drug_safety"],
    }

    # evaluate_relevance returns a float
    client.evaluate_relevance.return_value = 0.85

    return client


@pytest.fixture
def mock_search_client() -> AsyncMock:
    """AsyncMock of AzureSearchClient with realistic return values."""
    client = AsyncMock()

    base_result = {
        "id": "doc-001",
        "score": 0.92,
        "reranker_score": 0.88,
        "content": "Patient with type 2 diabetes mellitus and stage 3 CKD.",
        "metadata": {
            "patient_id": "P-12345",
            "document_type": "clinical_note",
            "date": "2025-11-01",
        },
    }

    client.hybrid_search.return_value = [base_result]
    client.search_patient_records.return_value = [base_result]
    client.search_treatment_protocols.return_value = [
        {
            "id": "proto-001",
            "score": 0.89,
            "reranker_score": 0.85,
            "content": "ADA 2024 Standards of Care: SGLT2 inhibitors recommended for T2DM with CKD.",
            "metadata": {
                "specialty": "endocrinology",
                "guideline": "ADA 2024",
            },
        }
    ]
    client.search_medical_literature.return_value = [
        {
            "id": "lit-001",
            "score": 0.87,
            "reranker_score": 0.82,
            "content": "DAPA-CKD trial demonstrated 39% reduction in kidney failure risk.",
            "metadata": {
                "pmid": "32970396",
                "journal": "N Engl J Med",
            },
        }
    ]

    client.index_document.return_value = None
    client.index_documents_batch.return_value = {
        "total": 5,
        "succeeded": 5,
        "failed": 0,
        "errors": [],
    }

    return client


@pytest.fixture
def mock_cosmos_client() -> AsyncMock:
    """AsyncMock of CosmosDBClient with realistic return values."""
    client = AsyncMock()

    client.get_patient_profile.return_value = {
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
        "active_conditions": [
            {
                "code": "E11.9",
                "coding_system": "ICD-10",
                "display": "Type 2 diabetes mellitus",
                "status": "active",
            }
        ],
        "active_medications": [
            {
                "rxcui": "860975",
                "name": "Metformin 500 mg",
                "dose": "500 mg",
                "frequency": "twice daily",
            }
        ],
        "allergies": [
            {
                "substance": "Penicillin",
                "reaction": "Anaphylaxis",
                "severity": "severe",
            }
        ],
        "recent_labs": [
            {
                "code": "4548-4",
                "coding_system": "LOINC",
                "display": "Hemoglobin A1c",
                "value": 7.2,
                "unit": "%",
                "test_date": "2025-11-01",
                "reference_range": "4.0-5.6",
            }
        ],
    }

    client.upsert_patient_profile.return_value = client.get_patient_profile.return_value
    client.save_conversation_turn.return_value = {"id": "turn-001", "session_id": "sess-001"}
    client.get_conversation_history.return_value = []
    client.get_cached_embedding.return_value = None
    client.cache_embedding.return_value = None
    client.log_audit_event.return_value = {"id": "audit-001"}
    client.get_audit_trail.return_value = []
    client.save_agent_state.return_value = {"id": "sess-001"}
    client.get_agent_state.return_value = None
    client.vector_search_patients.return_value = []

    return client


# ═══════════════════════════════════════════════════════════════════════════════
# External API Client Mocks
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_pubmed_client() -> AsyncMock:
    """AsyncMock of PubMedClient with realistic return values."""
    client = AsyncMock()

    client.search.return_value = ["32970396", "33356052", "34272327"]

    client.fetch_articles.return_value = [
        {
            "pmid": "32970396",
            "title": "Dapagliflozin in Patients with Chronic Kidney Disease",
            "abstract": "BACKGROUND: CKD is common and treatment options are limited. "
            "METHODS: We randomized 4304 participants. "
            "RESULTS: Dapagliflozin reduced the primary composite endpoint by 39%.",
            "authors": ["Heerspink HJL", "Stefansson BV", "Correa-Rotter R"],
            "journal": "N Engl J Med",
            "pub_date": "2020-10-08",
            "mesh_terms": [
                "Diabetes Mellitus, Type 2",
                "Renal Insufficiency, Chronic",
                "Sodium-Glucose Transporter 2 Inhibitors",
            ],
            "doi": "10.1056/NEJMoa2024816",
            "pmc_id": "PMC7993404",
        },
        {
            "pmid": "33356052",
            "title": "SGLT2 Inhibitors for Primary Prevention of CKD Progression",
            "abstract": "SGLT2 inhibitors have shown renoprotective effects across studies.",
            "authors": ["Perkovic V", "Jardine MJ"],
            "journal": "Lancet",
            "pub_date": "2020-12-15",
            "mesh_terms": ["Kidney Diseases", "Sodium-Glucose Transporter 2 Inhibitors"],
            "doi": "10.1016/S0140-6736(20)32533-5",
            "pmc_id": "",
        },
    ]

    client.search_and_fetch.return_value = client.fetch_articles.return_value
    client.get_related_articles.return_value = ["34272327", "35012345"]
    client.build_mesh_query.return_value = (
        '(("diabetes mellitus, type 2"[MeSH Terms])) AND '
        '(("dapagliflozin"[MeSH Terms]))'
    )
    client.close.return_value = None

    return client


@pytest.fixture
def mock_openfda_client() -> AsyncMock:
    """AsyncMock of OpenFDAClient with realistic return values."""
    client = AsyncMock()

    client.search_adverse_events.return_value = [
        {
            "safety_report_id": "10234567",
            "reactions": ["Nausea", "Vomiting", "Diarrhoea"],
            "outcomes": ["Recovered/Resolved"],
            "seriousness": {
                "is_serious": False,
                "death": False,
                "hospitalization": False,
                "life_threatening": False,
                "disability": False,
                "congenital_anomaly": False,
                "other_medically_important": False,
            },
            "drug_characterization": "Suspect",
            "receive_date": "20240315",
        },
    ]

    client.get_drug_label.return_value = {
        "brand_name": "Farxiga",
        "generic_name": "dapagliflozin",
        "warnings": "Risk of diabetic ketoacidosis.",
        "contraindications": "Patients on dialysis.",
        "drug_interactions": "May increase diuretic effect.",
        "adverse_reactions": "Genital mycotic infections, UTI.",
        "indications_and_usage": "Type 2 diabetes mellitus, CKD, heart failure.",
        "dosage_and_administration": "10 mg once daily.",
        "boxed_warning": "",
        "pregnancy": "Category C.",
    }

    client.search_drug_recalls.return_value = []
    client.get_adverse_event_counts.return_value = {
        "drug_name": "dapagliflozin",
        "total_reports": 5432,
        "reaction_counts": [
            {"term": "Urinary tract infection", "count": 890},
            {"term": "Diabetic ketoacidosis", "count": 345},
        ],
    }
    client.close.return_value = None

    return client


@pytest.fixture
def mock_rxnorm_client() -> AsyncMock:
    """AsyncMock of a RxNorm API client."""
    client = AsyncMock()

    client.normalize_drug_name.return_value = {
        "rxcui": "1488574",
        "name": "dapagliflozin 10 MG Oral Tablet",
        "tty": "SCD",
    }

    client.find_interactions.return_value = [
        {
            "drug_a": "metformin",
            "drug_b": "dapagliflozin",
            "severity": "minor",
            "description": "Potential additive hypoglycemic effect.",
            "source": "RxNorm",
        }
    ]

    client.approximate_match.return_value = [
        {"rxcui": "1488574", "name": "dapagliflozin", "score": 95},
        {"rxcui": "1488576", "name": "dapagliflozin propanediol", "score": 80},
    ]

    return client


@pytest.fixture
def mock_drugbank_client() -> AsyncMock:
    """AsyncMock of a DrugBank API client."""
    client = AsyncMock()

    client.check_interactions.return_value = [
        {
            "drug_a": "metformin",
            "drug_b": "lisinopril",
            "severity": "minor",
            "description": "Metformin and lisinopril may increase the risk of lactic acidosis.",
            "evidence_level": 3,
            "source": "DrugBank",
        }
    ]

    client.search_drug.return_value = [
        {
            "drugbank_id": "DB01261",
            "name": "Sitagliptin",
            "categories": ["DPP-4 Inhibitors"],
            "indication": "Treatment of type 2 diabetes mellitus.",
        }
    ]

    return client


# ═══════════════════════════════════════════════════════════════════════════════
# Sample Domain Data Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_demographics() -> Demographics:
    """Return a realistic Demographics instance."""
    return Demographics(
        age=62,
        sex="male",
        weight_kg=85.0,
        height_cm=175.0,
        blood_type="A+",
    )


@pytest.fixture
def sample_patient_profile(sample_demographics: Demographics) -> dict:
    """Return a realistic patient profile dict matching Cosmos DB format."""
    return {
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
        "active_conditions": [
            {
                "code": "E11.9",
                "coding_system": "ICD-10",
                "display": "Type 2 diabetes mellitus without complications",
                "onset_date": "2019-03-15",
                "status": "active",
            },
            {
                "code": "N18.3",
                "coding_system": "ICD-10",
                "display": "Chronic kidney disease, stage 3",
                "onset_date": "2021-06-10",
                "status": "active",
            },
        ],
        "active_medications": [
            {
                "rxcui": "860975",
                "name": "Metformin 500 mg oral tablet",
                "dose": "500 mg",
                "frequency": "twice daily",
                "start_date": "2020-01-10",
                "prescriber": "Dr. Smith",
            },
            {
                "rxcui": "314076",
                "name": "Lisinopril 10 mg oral tablet",
                "dose": "10 mg",
                "frequency": "once daily",
                "start_date": "2021-07-01",
                "prescriber": "Dr. Johnson",
            },
        ],
        "allergies": [
            {
                "substance": "Penicillin",
                "reaction": "Anaphylaxis",
                "severity": "severe",
                "code": "91936005",
                "coding_system": "SNOMED-CT",
            }
        ],
        "recent_labs": [
            {
                "code": "4548-4",
                "coding_system": "LOINC",
                "display": "Hemoglobin A1c",
                "value": 7.2,
                "unit": "%",
                "test_date": "2025-11-01",
                "reference_range": "4.0-5.6",
            },
            {
                "code": "2160-0",
                "coding_system": "LOINC",
                "display": "Creatinine",
                "value": 1.8,
                "unit": "mg/dL",
                "test_date": "2025-11-01",
                "reference_range": "0.7-1.3",
            },
        ],
    }


@pytest.fixture
def sample_clinical_query() -> ClinicalQuery:
    """Return a realistic ClinicalQuery instance."""
    return ClinicalQuery(
        text="What are the recommended treatment options for a 62-year-old male with type 2 diabetes and CKD stage 3?",
        patient_id="P-12345",
        session_id="sess-abc123",
        intent="treatment",
        extracted_entities=[
            ExtractedEntity(entity_type="condition", value="type 2 diabetes", code="E11.9"),
            ExtractedEntity(entity_type="condition", value="CKD stage 3", code="N18.3"),
        ],
    )


@pytest.fixture
def sample_agent_output() -> AgentOutput:
    """Return a realistic AgentOutput instance."""
    return AgentOutput(
        agent_name="literature_agent",
        latency_ms=1250,
        sources_retrieved=5,
        summary="Found 5 relevant studies on SGLT2 inhibitors for T2DM with CKD. "
        "DAPA-CKD trial (PMID: 32970396) shows 39% reduction in kidney failure.",
        raw_data={
            "papers": [
                {"pmid": "32970396", "title": "Dapagliflozin in CKD"},
                {"pmid": "33356052", "title": "SGLT2 Inhibitors Review"},
            ],
            "sources_retrieved": 5,
            "summary": "Found 5 relevant studies.",
        },
    )


@pytest.fixture
def sample_guardrails_result() -> GuardrailsResult:
    """Return a realistic GuardrailsResult instance."""
    return GuardrailsResult(
        is_valid=True,
        hallucination_flags=[],
        safety_concerns=[],
        disclaimers=[
            "This is a clinical decision support tool and does not replace clinical judgment.",
            "All recommendations should be verified with current clinical guidelines.",
        ],
    )


@pytest.fixture
def sample_clinical_response() -> ClinicalResponse:
    """Return a realistic ClinicalResponse instance."""
    return ClinicalResponse(
        assessment="Patient presents with uncontrolled type 2 diabetes (HbA1c 7.2%) and stage 3 CKD (creatinine 1.8 mg/dL).",
        recommendation="Consider adding an SGLT2 inhibitor (e.g., dapagliflozin 10 mg daily) which provides both glycemic and renal benefits.",
        evidence_summary=[
            "DAPA-CKD trial showed 39% reduction in kidney failure risk (PMID: 32970396).",
            "ADA 2024 guidelines recommend SGLT2 inhibitors for T2DM with CKD (Grade A).",
        ],
        drug_alerts=[
            DrugAlert(
                severity="minor",
                description="Potential additive hypoglycemic effect with metformin.",
                source="RxNorm",
                evidence_level=3,
                alternatives=[],
            )
        ],
        confidence_score=0.87,
        citations=[
            Citation(
                source_type="pubmed",
                identifier="32970396",
                title="Dapagliflozin in Patients with Chronic Kidney Disease",
                relevance_score=0.92,
                url="https://pubmed.ncbi.nlm.nih.gov/32970396/",
            ),
            Citation(
                source_type="guideline",
                identifier="ADA-2024-CKD",
                title="ADA Standards of Care 2024",
                relevance_score=0.88,
            ),
        ],
        disclaimers=[
            "This is a clinical decision support tool and does not replace clinical judgment.",
        ],
        agent_outputs={},
    )


@pytest.fixture
def sample_pubmed_articles() -> list[dict]:
    """Return a list of realistic PubMed article dicts."""
    return [
        {
            "pmid": "32970396",
            "title": "Dapagliflozin in Patients with Chronic Kidney Disease",
            "abstract": "BACKGROUND: CKD is common. METHODS: 4304 participants randomized. "
            "RESULTS: 39% reduction in primary composite endpoint.",
            "authors": ["Heerspink HJL", "Stefansson BV", "Correa-Rotter R"],
            "journal": "N Engl J Med",
            "pub_date": "2020-10-08",
            "mesh_terms": [
                "Diabetes Mellitus, Type 2",
                "Renal Insufficiency, Chronic",
            ],
            "doi": "10.1056/NEJMoa2024816",
            "pmc_id": "PMC7993404",
        },
        {
            "pmid": "33356052",
            "title": "SGLT2 Inhibitors for CKD Progression",
            "abstract": "SGLT2 inhibitors demonstrate renoprotective effects.",
            "authors": ["Perkovic V", "Jardine MJ"],
            "journal": "Lancet",
            "pub_date": "2020-12-15",
            "mesh_terms": ["Kidney Diseases"],
            "doi": "10.1016/S0140-6736(20)32533-5",
            "pmc_id": "",
        },
    ]


@pytest.fixture
def sample_drug_interactions() -> list[dict]:
    """Return a list of realistic drug interaction dicts."""
    return [
        {
            "drug_a": "metformin",
            "drug_b": "dapagliflozin",
            "severity": "minor",
            "description": "Potential additive hypoglycemic effect when used together.",
            "evidence_level": 3,
            "source": "DrugBank",
            "clinical_significance": "Monitor blood glucose more frequently.",
        },
        {
            "drug_a": "lisinopril",
            "drug_b": "dapagliflozin",
            "severity": "moderate",
            "description": "Risk of hypotension and acute kidney injury due to volume depletion.",
            "evidence_level": 2,
            "source": "DrugBank",
            "clinical_significance": "Monitor blood pressure and renal function.",
        },
    ]


@pytest.fixture
def sample_query_plan() -> QueryPlan:
    """Return a realistic QueryPlan instance."""
    return QueryPlan(
        query_type="treatment",
        required_agents=["patient_context", "literature", "protocol", "drug_safety"],
        sub_queries={
            "literature": "SGLT2 inhibitors for type 2 diabetes with CKD stage 3",
            "protocol": "ADA 2024 guidelines for diabetes with renal impairment",
            "drug_safety": "Check interactions: metformin, lisinopril, dapagliflozin",
        },
        priority="high",
        parallel_dispatch=True,
    )


@pytest.fixture
def sample_agent_task() -> AgentTask:
    """Return a realistic AgentTask instance."""
    return AgentTask(
        from_agent="orchestrator",
        to_agent="literature_agent",
        message_type="task_request",
        payload={
            "query": "SGLT2 inhibitors for type 2 diabetes with CKD stage 3",
            "patient_id": "P-12345",
        },
        session_id="sess-abc123",
        trace_id="trace-xyz789",
    )
