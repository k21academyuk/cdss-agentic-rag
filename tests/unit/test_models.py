"""Tests for all Pydantic domain models in cdss.core.models.

Covers creation, validation, serialization, and error cases for every
model class used across the CDSS pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
    LiteratureEvidence,
    MedicalCondition,
    Medication,
    PatientContext,
    PatientProfile,
    ProtocolMatch,
    PubMedArticle,
    QueryPlan,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Demographics
# ═══════════════════════════════════════════════════════════════════════════════


class TestDemographics:
    """Tests for the Demographics model."""

    def test_create_valid_demographics(self):
        demo = Demographics(age=62, sex="male", weight_kg=85.0, height_cm=175.0, blood_type="A+")
        assert demo.age == 62
        assert demo.sex == "male"
        assert demo.weight_kg == 85.0
        assert demo.height_cm == 175.0
        assert demo.blood_type == "A+"

    def test_demographics_optional_blood_type(self):
        demo = Demographics(age=30, sex="female", weight_kg=60.0, height_cm=165.0)
        assert demo.blood_type is None

    def test_demographics_age_zero_valid(self):
        demo = Demographics(age=0, sex="other", weight_kg=3.5, height_cm=50.0)
        assert demo.age == 0

    def test_demographics_negative_age_invalid(self):
        with pytest.raises(ValidationError) as exc_info:
            Demographics(age=-1, sex="male", weight_kg=80.0, height_cm=175.0)
        assert "greater than or equal to 0" in str(exc_info.value).lower() or "ge" in str(exc_info.value).lower()

    def test_demographics_age_exceeds_max_invalid(self):
        with pytest.raises(ValidationError):
            Demographics(age=151, sex="male", weight_kg=80.0, height_cm=175.0)

    def test_demographics_zero_weight_invalid(self):
        with pytest.raises(ValidationError):
            Demographics(age=30, sex="male", weight_kg=0.0, height_cm=175.0)

    def test_demographics_missing_required_field(self):
        with pytest.raises(ValidationError):
            Demographics(age=30, sex="male", weight_kg=80.0)  # missing height_cm

    def test_demographics_json_roundtrip(self):
        demo = Demographics(age=45, sex="female", weight_kg=70.0, height_cm=168.0, blood_type="O-")
        json_str = demo.model_dump_json()
        restored = Demographics.model_validate_json(json_str)
        assert restored == demo


# ═══════════════════════════════════════════════════════════════════════════════
# MedicalCondition
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicalCondition:
    """Tests for the MedicalCondition model."""

    def test_create_valid_condition(self):
        condition = MedicalCondition(
            code="E11.9",
            coding_system="ICD-10",
            display="Type 2 diabetes mellitus without complications",
            onset_date=date(2019, 3, 15),
            status="active",
        )
        assert condition.code == "E11.9"
        assert condition.coding_system == "ICD-10"
        assert condition.status == "active"

    def test_condition_snomed_ct_system(self):
        condition = MedicalCondition(
            code="44054006",
            coding_system="SNOMED-CT",
            display="Type 2 diabetes mellitus",
        )
        assert condition.coding_system == "SNOMED-CT"

    def test_condition_invalid_coding_system(self):
        with pytest.raises(ValidationError) as exc_info:
            MedicalCondition(
                code="E11.9",
                coding_system="INVALID",
                display="Diabetes",
            )
        errors = exc_info.value.errors()
        assert any("coding_system" in str(e.get("loc", "")) for e in errors)

    def test_condition_default_status(self):
        condition = MedicalCondition(code="J06.9", coding_system="ICD-10", display="URI")
        assert condition.status == "active"

    def test_condition_optional_onset_date(self):
        condition = MedicalCondition(code="I10", coding_system="ICD-10", display="Hypertension")
        assert condition.onset_date is None

    def test_condition_json_roundtrip(self):
        condition = MedicalCondition(
            code="N18.3", coding_system="ICD-10", display="CKD stage 3", onset_date=date(2021, 6, 10)
        )
        restored = MedicalCondition.model_validate_json(condition.model_dump_json())
        assert restored.code == condition.code
        assert restored.onset_date == condition.onset_date


# ═══════════════════════════════════════════════════════════════════════════════
# Medication
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedication:
    """Tests for the Medication model."""

    def test_create_valid_medication(self):
        med = Medication(
            rxcui="860975",
            name="Metformin 500 mg oral tablet",
            dose="500 mg",
            frequency="twice daily",
            start_date=date(2020, 1, 10),
            prescriber="Dr. Smith",
        )
        assert med.rxcui == "860975"
        assert med.frequency == "twice daily"
        assert med.prescriber == "Dr. Smith"

    def test_medication_optional_fields(self):
        med = Medication(rxcui="12345", name="Test Drug", dose="10 mg", frequency="daily")
        assert med.start_date is None
        assert med.prescriber is None

    def test_medication_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Medication(rxcui="12345", name="Test Drug")  # missing dose and frequency


# ═══════════════════════════════════════════════════════════════════════════════
# Allergy
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllergy:
    """Tests for the Allergy model."""

    def test_create_valid_allergy(self):
        allergy = Allergy(
            substance="Penicillin",
            reaction="Anaphylaxis",
            severity="severe",
            code="91936005",
            coding_system="SNOMED-CT",
        )
        assert allergy.substance == "Penicillin"
        assert allergy.severity == "severe"

    def test_allergy_invalid_severity(self):
        with pytest.raises(ValidationError):
            Allergy(substance="Aspirin", reaction="Rash", severity="extreme")

    def test_allergy_valid_severity_levels(self):
        for sev in ("mild", "moderate", "severe"):
            allergy = Allergy(substance="Drug", reaction="Reaction", severity=sev)
            assert allergy.severity == sev

    def test_allergy_optional_code(self):
        allergy = Allergy(substance="Sulfa", reaction="Hives", severity="moderate")
        assert allergy.code is None
        assert allergy.coding_system is None


# ═══════════════════════════════════════════════════════════════════════════════
# LabResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestLabResult:
    """Tests for the LabResult model."""

    def test_create_valid_lab_result(self):
        lab = LabResult(
            code="4548-4",
            display="Hemoglobin A1c",
            value=7.2,
            unit="%",
            test_date=date(2025, 11, 1),
            reference_range="4.0-5.6",
        )
        assert lab.code == "4548-4"
        assert lab.value == 7.2
        assert lab.coding_system == "LOINC"  # default

    def test_lab_result_optional_reference_range(self):
        lab = LabResult(
            code="2160-0",
            display="Creatinine",
            value=1.8,
            unit="mg/dL",
            test_date=date(2025, 11, 1),
        )
        assert lab.reference_range is None

    def test_lab_result_json_roundtrip(self):
        lab = LabResult(
            code="2160-0",
            display="Creatinine",
            value=1.8,
            unit="mg/dL",
            test_date=date(2025, 11, 1),
        )
        restored = LabResult.model_validate_json(lab.model_dump_json())
        assert restored.value == lab.value
        assert restored.test_date == lab.test_date


# ═══════════════════════════════════════════════════════════════════════════════
# PatientProfile
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatientProfile:
    """Tests for the PatientProfile model with nested models."""

    def test_create_full_patient_profile(self, sample_patient_profile):
        profile = PatientProfile(**sample_patient_profile)
        assert profile.patient_id == "P-12345"
        assert len(profile.active_conditions) == 2
        assert len(profile.active_medications) == 2
        assert len(profile.allergies) == 1
        assert len(profile.recent_labs) == 2
        assert profile.doc_type == "patient_profile"

    def test_patient_profile_auto_generated_id(self):
        profile = PatientProfile(
            patient_id="P-99999",
            demographics=Demographics(age=30, sex="female", weight_kg=60.0, height_cm=165.0),
        )
        assert profile.id is not None
        assert len(profile.id) > 0

    def test_patient_profile_empty_lists_default(self):
        profile = PatientProfile(
            patient_id="P-99999",
            demographics=Demographics(age=30, sex="female", weight_kg=60.0, height_cm=165.0),
        )
        assert profile.active_conditions == []
        assert profile.active_medications == []
        assert profile.allergies == []
        assert profile.recent_labs == []

    def test_patient_profile_missing_demographics_invalid(self):
        with pytest.raises(ValidationError):
            PatientProfile(patient_id="P-99999")

    def test_patient_profile_json_roundtrip(self, sample_patient_profile):
        profile = PatientProfile(**sample_patient_profile)
        json_str = profile.model_dump_json()
        restored = PatientProfile.model_validate_json(json_str)
        assert restored.patient_id == profile.patient_id
        assert len(restored.active_conditions) == len(profile.active_conditions)
        assert restored.active_conditions[0].code == "E11.9"

    def test_patient_profile_embedding_optional(self):
        profile = PatientProfile(
            patient_id="P-11111",
            demographics=Demographics(age=50, sex="male", weight_kg=90.0, height_cm=180.0),
        )
        assert profile.patient_embedding is None


# ═══════════════════════════════════════════════════════════════════════════════
# ClinicalQuery
# ═══════════════════════════════════════════════════════════════════════════════


class TestClinicalQuery:
    """Tests for the ClinicalQuery model."""

    def test_create_valid_query(self, sample_clinical_query):
        assert sample_clinical_query.text.startswith("What are the")
        assert sample_clinical_query.patient_id == "P-12345"
        assert sample_clinical_query.intent == "treatment"
        assert len(sample_clinical_query.extracted_entities) == 2

    def test_query_minimal(self):
        query = ClinicalQuery(text="What is hypertension?")
        assert query.patient_id is None
        assert query.session_id is None
        assert query.intent is None
        assert query.extracted_entities is None

    def test_query_empty_text_invalid(self):
        with pytest.raises(ValidationError):
            ClinicalQuery(text="")

    def test_query_with_entities(self):
        query = ClinicalQuery(
            text="Check drug interactions for metformin and lisinopril",
            intent="drug_check",
            extracted_entities=[
                ExtractedEntity(entity_type="medication", value="metformin", code="860975"),
                ExtractedEntity(entity_type="medication", value="lisinopril", code="314076"),
            ],
        )
        assert len(query.extracted_entities) == 2
        assert query.extracted_entities[0].entity_type == "medication"


# ═══════════════════════════════════════════════════════════════════════════════
# ExtractedEntity
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractedEntity:
    """Tests for the ExtractedEntity model."""

    def test_valid_entity_types(self):
        for entity_type in ("condition", "medication", "lab_test", "procedure", "anatomical_site"):
            entity = ExtractedEntity(entity_type=entity_type, value="test")
            assert entity.entity_type == entity_type

    def test_invalid_entity_type(self):
        with pytest.raises(ValidationError):
            ExtractedEntity(entity_type="invalid_type", value="test")

    def test_entity_optional_code(self):
        entity = ExtractedEntity(entity_type="condition", value="diabetes")
        assert entity.code is None


# ═══════════════════════════════════════════════════════════════════════════════
# ClinicalResponse
# ═══════════════════════════════════════════════════════════════════════════════


class TestClinicalResponse:
    """Tests for the ClinicalResponse model."""

    def test_create_full_response(self, sample_clinical_response):
        assert "diabetes" in sample_clinical_response.assessment.lower()
        assert sample_clinical_response.confidence_score == 0.87
        assert len(sample_clinical_response.citations) == 2
        assert len(sample_clinical_response.drug_alerts) == 1

    def test_response_confidence_score_range(self):
        with pytest.raises(ValidationError):
            ClinicalResponse(
                assessment="Test",
                recommendation="Test",
                confidence_score=1.5,
            )

    def test_response_negative_confidence_invalid(self):
        with pytest.raises(ValidationError):
            ClinicalResponse(
                assessment="Test",
                recommendation="Test",
                confidence_score=-0.1,
            )

    def test_response_json_roundtrip(self, sample_clinical_response):
        json_str = sample_clinical_response.model_dump_json()
        restored = ClinicalResponse.model_validate_json(json_str)
        assert restored.assessment == sample_clinical_response.assessment
        assert restored.confidence_score == sample_clinical_response.confidence_score
        assert len(restored.citations) == len(sample_clinical_response.citations)


# ═══════════════════════════════════════════════════════════════════════════════
# Citation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCitation:
    """Tests for the Citation model."""

    def test_valid_source_types(self):
        for src_type in ("pubmed", "guideline", "patient_record", "drug_database"):
            cit = Citation(
                source_type=src_type,
                identifier="test-id",
                title="Test Title",
                relevance_score=0.8,
            )
            assert cit.source_type == src_type

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            Citation(
                source_type="wikipedia",
                identifier="test-id",
                title="Test",
                relevance_score=0.5,
            )

    def test_citation_relevance_score_bounds(self):
        with pytest.raises(ValidationError):
            Citation(
                source_type="pubmed",
                identifier="123",
                title="Test",
                relevance_score=1.5,
            )

    def test_citation_optional_url(self):
        cit = Citation(
            source_type="guideline",
            identifier="ADA-2024",
            title="ADA Standards",
            relevance_score=0.9,
        )
        assert cit.url is None


# ═══════════════════════════════════════════════════════════════════════════════
# DrugAlert
# ═══════════════════════════════════════════════════════════════════════════════


class TestDrugAlert:
    """Tests for the DrugAlert model."""

    def test_valid_severities(self):
        for sev in ("minor", "moderate", "major"):
            alert = DrugAlert(
                severity=sev,
                description="Test alert",
                source="DrugBank",
                evidence_level=3,
            )
            assert alert.severity == sev

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            DrugAlert(
                severity="critical",
                description="Test",
                source="DrugBank",
                evidence_level=3,
            )

    def test_evidence_level_bounds(self):
        with pytest.raises(ValidationError):
            DrugAlert(severity="minor", description="Test", source="DB", evidence_level=0)
        with pytest.raises(ValidationError):
            DrugAlert(severity="minor", description="Test", source="DB", evidence_level=6)

    def test_drug_alert_with_alternatives(self):
        alert = DrugAlert(
            severity="major",
            description="Severe interaction",
            source="DrugBank",
            evidence_level=1,
            alternatives=["Drug A", "Drug B"],
        )
        assert len(alert.alternatives) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# DrugInteraction
# ═══════════════════════════════════════════════════════════════════════════════


class TestDrugInteraction:
    """Tests for the DrugInteraction model."""

    def test_create_valid_interaction(self):
        interaction = DrugInteraction(
            drug_a="metformin",
            drug_b="dapagliflozin",
            severity="minor",
            description="Additive hypoglycemic effect",
            evidence_level=3,
            source="DrugBank",
        )
        assert interaction.drug_a == "metformin"
        assert interaction.severity == "minor"

    def test_interaction_invalid_severity(self):
        with pytest.raises(ValidationError):
            DrugInteraction(
                drug_a="A",
                drug_b="B",
                severity="extreme",
                description="Test",
                evidence_level=3,
                source="Test",
            )

    def test_interaction_clinical_significance_optional(self):
        interaction = DrugInteraction(
            drug_a="A", drug_b="B", severity="moderate",
            description="Test", evidence_level=2, source="DB",
        )
        assert interaction.clinical_significance is None


# ═══════════════════════════════════════════════════════════════════════════════
# DrugSafetyReport
# ═══════════════════════════════════════════════════════════════════════════════


class TestDrugSafetyReport:
    """Tests for the DrugSafetyReport model."""

    def test_empty_report(self):
        report = DrugSafetyReport()
        assert report.interactions == []
        assert report.adverse_events == []
        assert report.alternatives == []
        assert report.dosage_adjustments == []

    def test_report_with_interactions(self):
        interaction = DrugInteraction(
            drug_a="metformin", drug_b="dapagliflozin", severity="minor",
            description="Test", evidence_level=3, source="DrugBank",
        )
        report = DrugSafetyReport(
            interactions=[interaction],
            alternatives=["sitagliptin"],
            dosage_adjustments=["Reduce metformin to 250 mg if eGFR < 30"],
        )
        assert len(report.interactions) == 1
        assert report.alternatives == ["sitagliptin"]


# ═══════════════════════════════════════════════════════════════════════════════
# QueryPlan
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryPlan:
    """Tests for the QueryPlan model."""

    def test_create_valid_plan(self, sample_query_plan):
        assert sample_query_plan.query_type == "treatment"
        assert len(sample_query_plan.required_agents) == 4
        assert sample_query_plan.parallel_dispatch is True

    def test_valid_query_types(self):
        for qt in ("diagnosis", "treatment", "drug_check", "general", "emergency"):
            plan = QueryPlan(query_type=qt, required_agents=["agent1"])
            assert plan.query_type == qt

    def test_invalid_query_type(self):
        with pytest.raises(ValidationError):
            QueryPlan(query_type="invalid", required_agents=["agent1"])

    def test_valid_priorities(self):
        for prio in ("low", "medium", "high", "critical"):
            plan = QueryPlan(query_type="general", required_agents=["a"], priority=prio)
            assert plan.priority == prio

    def test_default_priority(self):
        plan = QueryPlan(query_type="general", required_agents=["a"])
        assert plan.priority == "medium"

    def test_plan_json_roundtrip(self, sample_query_plan):
        restored = QueryPlan.model_validate_json(sample_query_plan.model_dump_json())
        assert restored.query_type == sample_query_plan.query_type
        assert restored.required_agents == sample_query_plan.required_agents


# ═══════════════════════════════════════════════════════════════════════════════
# AgentOutput
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentOutput:
    """Tests for the AgentOutput model."""

    def test_create_valid_output(self, sample_agent_output):
        assert sample_agent_output.agent_name == "literature_agent"
        assert sample_agent_output.latency_ms == 1250
        assert sample_agent_output.sources_retrieved == 5

    def test_output_negative_latency_invalid(self):
        with pytest.raises(ValidationError):
            AgentOutput(agent_name="test", latency_ms=-1, sources_retrieved=0, summary="Test")

    def test_output_negative_sources_invalid(self):
        with pytest.raises(ValidationError):
            AgentOutput(agent_name="test", latency_ms=100, sources_retrieved=-1, summary="Test")

    def test_output_optional_raw_data(self):
        output = AgentOutput(agent_name="test", latency_ms=100, sources_retrieved=0, summary="Test")
        assert output.raw_data is None


# ═══════════════════════════════════════════════════════════════════════════════
# ConversationTurn
# ═══════════════════════════════════════════════════════════════════════════════


class TestConversationTurn:
    """Tests for the ConversationTurn model."""

    def test_create_valid_turn(
        self,
        sample_clinical_query,
        sample_clinical_response,
        sample_guardrails_result,
    ):
        turn = ConversationTurn(
            session_id="sess-001",
            patient_id="P-12345",
            turn_number=1,
            clinician_id="C-001",
            query=sample_clinical_query,
            response=sample_clinical_response,
            guardrails=sample_guardrails_result,
            total_latency_ms=3500,
            tokens_used={"prompt": 1500, "completion": 800},
        )
        assert turn.session_id == "sess-001"
        assert turn.turn_number == 1
        assert turn.feedback is None
        assert turn.doc_type == "conversation_turn"

    def test_turn_auto_generated_id(
        self,
        sample_clinical_query,
        sample_clinical_response,
        sample_guardrails_result,
    ):
        turn = ConversationTurn(
            session_id="sess-001",
            patient_id="P-12345",
            turn_number=1,
            clinician_id="C-001",
            query=sample_clinical_query,
            response=sample_clinical_response,
            guardrails=sample_guardrails_result,
            total_latency_ms=1000,
        )
        assert turn.id is not None
        assert len(turn.id) > 0

    def test_turn_number_must_be_positive(
        self,
        sample_clinical_query,
        sample_clinical_response,
        sample_guardrails_result,
    ):
        with pytest.raises(ValidationError):
            ConversationTurn(
                session_id="s",
                patient_id="P",
                turn_number=0,
                clinician_id="C",
                query=sample_clinical_query,
                response=sample_clinical_response,
                guardrails=sample_guardrails_result,
                total_latency_ms=100,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# AuditLogEntry
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditLogEntry:
    """Tests for the AuditLogEntry model."""

    def test_create_valid_audit_entry(self):
        entry = AuditLogEntry(
            date_partition="2025-12-01",
            event_type="patient_data_access",
            actor={"clinician_id": "C-001", "role": "physician"},
            action="read_patient_profile",
            resource={"type": "patient_profile", "id": "P-12345"},
            session_id="sess-abc123",
            justification="Clinical query about treatment options",
            outcome="success",
            data_sent_to_llm=True,
            phi_fields_sent=["demographics.age", "active_conditions"],
            phi_fields_redacted=["demographics.name"],
        )
        assert entry.event_type == "patient_data_access"
        assert entry.data_sent_to_llm is True
        assert len(entry.phi_fields_sent) == 2

    def test_audit_entry_auto_id(self):
        entry = AuditLogEntry(
            date_partition="2025-12-01",
            event_type="llm_interaction",
            actor={"system": "cdss"},
            action="generate_response",
            resource={"type": "query", "id": "q-001"},
            session_id="s-001",
            justification="Query processing",
            outcome="success",
            data_sent_to_llm=False,
        )
        assert entry.id is not None

    def test_audit_entry_json_roundtrip(self):
        entry = AuditLogEntry(
            date_partition="2025-12-01",
            event_type="agent_execution",
            actor={"agent": "literature_agent"},
            action="search_pubmed",
            resource={"type": "pubmed", "id": "search-001"},
            session_id="s-002",
            justification="Literature search",
            outcome="success",
            data_sent_to_llm=False,
        )
        restored = AuditLogEntry.model_validate_json(entry.model_dump_json())
        assert restored.event_type == entry.event_type
        assert restored.action == entry.action


# ═══════════════════════════════════════════════════════════════════════════════
# GuardrailsResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardrailsResult:
    """Tests for the GuardrailsResult model."""

    def test_valid_result(self, sample_guardrails_result):
        assert sample_guardrails_result.is_valid is True
        assert len(sample_guardrails_result.disclaimers) == 2

    def test_failed_guardrails(self):
        result = GuardrailsResult(
            is_valid=False,
            hallucination_flags=["Unsupported dosage claim"],
            safety_concerns=["Contraindicated drug for CKD stage 5"],
            disclaimers=["Response flagged for review."],
        )
        assert result.is_valid is False
        assert len(result.hallucination_flags) == 1
        assert len(result.safety_concerns) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# AgentTask
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentTask:
    """Tests for the AgentTask model."""

    def test_create_valid_task(self, sample_agent_task):
        assert sample_agent_task.from_agent == "orchestrator"
        assert sample_agent_task.to_agent == "literature_agent"
        assert sample_agent_task.message_type == "task_request"

    def test_valid_task_types(self):
        for task_type in ("task_request", "task_response", "error"):
            task = AgentTask(
                from_agent="a",
                to_agent="b",
                message_type=task_type,
                payload={"key": "value"},
                session_id="s",
                trace_id="t",
            )
            assert task.message_type == task_type

    def test_invalid_task_type(self):
        with pytest.raises(ValidationError):
            AgentTask(
                from_agent="a",
                to_agent="b",
                message_type="invalid",
                payload={},
                session_id="s",
                trace_id="t",
            )

    def test_task_auto_generated_message_id(self):
        task = AgentTask(
            from_agent="a",
            to_agent="b",
            message_type="task_request",
            payload={},
            session_id="s",
            trace_id="t",
        )
        assert task.message_id is not None


# ═══════════════════════════════════════════════════════════════════════════════
# PubMedArticle and LiteratureEvidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestPubMedArticle:
    """Tests for the PubMedArticle model."""

    def test_create_valid_article(self):
        article = PubMedArticle(
            pmid="32970396",
            title="Dapagliflozin in CKD",
            journal="N Engl J Med",
            publication_date="2020-10-08",
            authors=["Heerspink HJL"],
            abstract="Background: CKD is common.",
            mesh_terms=["Diabetes Mellitus, Type 2"],
            doi="10.1056/NEJMoa2024816",
        )
        assert article.pmid == "32970396"
        assert len(article.authors) == 1

    def test_article_defaults(self):
        article = PubMedArticle(
            pmid="12345",
            title="Test",
            journal="Test J",
            publication_date="2024",
        )
        assert article.abstract == ""
        assert article.mesh_terms == []
        assert article.doi is None
        assert article.pmc_id is None


class TestLiteratureEvidence:
    """Tests for the LiteratureEvidence model."""

    def test_create_valid_evidence(self):
        evidence = LiteratureEvidence(
            papers=[
                PubMedArticle(pmid="123", title="T1", journal="J1", publication_date="2024"),
            ],
            evidence_level="Level I - Systematic Review",
            summary="Strong evidence supports SGLT2 inhibitors.",
            consensus_strength=0.9,
        )
        assert len(evidence.papers) == 1
        assert evidence.consensus_strength == 0.9

    def test_evidence_consensus_bounds(self):
        with pytest.raises(ValidationError):
            LiteratureEvidence(
                evidence_level="Level I",
                summary="Test",
                consensus_strength=1.5,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ProtocolMatch
# ═══════════════════════════════════════════════════════════════════════════════


class TestProtocolMatch:
    """Tests for the ProtocolMatch model."""

    def test_create_valid_match(self):
        match = ProtocolMatch(
            guideline_name="ADA Standards of Care 2024",
            version="2024",
            recommendation="Use SGLT2 inhibitors for T2DM with CKD.",
            evidence_grade="A",
            specialty="endocrinology",
            last_updated=date(2024, 1, 15),
        )
        assert match.evidence_grade == "A"
        assert match.specialty == "endocrinology"

    def test_valid_evidence_grades(self):
        for grade in ("A", "B", "C", "D", "expert_opinion"):
            match = ProtocolMatch(
                guideline_name="Test",
                version="1.0",
                recommendation="Test rec",
                evidence_grade=grade,
                specialty="general",
                last_updated=date(2024, 1, 1),
            )
            assert match.evidence_grade == grade

    def test_invalid_evidence_grade(self):
        with pytest.raises(ValidationError):
            ProtocolMatch(
                guideline_name="Test",
                version="1.0",
                recommendation="Test",
                evidence_grade="F",
                specialty="general",
                last_updated=date(2024, 1, 1),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# PatientContext
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatientContext:
    """Tests for the PatientContext model."""

    def test_create_with_demographics_only(self):
        ctx = PatientContext(
            demographics=Demographics(age=30, sex="female", weight_kg=60.0, height_cm=165.0),
        )
        assert ctx.conditions == []
        assert ctx.medications == []
        assert ctx.timeline_summary is None

    def test_create_full_context(self):
        ctx = PatientContext(
            demographics=Demographics(age=62, sex="male", weight_kg=85.0, height_cm=175.0),
            conditions=[
                MedicalCondition(code="E11.9", coding_system="ICD-10", display="T2DM"),
            ],
            medications=[
                Medication(rxcui="860975", name="Metformin 500mg", dose="500 mg", frequency="BID"),
            ],
            allergies=[
                Allergy(substance="Penicillin", reaction="Anaphylaxis", severity="severe"),
            ],
            timeline_summary="62-year-old male with 5-year history of T2DM.",
        )
        assert len(ctx.conditions) == 1
        assert ctx.timeline_summary is not None
