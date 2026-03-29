"""Tests for the MedicalDocumentChunker in cdss.rag.chunker.

Covers routing by document type, section splitting, token estimation,
medical code extraction, and edge cases for all document types.
"""

from __future__ import annotations

import pytest

from cdss.core.exceptions import DocumentProcessingError
from cdss.rag.chunker import CHARS_PER_TOKEN, DocumentChunk, MedicalDocumentChunker


@pytest.fixture
def chunker() -> MedicalDocumentChunker:
    """Return a default MedicalDocumentChunker instance."""
    return MedicalDocumentChunker(default_chunk_size=512, default_overlap=128)


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_document Routing
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkDocumentRouting:
    """Test that chunk_document routes to the correct method by type."""

    def test_routes_lab_report(self, chunker):
        content = "CBC:\nWBC: 7.5 K/uL\nRBC: 4.8 M/uL\nHemoglobin: 14.2 g/dL"
        chunks = chunker.chunk_document(content, "lab_report", "doc-001")
        assert len(chunks) >= 1
        assert any("lab" in c.section_type for c in chunks)

    def test_routes_lab_alias(self, chunker):
        content = "Complete Blood Count:\nWBC: 7.5\nRBC: 4.8"
        chunks = chunker.chunk_document(content, "lab", "doc-002")
        assert len(chunks) >= 1

    def test_routes_discharge_summary(self, chunker):
        content = (
            "Chief Complaint\nChest pain\n\n"
            "Assessment\nAcute coronary syndrome\n\n"
            "Plan\nStart heparin drip"
        )
        chunks = chunker.chunk_document(content, "discharge_summary", "doc-003")
        assert len(chunks) >= 1

    def test_routes_radiology_report(self, chunker):
        content = (
            "Findings\nNo acute pulmonary disease.\n\n"
            "Impression\nNormal chest radiograph."
        )
        chunks = chunker.chunk_document(content, "radiology_report", "doc-004")
        assert len(chunks) >= 1

    def test_routes_clinical_guideline(self, chunker):
        content = (
            "Recommendation 1: Use SGLT2 inhibitors for T2DM with CKD. Grade A.\n\n"
            "Recommendation 2: Monitor eGFR quarterly. Grade B."
        )
        chunks = chunker.chunk_document(content, "clinical_guideline", "doc-005")
        assert len(chunks) >= 1

    def test_routes_pubmed_abstract(self, chunker):
        content = "This study investigated the efficacy of SGLT2 inhibitors in CKD patients."
        chunks = chunker.chunk_document(content, "pubmed_abstract", "doc-006")
        assert len(chunks) == 1
        assert chunks[0].section_type == "pubmed_abstract"

    def test_routes_unknown_type_to_generic(self, chunker):
        content = "This is a generic medical document with some content about treatments."
        chunks = chunker.chunk_document(content, "unknown_type", "doc-007")
        assert len(chunks) >= 1

    def test_normalizes_document_type(self, chunker):
        content = "Complete Blood Count:\nWBC: 7.5"
        chunks = chunker.chunk_document(content, "  Lab Report  ", "doc-008")
        assert len(chunks) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_lab_report
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkLabReport:
    """Test lab report chunking by test section."""

    def test_splits_by_lab_sections(self, chunker):
        content = (
            "Patient: John Doe\nDate: 2025-01-15\n\n"
            "Complete Blood Count\n"
            "WBC: 7.5 K/uL (4.5-11.0)\n"
            "RBC: 4.8 M/uL (4.5-5.5)\n"
            "Hemoglobin: 14.2 g/dL (13.5-17.5)\n\n"
            "Basic Metabolic Panel\n"
            "Glucose: 110 mg/dL (70-100)\n"
            "BUN: 25 mg/dL (7-20)\n"
            "Creatinine: 1.8 mg/dL (0.7-1.3)\n"
        )
        chunks = chunker.chunk_lab_report(content, "lab-001")
        # Should have at least header, CBC section, and BMP section
        assert len(chunks) >= 2

    def test_chunk_sizes_within_bounds(self, chunker):
        content = (
            "Complete Blood Count\n"
            "WBC: 7.5\nRBC: 4.8\nHgb: 14.2\nHct: 42%\nPlt: 250\n"
        )
        chunks = chunker.chunk_lab_report(content, "lab-002")
        for chunk in chunks:
            estimated_tokens = chunker.estimate_tokens(chunk.content)
            assert estimated_tokens <= 600  # 512 + some tolerance for boundary splitting

    def test_preserves_patient_id_metadata(self, chunker):
        content = "CBC\nWBC: 7.5"
        chunks = chunker.chunk_lab_report(content, "lab-003", metadata={"patient_id": "P-12345"})
        assert all(c.patient_id == "P-12345" for c in chunks)

    def test_extracts_date(self, chunker):
        content = "Date: 2025-01-15\nCBC\nWBC: 7.5"
        chunks = chunker.chunk_lab_report(content, "lab-004")
        assert any(c.date is not None for c in chunks)

    def test_fallback_when_no_sections(self, chunker):
        content = "WBC 7.5, RBC 4.8, Hemoglobin 14.2, Platelet 250"
        chunks = chunker.chunk_lab_report(content, "lab-005")
        assert len(chunks) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_discharge_summary
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkDischargeSummary:
    """Test discharge summary chunking by clinical section."""

    def test_splits_by_section_headers(self, chunker):
        content = (
            "Chief Complaint\n"
            "Chest pain and shortness of breath for 3 days.\n\n"
            "History of Present Illness\n"
            "62-year-old male with history of T2DM presenting with acute chest pain.\n\n"
            "Assessment\n"
            "Acute coronary syndrome with elevated troponin.\n\n"
            "Plan\n"
            "1. Start heparin drip\n2. Cardiology consult\n3. Serial troponins q6h"
        )
        chunks = chunker.chunk_discharge_summary(content, "dc-001")
        section_types = [c.section_type for c in chunks]
        assert any("chief_complaint" in st for st in section_types)
        assert any("assessment" in st for st in section_types)
        assert any("plan" in st for st in section_types)

    def test_handles_256_token_overlap(self, chunker):
        # Create a section with >1024 tokens (>4096 chars) to trigger splitting with overlap
        long_section = "History of Present Illness\n" + ("Patient has a complex history. " * 200)
        chunks = chunker.chunk_discharge_summary(long_section, "dc-002")
        assert len(chunks) >= 2

    def test_metadata_includes_document_type(self, chunker):
        content = "Assessment\nAcute coronary syndrome"
        chunks = chunker.chunk_discharge_summary(content, "dc-003")
        for chunk in chunks:
            assert chunk.metadata.get("document_type") == "discharge_summary"


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_radiology_report
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkRadiologyReport:
    """Test radiology report chunking with findings/impression split."""

    def test_splits_findings_and_impression(self, chunker):
        content = (
            "Findings\n"
            "The lungs are clear bilaterally. No pleural effusion. Heart size is normal.\n\n"
            "Impression\n"
            "1. Normal chest radiograph.\n2. No acute pulmonary disease."
        )
        chunks = chunker.chunk_radiology_report(content, "rad-001")
        section_types = [c.section_type for c in chunks]
        assert "radiology_findings" in section_types
        assert "radiology_impression" in section_types

    def test_findings_and_impression_share_link_id(self, chunker):
        content = (
            "Findings\nClear lungs.\n\n"
            "Impression\nNormal radiograph."
        )
        chunks = chunker.chunk_radiology_report(content, "rad-002")
        link_ids = {c.metadata.get("link_id") for c in chunks}
        # All chunks should share the same link_id
        assert len(link_ids) == 1
        assert None not in link_ids

    def test_heuristic_splitting_without_headers(self, chunker):
        content = (
            "The lungs are clear bilaterally. Heart size is normal.\n"
            "IMPRESSION: Normal chest radiograph."
        )
        chunks = chunker.chunk_radiology_report(content, "rad-003")
        assert len(chunks) >= 1

    def test_radiology_preserves_medical_codes(self, chunker):
        content = (
            "Findings\n"
            "Patient with diagnosis E11.9 shows no acute findings.\n\n"
            "Impression\nNormal study."
        )
        chunks = chunker.chunk_radiology_report(content, "rad-004")
        all_codes = []
        for chunk in chunks:
            all_codes.extend(chunk.medical_codes)
        assert any("ICD10:E11.9" in code for code in all_codes)


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_clinical_guideline
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkClinicalGuideline:
    """Test clinical guideline chunking with evidence grade preservation."""

    def test_splits_by_recommendations(self, chunker):
        content = (
            "Recommendation 1: Use SGLT2 inhibitors for T2DM with CKD. Grade A.\n"
            "Evidence: DAPA-CKD trial (PMID: 32970396).\n\n"
            "Recommendation 2: Monitor eGFR quarterly in CKD patients. Grade B.\n"
            "Evidence: KDIGO 2024 guidelines."
        )
        chunks = chunker.chunk_clinical_guideline(content, "guide-001")
        assert len(chunks) >= 2

    def test_preserves_evidence_grade(self, chunker):
        content = (
            "Recommendation 1: Use SGLT2 inhibitors. Grade A.\n"
            "Supporting evidence from DAPA-CKD.\n\n"
            "Recommendation 2: Monitor renal function. Grade B.\n"
            "Evidence from KDIGO guidelines."
        )
        chunks = chunker.chunk_clinical_guideline(content, "guide-002")
        grades = [c.metadata.get("evidence_grade") for c in chunks]
        # At least some chunks should have evidence grades
        assert any(g is not None for g in grades)

    def test_falls_back_to_section_splitting(self, chunker):
        content = (
            "Background\n"
            "Type 2 diabetes mellitus is a chronic metabolic disorder.\n\n"
            "Methods\n"
            "Systematic review of randomized controlled trials.\n\n"
            "Results\n"
            "SGLT2 inhibitors reduced CKD progression by 39%."
        )
        chunks = chunker.chunk_clinical_guideline(content, "guide-003")
        assert len(chunks) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_pubmed_abstract
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkPubmedAbstract:
    """Test PubMed abstract chunking (single chunk)."""

    def test_returns_single_chunk(self, chunker):
        content = (
            "BACKGROUND: Type 2 diabetes with CKD has limited treatment options. "
            "METHODS: We randomized 4304 participants. "
            "RESULTS: Dapagliflozin reduced primary endpoint by 39%."
        )
        chunks = chunker.chunk_pubmed_abstract(content, "pmid-32970396")
        assert len(chunks) == 1
        assert chunks[0].section_type == "pubmed_abstract"

    def test_preserves_mesh_terms_in_metadata(self, chunker):
        content = "Abstract text about diabetes treatment."
        metadata = {
            "mesh_terms": ["Diabetes Mellitus, Type 2", "SGLT2 Inhibitors"],
            "pmid": "32970396",
            "title": "DAPA-CKD Trial",
            "authors": ["Heerspink HJL"],
            "journal": "N Engl J Med",
        }
        chunks = chunker.chunk_pubmed_abstract(content, "pmid-32970396", metadata)
        assert chunks[0].metadata["pmid"] == "32970396"
        assert len(chunks[0].metadata["mesh_terms"]) == 2
        assert chunks[0].metadata["title"] == "DAPA-CKD Trial"

    def test_confidence_score_is_1(self, chunker):
        content = "Abstract about clinical trial results."
        chunks = chunker.chunk_pubmed_abstract(content, "pmid-12345")
        assert chunks[0].confidence_score == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_generic
