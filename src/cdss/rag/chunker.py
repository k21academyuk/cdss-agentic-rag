"""Medical document chunking for the Clinical Decision Support System.

Provides domain-aware chunking strategies for different medical document types,
ensuring that clinical context, section boundaries, and medical codes are
preserved across chunk boundaries. Chunking rules are tailored per document
type to optimize downstream retrieval quality.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cdss.core.exceptions import DocumentProcessingError
from cdss.core.logging import get_logger

logger = get_logger(__name__)

# Approximate ratio: 1 token ~ 4 characters (conservative estimate for English text)
CHARS_PER_TOKEN = 4


@dataclass
class DocumentChunk:
    """A single chunk of a medical document with full provenance metadata.

    Attributes:
        content: The textual content of this chunk.
        chunk_id: Unique identifier for this chunk.
        document_id: Identifier of the source document.
        section_type: Clinical section type (e.g. "lab_results", "medications").
        page_number: Page number in the original document, if known.
        patient_id: Associated patient identifier, if applicable.
        date: Date associated with the document or section (ISO 8601).
        medical_codes: ICD-10, CPT, LOINC, or other medical codes found.
        confidence_score: Confidence in chunk quality (0.0 - 1.0).
        metadata: Additional key-value metadata for provenance.
    """

    content: str
    chunk_id: str
    document_id: str
    section_type: str
    page_number: int | None = None
    patient_id: str | None = None
    date: str | None = None
    medical_codes: list[str] = field(default_factory=list)
    confidence_score: float = 1.0
    metadata: dict = field(default_factory=dict)


class MedicalDocumentChunker:
    """Domain-aware chunking for medical documents.

    Routes documents to type-specific chunking strategies that respect
    clinical section boundaries and preserve medical coding information.

    Chunking rules by document type:
      - Lab Reports: 256-512 tokens, by test section, preserve tables as JSON.
      - Prescriptions: Full document as single chunk.
      - Discharge Summaries: 512-1024 tokens, by clinical section
        (HPI, Assessment, Plan), 256-token overlap.
      - Radiology Reports: 256-512 tokens, findings + impression separate,
        linked via metadata.
      - Clinical Guidelines: 512-1024 tokens, by recommendation/evidence level.
      - PubMed Abstracts: Full abstract, include MeSH + PMID.
    """

    SECTION_HEADERS: list[str] = [
        "chief complaint",
        "history of present illness",
        "past medical history",
        "medications",
        "allergies",
        "physical examination",
        "assessment",
        "plan",
        "laboratory results",
        "imaging",
        "procedures",
        "discharge instructions",
        "findings",
        "impression",
        "recommendations",
        "background",
        "methods",
        "results",
        "conclusion",
        "discussion",
    ]

    # Regex patterns for extracting medical codes
    _ICD10_PATTERN = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,4})?)\b")
    _CPT_PATTERN = re.compile(r"\b(\d{5})\b")
    _LOINC_PATTERN = re.compile(r"\b(\d{4,5}-\d)\b")
    _DATE_PATTERN = re.compile(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b"
    )

    # Common lab test section markers
    _LAB_SECTION_MARKERS: list[str] = [
        "complete blood count",
        "cbc",
        "basic metabolic panel",
        "bmp",
        "comprehensive metabolic panel",
        "cmp",
        "lipid panel",
        "liver function",
        "lft",
        "thyroid",
        "coagulation",
        "urinalysis",
        "hemoglobin a1c",
        "hba1c",
        "iron studies",
        "cardiac enzymes",
        "troponin",
        "bnp",
        "arterial blood gas",
        "abg",
    ]

    # Document type routing table
    _DOCUMENT_TYPE_MAP: dict[str, str] = {
        "lab_report": "chunk_lab_report",
        "lab": "chunk_lab_report",
        "prescription": "chunk_prescription",
        "rx": "chunk_prescription",
        "discharge_summary": "chunk_discharge_summary",
        "discharge": "chunk_discharge_summary",
        "radiology_report": "chunk_radiology_report",
        "radiology": "chunk_radiology_report",
        "imaging": "chunk_radiology_report",
        "clinical_guideline": "chunk_clinical_guideline",
        "guideline": "chunk_clinical_guideline",
        "protocol": "chunk_clinical_guideline",
        "pubmed_abstract": "chunk_pubmed_abstract",
        "pubmed": "chunk_pubmed_abstract",
        "abstract": "chunk_pubmed_abstract",
    }

    def __init__(
        self, default_chunk_size: int = 512, default_overlap: int = 128
    ) -> None:
        """Initialize the chunker with default size parameters.

        Args:
            default_chunk_size: Default maximum chunk size in tokens.
            default_overlap: Default overlap between consecutive chunks in tokens.
        """
        self.default_chunk_size = default_chunk_size
        self.default_overlap = default_overlap
        logger.info(
            "MedicalDocumentChunker initialized",
            extra={
                "default_chunk_size": default_chunk_size,
                "default_overlap": default_overlap,
            },
        )

    def chunk_document(
        self,
        content: str,
        document_type: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Chunk a document based on its type using domain-aware rules.

        Routes to the appropriate type-specific chunking method based on
        the document_type parameter.

        Args:
            content: Full text content of the document.
            document_type: Type identifier (e.g. "lab_report", "discharge_summary").
            document_id: Unique identifier for this document.
            metadata: Optional metadata dict to propagate to all chunks.

        Returns:
            List of DocumentChunk instances with full provenance metadata.

        Raises:
            DocumentProcessingError: If the content is empty or chunking fails.
        """
        if not content or not content.strip():
            raise DocumentProcessingError(
                message="Cannot chunk empty document content.",
                document_id=document_id,
                document_type=document_type,
            )

        metadata = metadata or {}
        normalized_type = document_type.lower().strip().replace(" ", "_")

        method_name = self._DOCUMENT_TYPE_MAP.get(normalized_type)

        logger.info(
            "Chunking document",
            extra={
                "document_id": document_id,
                "document_type": document_type,
                "content_length": len(content),
                "estimated_tokens": self.estimate_tokens(content),
                "method": method_name or "chunk_generic",
            },
        )

        if method_name is not None:
            method = getattr(self, method_name)
            chunks = method(content, document_id, metadata)
        else:
            logger.warning(
                "Unknown document type, using generic chunking",
                extra={"document_type": document_type, "document_id": document_id},
            )
            chunks = self.chunk_generic(content, document_id, metadata)

        logger.info(
            "Chunking complete",
            extra={
                "document_id": document_id,
                "chunk_count": len(chunks),
            },
        )

        return chunks

    def chunk_lab_report(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Chunk lab report by test section (CBC, metabolic panel, etc.).

        Uses 256-512 token chunks. Each lab test section becomes its own chunk
        when possible. Tables are preserved inline. If a section exceeds
        512 tokens, it is split with overlap.

        Args:
            content: Full lab report text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances.
        """
        metadata = metadata or {}
        chunks: list[DocumentChunk] = []
        patient_id = metadata.get("patient_id")
        date = self._extract_first_date(content) or metadata.get("date")

        # Try to split by lab section markers
        lab_sections = self._split_by_lab_sections(content)

        if not lab_sections:
            # Fall back to generic section splitting
            lab_sections = [("laboratory_results", content)]

        for section_name, section_content in lab_sections:
            section_content = section_content.strip()
            if not section_content:
                continue

            estimated_tokens = self.estimate_tokens(section_content)
            medical_codes = self._extract_medical_codes(section_content)

            if estimated_tokens <= 512:
                # Section fits in one chunk
                chunk = DocumentChunk(
                    content=section_content,
                    chunk_id=self._generate_chunk_id(document_id, section_name, 0),
                    document_id=document_id,
                    section_type=f"lab_{section_name}",
                    page_number=metadata.get("page_number"),
                    patient_id=patient_id,
                    date=date,
                    medical_codes=medical_codes,
                    confidence_score=1.0,
                    metadata={
                        **metadata,
                        "document_type": "lab_report",
                        "lab_section": section_name,
                    },
                )
                chunks.append(chunk)
            else:
                # Split large sections with overlap
                sub_chunks = self._split_by_tokens(
                    section_content, max_tokens=512, overlap=128
                )
                for idx, sub_content in enumerate(sub_chunks):
                    sub_codes = self._extract_medical_codes(sub_content)
                    chunk = DocumentChunk(
                        content=sub_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, section_name, idx
                        ),
                        document_id=document_id,
                        section_type=f"lab_{section_name}",
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=sub_codes,
                        confidence_score=0.95,
                        metadata={
                            **metadata,
                            "document_type": "lab_report",
                            "lab_section": section_name,
                            "chunk_index": idx,
                            "total_sub_chunks": len(sub_chunks),
                        },
                    )
                    chunks.append(chunk)

        if not chunks:
            chunks.append(
                DocumentChunk(
                    content=content.strip(),
                    chunk_id=self._generate_chunk_id(document_id, "lab_full", 0),
                    document_id=document_id,
                    section_type="lab_results",
                    patient_id=patient_id,
                    date=date,
                    medical_codes=self._extract_medical_codes(content),
                    confidence_score=0.8,
                    metadata={**metadata, "document_type": "lab_report"},
                )
            )

        return chunks

    def chunk_prescription(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Keep full prescription as a single chunk.

        Prescriptions are short documents and should be preserved in their
        entirety to avoid splitting dosage instructions across chunks.

        Args:
            content: Full prescription text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List containing a single DocumentChunk.
        """
        metadata = metadata or {}
        patient_id = metadata.get("patient_id")
        date = self._extract_first_date(content) or metadata.get("date")
        medical_codes = self._extract_medical_codes(content)

        chunk = DocumentChunk(
            content=content.strip(),
            chunk_id=self._generate_chunk_id(document_id, "prescription", 0),
            document_id=document_id,
            section_type="prescription",
            page_number=metadata.get("page_number"),
            patient_id=patient_id,
            date=date,
            medical_codes=medical_codes,
            confidence_score=1.0,
            metadata={**metadata, "document_type": "prescription"},
        )

        return [chunk]

    def chunk_discharge_summary(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Chunk discharge summary by clinical section.

        Uses 512-1024 token chunks with 256-token overlap. Splits by
        clinical section headers (HPI, Assessment, Plan, etc.).

        Args:
            content: Full discharge summary text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances.
        """
        metadata = metadata or {}
        chunks: list[DocumentChunk] = []
        patient_id = metadata.get("patient_id")
        date = self._extract_first_date(content) or metadata.get("date")

        sections = self._split_by_sections(content)

        if not sections:
            sections = [("discharge_summary", content)]

        for section_name, section_content in sections:
            section_content = section_content.strip()
            if not section_content:
                continue

            estimated_tokens = self.estimate_tokens(section_content)
            medical_codes = self._extract_medical_codes(section_content)

            # Normalize section name for section_type
            normalized_section = section_name.lower().replace(" ", "_")

            if estimated_tokens <= 1024:
                chunk = DocumentChunk(
                    content=section_content,
                    chunk_id=self._generate_chunk_id(
                        document_id, normalized_section, 0
                    ),
                    document_id=document_id,
                    section_type=normalized_section,
                    page_number=metadata.get("page_number"),
                    patient_id=patient_id,
                    date=date,
                    medical_codes=medical_codes,
                    confidence_score=1.0,
                    metadata={
                        **metadata,
                        "document_type": "discharge_summary",
                        "clinical_section": section_name,
                    },
                )
                chunks.append(chunk)
            else:
                # Split large sections with 256-token overlap
                sub_chunks = self._split_by_tokens(
                    section_content, max_tokens=1024, overlap=256
                )
                for idx, sub_content in enumerate(sub_chunks):
                    sub_codes = self._extract_medical_codes(sub_content)
                    chunk = DocumentChunk(
                        content=sub_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, normalized_section, idx
                        ),
                        document_id=document_id,
                        section_type=normalized_section,
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=sub_codes,
                        confidence_score=0.95,
                        metadata={
                            **metadata,
                            "document_type": "discharge_summary",
                            "clinical_section": section_name,
                            "chunk_index": idx,
                            "total_sub_chunks": len(sub_chunks),
                        },
                    )
                    chunks.append(chunk)

        if not chunks:
            chunks = self._fallback_chunking(
                content, document_id, "discharge_summary", metadata
            )

        return chunks

    def chunk_radiology_report(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Chunk radiology report with findings and impression as separate linked chunks.

        Creates separate chunks for findings and impression sections, linked
        via shared metadata. Uses 256-512 token chunks.

        Args:
            content: Full radiology report text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances with linked findings and impressions.
        """
        metadata = metadata or {}
        chunks: list[DocumentChunk] = []
        patient_id = metadata.get("patient_id")
        date = self._extract_first_date(content) or metadata.get("date")

        # Generate a linking ID so findings and impression can reference each other
        link_id = f"rad-link-{uuid.uuid4().hex[:12]}"

        sections = self._split_by_sections(content)

        findings_content: str = ""
        impression_content: str = ""
        other_sections: list[tuple[str, str]] = []

        for section_name, section_content in sections:
            lower_name = section_name.lower().strip()
            if lower_name == "findings":
                findings_content = section_content.strip()
            elif lower_name == "impression":
                impression_content = section_content.strip()
            else:
                other_sections.append((section_name, section_content))

        # If we could not parse sections, try heuristic splitting
        if not findings_content and not impression_content:
            findings_content, impression_content = self._split_radiology_heuristic(
                content
            )

        # Create findings chunk(s)
        if findings_content:
            findings_tokens = self.estimate_tokens(findings_content)
            if findings_tokens <= 512:
                chunks.append(
                    DocumentChunk(
                        content=findings_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, "findings", 0
                        ),
                        document_id=document_id,
                        section_type="radiology_findings",
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=self._extract_medical_codes(findings_content),
                        confidence_score=1.0,
                        metadata={
                            **metadata,
                            "document_type": "radiology_report",
                            "radiology_section": "findings",
                            "link_id": link_id,
                        },
                    )
                )
            else:
                sub_chunks = self._split_by_tokens(
                    findings_content, max_tokens=512, overlap=128
                )
                for idx, sub_content in enumerate(sub_chunks):
                    chunks.append(
                        DocumentChunk(
                            content=sub_content,
                            chunk_id=self._generate_chunk_id(
                                document_id, "findings", idx
                            ),
                            document_id=document_id,
                            section_type="radiology_findings",
                            page_number=metadata.get("page_number"),
                            patient_id=patient_id,
                            date=date,
                            medical_codes=self._extract_medical_codes(sub_content),
                            confidence_score=0.95,
                            metadata={
                                **metadata,
                                "document_type": "radiology_report",
                                "radiology_section": "findings",
                                "link_id": link_id,
                                "chunk_index": idx,
                                "total_sub_chunks": len(sub_chunks),
                            },
                        )
                    )

        # Create impression chunk(s)
        if impression_content:
            impression_tokens = self.estimate_tokens(impression_content)
            if impression_tokens <= 512:
                chunks.append(
                    DocumentChunk(
                        content=impression_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, "impression", 0
                        ),
                        document_id=document_id,
                        section_type="radiology_impression",
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=self._extract_medical_codes(impression_content),
                        confidence_score=1.0,
                        metadata={
                            **metadata,
                            "document_type": "radiology_report",
                            "radiology_section": "impression",
                            "link_id": link_id,
                        },
                    )
                )
            else:
                sub_chunks = self._split_by_tokens(
                    impression_content, max_tokens=512, overlap=128
                )
                for idx, sub_content in enumerate(sub_chunks):
                    chunks.append(
                        DocumentChunk(
                            content=sub_content,
                            chunk_id=self._generate_chunk_id(
                                document_id, "impression", idx
                            ),
                            document_id=document_id,
                            section_type="radiology_impression",
                            page_number=metadata.get("page_number"),
                            patient_id=patient_id,
                            date=date,
                            medical_codes=self._extract_medical_codes(sub_content),
                            confidence_score=0.95,
                            metadata={
                                **metadata,
                                "document_type": "radiology_report",
                                "radiology_section": "impression",
                                "link_id": link_id,
                                "chunk_index": idx,
                                "total_sub_chunks": len(sub_chunks),
                            },
                        )
                    )

        # Handle other sections (technique, comparison, clinical history, etc.)
        for section_name, section_content in other_sections:
            section_content = section_content.strip()
            if not section_content:
                continue
            normalized = section_name.lower().replace(" ", "_")
            sub_chunks_list = self._split_by_tokens(
                section_content, max_tokens=512, overlap=128
            )
            for idx, sub_content in enumerate(sub_chunks_list):
                chunks.append(
                    DocumentChunk(
                        content=sub_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, normalized, idx
                        ),
                        document_id=document_id,
                        section_type=f"radiology_{normalized}",
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=self._extract_medical_codes(sub_content),
                        confidence_score=0.9,
                        metadata={
                            **metadata,
                            "document_type": "radiology_report",
                            "radiology_section": section_name,
                            "link_id": link_id,
                        },
                    )
                )

        if not chunks:
            chunks = self._fallback_chunking(
                content, document_id, "radiology_report", metadata
            )
            for chunk in chunks:
                chunk.metadata["link_id"] = link_id

        return chunks

    def chunk_clinical_guideline(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Chunk clinical guideline by recommendation, preserving evidence grade.

        Uses 512-1024 token chunks. Attempts to identify individual
        recommendations and their evidence levels, keeping each as
        a self-contained chunk.

        Args:
            content: Full clinical guideline text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances.
        """
        metadata = metadata or {}
        chunks: list[DocumentChunk] = []

        # Try to split by recommendation markers
        recommendations = self._split_by_recommendations(content)

        if recommendations:
            for idx, (rec_content, evidence_grade) in enumerate(recommendations):
                rec_content = rec_content.strip()
                if not rec_content:
                    continue

                estimated_tokens = self.estimate_tokens(rec_content)
                medical_codes = self._extract_medical_codes(rec_content)

                if estimated_tokens <= 1024:
                    chunk = DocumentChunk(
                        content=rec_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, "recommendation", idx
                        ),
                        document_id=document_id,
                        section_type="guideline_recommendation",
                        page_number=metadata.get("page_number"),
                        patient_id=None,
                        date=metadata.get("date"),
                        medical_codes=medical_codes,
                        confidence_score=1.0,
                        metadata={
                            **metadata,
                            "document_type": "clinical_guideline",
                            "evidence_grade": evidence_grade,
                            "recommendation_index": idx,
                        },
                    )
                    chunks.append(chunk)
                else:
                    sub_chunks = self._split_by_tokens(
                        rec_content, max_tokens=1024, overlap=256
                    )
                    for sub_idx, sub_content in enumerate(sub_chunks):
                        chunk = DocumentChunk(
                            content=sub_content,
                            chunk_id=self._generate_chunk_id(
                                document_id, f"recommendation_{idx}", sub_idx
                            ),
                            document_id=document_id,
                            section_type="guideline_recommendation",
                            page_number=metadata.get("page_number"),
                            patient_id=None,
                            date=metadata.get("date"),
                            medical_codes=self._extract_medical_codes(sub_content),
                            confidence_score=0.95,
                            metadata={
                                **metadata,
                                "document_type": "clinical_guideline",
                                "evidence_grade": evidence_grade,
                                "recommendation_index": idx,
                                "chunk_index": sub_idx,
                                "total_sub_chunks": len(sub_chunks),
                            },
                        )
                        chunks.append(chunk)
        else:
            # Fall back to section-based chunking
            sections = self._split_by_sections(content)
            if not sections:
                sections = [("guideline", content)]

            for section_name, section_content in sections:
                section_content = section_content.strip()
                if not section_content:
                    continue

                normalized_section = section_name.lower().replace(" ", "_")
                sub_chunks = self._split_by_tokens(
                    section_content, max_tokens=1024, overlap=256
                )
                for idx, sub_content in enumerate(sub_chunks):
                    chunk = DocumentChunk(
                        content=sub_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, normalized_section, idx
                        ),
                        document_id=document_id,
                        section_type=f"guideline_{normalized_section}",
                        page_number=metadata.get("page_number"),
                        patient_id=None,
                        date=metadata.get("date"),
                        medical_codes=self._extract_medical_codes(sub_content),
                        confidence_score=0.9,
                        metadata={
                            **metadata,
                            "document_type": "clinical_guideline",
                            "clinical_section": section_name,
                            "chunk_index": idx,
                        },
                    )
                    chunks.append(chunk)

        if not chunks:
            chunks = self._fallback_chunking(
                content, document_id, "clinical_guideline", metadata
            )

        return chunks

    def chunk_pubmed_abstract(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Keep full PubMed abstract as a single chunk with MeSH terms and PMID.

        PubMed abstracts are typically short enough to fit in a single chunk.
        Preserves MeSH descriptors and PubMed ID in metadata for precise
        citation and retrieval.

        Args:
            content: Full abstract text.
            document_id: Unique identifier for this document (often PMID).
            metadata: Optional metadata; should include "mesh_terms" and "pmid".

        Returns:
            List containing a single DocumentChunk.
        """
        metadata = metadata or {}
        medical_codes = self._extract_medical_codes(content)

        # Extract MeSH terms from metadata if present
        mesh_terms: list[str] = metadata.get("mesh_terms", [])
        pmid: str = metadata.get("pmid", document_id)

        chunk = DocumentChunk(
            content=content.strip(),
            chunk_id=self._generate_chunk_id(document_id, "abstract", 0),
            document_id=document_id,
            section_type="pubmed_abstract",
            page_number=None,
            patient_id=None,
            date=metadata.get("publication_date", metadata.get("date")),
            medical_codes=medical_codes,
            confidence_score=1.0,
            metadata={
                **metadata,
                "document_type": "pubmed_abstract",
                "pmid": pmid,
                "mesh_terms": mesh_terms,
                "title": metadata.get("title", ""),
                "authors": metadata.get("authors", []),
                "journal": metadata.get("journal", ""),
            },
        )

        return [chunk]

    def chunk_generic(
        self,
        content: str,
        document_id: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Generic semantic chunking with overlap.

        Uses the default chunk size and overlap. First tries section-based
        splitting, then falls back to token-based splitting.

        Args:
            content: Full document text.
            document_id: Unique identifier for this document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances.
        """
        metadata = metadata or {}
        chunks: list[DocumentChunk] = []
        patient_id = metadata.get("patient_id")
        date = self._extract_first_date(content) or metadata.get("date")

        # Try section-based splitting first
        sections = self._split_by_sections(content)

        if sections and len(sections) > 1:
            for section_name, section_content in sections:
                section_content = section_content.strip()
                if not section_content:
                    continue

                normalized_section = section_name.lower().replace(" ", "_")
                sub_chunks = self._split_by_tokens(
                    section_content,
                    max_tokens=self.default_chunk_size,
                    overlap=self.default_overlap,
                )
                for idx, sub_content in enumerate(sub_chunks):
                    chunk = DocumentChunk(
                        content=sub_content,
                        chunk_id=self._generate_chunk_id(
                            document_id, normalized_section, idx
                        ),
                        document_id=document_id,
                        section_type=normalized_section,
                        page_number=metadata.get("page_number"),
                        patient_id=patient_id,
                        date=date,
                        medical_codes=self._extract_medical_codes(sub_content),
                        confidence_score=0.85,
                        metadata={
                            **metadata,
                            "document_type": "generic",
                            "clinical_section": section_name,
                            "chunk_index": idx,
                        },
                    )
                    chunks.append(chunk)
        else:
            # Pure token-based splitting
            token_chunks = self._split_by_tokens(
                content,
                max_tokens=self.default_chunk_size,
                overlap=self.default_overlap,
            )
            for idx, sub_content in enumerate(token_chunks):
                chunk = DocumentChunk(
                    content=sub_content,
                    chunk_id=self._generate_chunk_id(document_id, "generic", idx),
                    document_id=document_id,
                    section_type="generic",
                    page_number=metadata.get("page_number"),
                    patient_id=patient_id,
                    date=date,
                    medical_codes=self._extract_medical_codes(sub_content),
                    confidence_score=0.8,
                    metadata={
                        **metadata,
                        "document_type": "generic",
                        "chunk_index": idx,
                        "total_chunks": len(token_chunks),
                    },
                )
                chunks.append(chunk)

        return chunks

    # ── Internal helper methods ──────────────────────────────────────────────

    def _split_by_sections(self, content: str) -> list[tuple[str, str]]:
        """Split document by section headers.

        Scans for known clinical section headers (case-insensitive) and splits
        the document at each header boundary.

        Args:
            content: Full document text.

        Returns:
            List of (section_name, section_content) tuples. Content before
            the first recognized header is placed in a "preamble" section.
        """
        # Build pattern from known headers
        escaped_headers = [re.escape(h) for h in self.SECTION_HEADERS]
        pattern = re.compile(
            r"^[\s]*(?:#+\s*)?(" + "|".join(escaped_headers) + r")[\s]*:?\s*$",
            re.IGNORECASE | re.MULTILINE,
        )

        matches = list(pattern.finditer(content))

        if not matches:
            return []

        sections: list[tuple[str, str]] = []

        # Content before first header
        preamble = content[: matches[0].start()].strip()
        if preamble:
            sections.append(("preamble", preamble))

        for i, match in enumerate(matches):
            section_name = match.group(1).strip().lower()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end].strip()
            if section_content:
                sections.append((section_name, section_content))

        return sections

    def _split_by_tokens(
        self, text: str, max_tokens: int, overlap: int
    ) -> list[str]:
        """Split text into chunks by approximate token count with overlap.

        Uses paragraph and sentence boundaries for cleaner splits when
        possible, falling back to character-based splitting.

        Args:
            text: Text to split.
            max_tokens: Maximum tokens per chunk.
            overlap: Number of overlapping tokens between consecutive chunks.

        Returns:
            List of text chunks.
        """
        text = text.strip()
        if not text:
            return []

        max_chars = max_tokens * CHARS_PER_TOKEN
        overlap_chars = overlap * CHARS_PER_TOKEN

        total_chars = len(text)
        if total_chars <= max_chars:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < total_chars:
            end = min(start + max_chars, total_chars)

            # If not at the end, try to find a clean break point
            if end < total_chars:
                # Try paragraph break first
                paragraph_break = text.rfind("\n\n", start + max_chars // 2, end)
                if paragraph_break > start:
                    end = paragraph_break

                else:
                    # Try sentence break (period followed by space or newline)
                    sentence_break = -1
                    search_start = start + max_chars // 2
                    for pattern_str in [". ", ".\n", "? ", "?\n", "! ", "!\n"]:
                        pos = text.rfind(pattern_str, search_start, end)
                        if pos > sentence_break:
                            sentence_break = pos + 1  # Include the period

                    if sentence_break > start:
                        end = sentence_break
                    else:
                        # Try newline break
                        newline_break = text.rfind("\n", start + max_chars // 2, end)
                        if newline_break > start:
                            end = newline_break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)

            if end >= total_chars:
                break

            # Move start forward, accounting for overlap
            start = max(end - overlap_chars, start + 1)

        return chunks

    def _split_by_lab_sections(
        self, content: str
    ) -> list[tuple[str, str]]:
        """Split lab report content by lab test section markers.

        Args:
            content: Full lab report text.

        Returns:
            List of (section_name, section_content) tuples.
        """
        escaped_markers = [re.escape(m) for m in self._LAB_SECTION_MARKERS]
        pattern = re.compile(
            r"(?:^|\n)[\s]*(?:#+\s*)?(" + "|".join(escaped_markers) + r")[\s]*:?\s*(?:\n|$)",
            re.IGNORECASE,
        )

        matches = list(pattern.finditer(content))

        if not matches:
            return []

        sections: list[tuple[str, str]] = []

        # Content before first lab section
        preamble = content[: matches[0].start()].strip()
        if preamble:
            sections.append(("header", preamble))

        for i, match in enumerate(matches):
            section_name = match.group(1).strip().lower().replace(" ", "_")
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end].strip()
            if section_content:
                sections.append((section_name, section_content))

        return sections

    def _split_by_recommendations(
        self, content: str
    ) -> list[tuple[str, str]]:
        """Split clinical guideline by recommendation markers.

        Looks for patterns like "Recommendation 1:", "Grade A:", or
        numbered recommendation lists.

        Args:
            content: Full guideline text.

        Returns:
            List of (recommendation_text, evidence_grade) tuples.
        """
        # Look for recommendation patterns
        rec_pattern = re.compile(
            r"(?:^|\n)\s*(?:recommendation|rec\.?)\s*(\d+)\s*[:.]?\s*"
            r"(?:\(?(grade\s*[A-D]|class\s*[I]+[aAbB]*|level\s*[A-C]|"
            r"strong|weak|moderate|conditional|high|low)\)?)?\s*",
            re.IGNORECASE,
        )

        # Also try numbered list pattern
        numbered_pattern = re.compile(
            r"(?:^|\n)\s*(\d+)\s*[.)]\s+",
            re.MULTILINE,
        )

        # Evidence grade extraction
        grade_pattern = re.compile(
            r"(?:grade|class|level|strength|evidence)\s*[:=]?\s*"
            r"([A-D]|[I]+[aAbB]*|strong|weak|moderate|conditional|high|low)",
            re.IGNORECASE,
        )

        matches = list(rec_pattern.finditer(content))

        if matches:
            recommendations: list[tuple[str, str]] = []
            for i, match in enumerate(matches):
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                rec_text = content[start:end].strip()

                # Extract evidence grade from the match or the text
                grade = match.group(2) if match.group(2) else ""
                if not grade:
                    grade_match = grade_pattern.search(rec_text)
                    grade = grade_match.group(1) if grade_match else "ungraded"

                if rec_text:
                    recommendations.append((rec_text, grade.strip().lower()))

            return recommendations

        # Try numbered list pattern as fallback
        numbered_matches = list(numbered_pattern.finditer(content))
        if len(numbered_matches) >= 3:
            recommendations = []
            for i, match in enumerate(numbered_matches):
                start = match.end()
                end = (
                    numbered_matches[i + 1].start()
                    if i + 1 < len(numbered_matches)
                    else len(content)
                )
                rec_text = content[start:end].strip()

                grade_match = grade_pattern.search(rec_text)
                grade = grade_match.group(1) if grade_match else "ungraded"

                if rec_text:
                    recommendations.append((rec_text, grade.strip().lower()))

            return recommendations

        return []

    def _split_radiology_heuristic(
        self, content: str
    ) -> tuple[str, str]:
        """Heuristically split radiology report into findings and impression.

        Looks for common separators when section headers are not present.

        Args:
            content: Full radiology report text.

        Returns:
            Tuple of (findings_text, impression_text). Either may be empty.
        """
        # Try common impression markers
        impression_markers = [
            "\nimpression:",
            "\nimpression\n",
            "\nIMPRESSION:",
            "\nIMPRESSION\n",
            "\nconclusion:",
            "\nCONCLUSION:",
        ]

        for marker in impression_markers:
            idx = content.lower().find(marker.lower())
            if idx >= 0:
                findings = content[:idx].strip()
                impression = content[idx + len(marker) :].strip()
                return findings, impression

        # If no clear separation, treat everything as findings
        return content.strip(), ""

    def _extract_medical_codes(self, text: str) -> list[str]:
        """Extract medical codes (ICD-10, CPT, LOINC) from text.

        Args:
            text: Text to scan for medical codes.

        Returns:
            Deduplicated list of extracted codes.
        """
        codes: set[str] = set()

        # ICD-10 codes (letter followed by digits, optionally with decimal)
        for match in self._ICD10_PATTERN.finditer(text):
            code = match.group(1)
            # Filter out common false positives (single letter + 2 digits
            # that look like ICD-10 but are not)
            if len(code) >= 3:
                codes.add(f"ICD10:{code}")

        # LOINC codes (digits-digit pattern)
        for match in self._LOINC_PATTERN.finditer(text):
            codes.add(f"LOINC:{match.group(1)}")

        return sorted(codes)

    def _extract_first_date(self, text: str) -> str | None:
        """Extract the first date found in the text.

        Args:
            text: Text to scan for dates.

        Returns:
            First date string found, or None.
        """
        match = self._DATE_PATTERN.search(text)
        if match:
            date_str = match.group(1)
            # Try to normalize to ISO format
            try:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                    try:
                        parsed = datetime.strptime(date_str, fmt)
                        return parsed.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
            except Exception:
                pass
            return date_str
        return None

    def _fallback_chunking(
        self,
        content: str,
        document_id: str,
        document_type: str,
        metadata: dict | None = None,
    ) -> list[DocumentChunk]:
        """Create chunks using simple token-based splitting as a fallback.

        Args:
            content: Full document text.
            document_id: Unique identifier for this document.
            document_type: Type of the document.
            metadata: Optional additional metadata.

        Returns:
            List of DocumentChunk instances.
        """
        metadata = metadata or {}
        token_chunks = self._split_by_tokens(
            content,
            max_tokens=self.default_chunk_size,
            overlap=self.default_overlap,
        )
        chunks: list[DocumentChunk] = []
        for idx, sub_content in enumerate(token_chunks):
            chunk = DocumentChunk(
                content=sub_content,
                chunk_id=self._generate_chunk_id(document_id, "fallback", idx),
                document_id=document_id,
                section_type=document_type,
                page_number=metadata.get("page_number"),
                patient_id=metadata.get("patient_id"),
                date=metadata.get("date"),
                medical_codes=self._extract_medical_codes(sub_content),
                confidence_score=0.7,
                metadata={
                    **metadata,
                    "document_type": document_type,
                    "chunk_index": idx,
                    "total_chunks": len(token_chunks),
                    "fallback": True,
                },
            )
            chunks.append(chunk)
        return chunks

    @staticmethod
    def _generate_chunk_id(
        document_id: str, section: str, index: int
    ) -> str:
        """Generate a deterministic chunk ID.

        Args:
            document_id: Source document identifier.
            section: Section name within the document.
            index: Chunk index within the section.

        Returns:
            Deterministic chunk ID string.
        """
        return f"{document_id}_{section}_{index}"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for a text string.

        Uses the approximation of 1 token per 4 characters, which is
        conservative for English medical text.

        Args:
            text: Text to estimate token count for.

        Returns:
            Estimated number of tokens.
        """
        return len(text) // CHARS_PER_TOKEN