# ═══════════════════════════════════════════════════════════════════════════════


class TestChunkGeneric:
    """Test generic chunking with token-based splitting and overlap."""

    def test_short_content_single_chunk(self, chunker):
        content = "This is a short medical note about a patient follow-up visit."
        chunks = chunker.chunk_generic(content, "gen-001")
        assert len(chunks) == 1

    def test_long_content_multiple_chunks(self, chunker):
        # Create content exceeding 512 tokens (>2048 chars)
        content = "Patient presents with multiple comorbidities. " * 100
        chunks = chunker.chunk_generic(content, "gen-002")
        assert len(chunks) >= 2

    def test_section_based_splitting_when_headers_present(self, chunker):
        content = (
            "Assessment\n"
            "Patient has uncontrolled diabetes.\n\n"
            "Plan\n"
            "Increase metformin dose to 1000 mg BID."
        )
        chunks = chunker.chunk_generic(content, "gen-003")
        section_types = [c.section_type for c in chunks]
        assert any("assessment" in st for st in section_types)

    def test_generic_confidence_score(self, chunker):
        content = "Medical note content without section headers."
        chunks = chunker.chunk_generic(content, "gen-004")
        for chunk in chunks:
            assert chunk.confidence_score <= 0.85


# ═══════════════════════════════════════════════════════════════════════════════
# estimate_tokens
# ═══════════════════════════════════════════════════════════════════════════════


class TestEstimateTokens:
    """Test token estimation."""

    def test_empty_string(self):
        assert MedicalDocumentChunker.estimate_tokens("") == 0

    def test_known_length(self):
        # 100 characters / 4 = 25 tokens
        text = "a" * 100
        assert MedicalDocumentChunker.estimate_tokens(text) == 25

    def test_approximate_accuracy(self):
        text = "This is a medical document with approximately twenty tokens."
        tokens = MedicalDocumentChunker.estimate_tokens(text)
        assert 10 <= tokens <= 30  # reasonable range


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases for the chunker."""

    def test_empty_content_raises_error(self, chunker):
        with pytest.raises(DocumentProcessingError):
            chunker.chunk_document("", "lab_report", "doc-001")

    def test_whitespace_only_raises_error(self, chunker):
        with pytest.raises(DocumentProcessingError):
            chunker.chunk_document("   \n\t\n   ", "lab_report", "doc-001")

    def test_very_short_content(self, chunker):
        content = "Normal."
        chunks = chunker.chunk_document(content, "discharge_summary", "doc-001")
        assert len(chunks) >= 1
        assert chunks[0].content == "Normal."

    def test_no_section_headers_in_discharge(self, chunker):
        content = "Patient was admitted for chest pain and discharged in stable condition."
        chunks = chunker.chunk_discharge_summary(content, "dc-no-headers")
        assert len(chunks) >= 1

    def test_chunk_id_deterministic(self, chunker):
        id1 = chunker._generate_chunk_id("doc-001", "findings", 0)
        id2 = chunker._generate_chunk_id("doc-001", "findings", 0)
        assert id1 == id2
        assert id1 == "doc-001_findings_0"

    def test_medical_code_extraction_icd10(self, chunker):
        text = "Patient diagnosed with E11.9 (Type 2 DM) and N18.3 (CKD Stage 3)."
        codes = chunker._extract_medical_codes(text)
        assert "ICD10:E11.9" in codes
        assert "ICD10:N18.3" in codes

    def test_medical_code_extraction_loinc(self, chunker):
        text = "Lab results: LOINC 4548-4 HbA1c: 7.2%"
        codes = chunker._extract_medical_codes(text)
        assert "LOINC:4548-4" in codes

    def test_prescription_single_chunk(self, chunker):
        content = (
            "Rx: Metformin 500 mg\n"
            "Sig: Take 1 tablet by mouth twice daily with meals\n"
            "Disp: 60 tablets\n"
            "Refills: 3"
        )
        chunks = chunker.chunk_prescription(content, "rx-001")
        assert len(chunks) == 1
        assert chunks[0].section_type == "prescription"

    def test_date_extraction(self, chunker):
        text = "Report date: 2025-01-15\nFollow-up: 02/28/2025"
        date_val = chunker._extract_first_date(text)
        assert date_val is not None
        assert "2025" in date_val

    def test_custom_chunk_size(self):
        chunker = MedicalDocumentChunker(default_chunk_size=256, default_overlap=64)
        content = "Long clinical note. " * 200
        chunks = chunker.chunk_generic(content, "custom-size-001")
        assert len(chunks) >= 3  # should produce more chunks with smaller size

    def test_metadata_propagation(self, chunker):
        content = "CBC\nWBC: 7.5"
        metadata = {"patient_id": "P-001", "facility": "Hospital A", "page_number": 1}
        chunks = chunker.chunk_document(content, "lab_report", "doc-meta", metadata=metadata)
        for chunk in chunks:
            assert chunk.patient_id == "P-001"
