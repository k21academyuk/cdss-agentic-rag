"""
Service layer for document ingestion in the Clinical Decision Support System.

Provides a high-level interface for ingesting patient documents, treatment
protocols, and PubMed literature into the CDSS knowledge base.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from cdss.ingestion.pipeline import (
    DocumentIngestionPipeline,
    DocumentType,
    IngestionStatus,
)

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    """Service for managing document ingestion.

    Wraps the DocumentIngestionPipeline with additional validation,
    error handling, and response formatting for use by API endpoints.
    """

    ALLOWED_DOCUMENT_TYPES = {dt.value for dt in DocumentType}

    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
    MAX_PUBMED_BATCH_SIZE = 500

    def __init__(
        self,
        pipeline: DocumentIngestionPipeline | None = None,
        settings: Any | None = None,
    ):
        self.pipeline = pipeline or DocumentIngestionPipeline()
        self.settings = settings or {}

    def _validate_document_type(self, document_type: str) -> DocumentType:
        """Validate and return the DocumentType enum value."""
        if document_type not in self.ALLOWED_DOCUMENT_TYPES:
            raise ValueError(
                f"Invalid document_type '{document_type}'. "
                f"Allowed types: {sorted(self.ALLOWED_DOCUMENT_TYPES)}"
            )
        return DocumentType(document_type)

    def _validate_file_size(self, file_bytes: bytes) -> None:
        """Validate that the file does not exceed the maximum allowed size."""
        if len(file_bytes) > self.MAX_FILE_SIZE_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            max_mb = self.MAX_FILE_SIZE_BYTES / (1024 * 1024)
            raise ValueError(
                f"File size ({size_mb:.1f} MB) exceeds maximum allowed size "
                f"({max_mb:.0f} MB)."
            )

    def _validate_file_content(self, file_bytes: bytes) -> None:
        """Basic validation that the file content is not empty."""
        if not file_bytes or len(file_bytes) == 0:
            raise ValueError("File content is empty.")

    async def ingest_patient_document(
        self,
        file_bytes: bytes,
        document_type: str,
        patient_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Ingest a patient document and return status.

        Args:
            file_bytes: Raw bytes of the document (PDF, image, etc.)
            document_type: Type of clinical document (e.g., 'lab_report', 'prescription')
            patient_id: Optional patient identifier for linking the document
            metadata: Optional additional metadata to store with the document

        Returns:
            dict with document_id, status, and message

        Raises:
            ValueError: If document_type is invalid or file validation fails
        """
        # Validate inputs
        doc_type = self._validate_document_type(document_type)
        self._validate_file_content(file_bytes)
        self._validate_file_size(file_bytes)

        logger.info(
            "Starting patient document ingestion: type=%s, patient_id=%s, size=%d bytes",
            doc_type.value,
            patient_id,
            len(file_bytes),
        )

        effective_metadata = metadata or {}
        effective_metadata["source"] = "patient_document_upload"
        effective_metadata["upload_timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            document_id = await self.pipeline.ingest_document(
                document_bytes=file_bytes,
                document_type=doc_type.value,
                patient_id=patient_id,
                metadata=effective_metadata,
            )

            status = self.pipeline.get_ingestion_status(document_id)

            return {
                "document_id": document_id,
                "status": status.get("status", IngestionStatus.COMPLETED.value),
                "message": f"Document ingestion completed successfully. "
                f"Type: {doc_type.value}.",
                "patient_id": patient_id,
                "document_type": doc_type.value,
                "details": status.get("details"),
                "steps_completed": status.get("steps_completed", []),
                "created_at": status.get("created_at"),
                "completed_at": status.get("updated_at"),
            }

        except Exception as exc:
            logger.exception(
                "Patient document ingestion failed: type=%s, patient_id=%s",
                document_type,
                patient_id,
            )
            return {
                "document_id": None,
                "status": IngestionStatus.FAILED.value,
                "message": f"Document ingestion failed: {str(exc)}",
                "patient_id": patient_id,
                "document_type": document_type,
                "error": str(exc),
            }

    async def ingest_protocol(
        self,
        file_bytes: bytes,
        specialty: str,
        guideline_name: str,
        version: str,
        metadata: dict | None = None,
    ) -> dict:
        """Ingest a treatment protocol.

        Args:
            file_bytes: Raw bytes of the protocol PDF
            specialty: Medical specialty (e.g., 'cardiology', 'oncology')
            guideline_name: Name of the guideline (e.g., 'ACS Management Protocol')
            version: Version string (e.g., '2024.1')
            metadata: Optional additional metadata

        Returns:
            dict with document_id, status, and message
        """
        # Validate inputs
        self._validate_file_content(file_bytes)
        self._validate_file_size(file_bytes)

        if not specialty or not specialty.strip():
            raise ValueError("Specialty must not be empty.")
        if not guideline_name or not guideline_name.strip():
            raise ValueError("Guideline name must not be empty.")
        if not version or not version.strip():
            raise ValueError("Version must not be empty.")

        specialty = specialty.strip().lower()
        guideline_name = guideline_name.strip()
        version = version.strip()

        logger.info(
            "Starting protocol ingestion: specialty=%s, guideline=%s, version=%s, size=%d bytes",
            specialty,
            guideline_name,
            version,
            len(file_bytes),
        )

        effective_metadata = metadata or {}
        effective_metadata["source"] = "protocol_upload"
        effective_metadata["upload_timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            document_id = await self.pipeline.ingest_treatment_protocol(
                pdf_bytes=file_bytes,
                specialty=specialty,
                guideline_name=guideline_name,
                version=version,
                metadata=effective_metadata,
            )

            status = self.pipeline.get_ingestion_status(document_id)

            return {
                "document_id": document_id,
                "status": status.get("status", IngestionStatus.COMPLETED.value),
                "message": f"Protocol ingestion completed: {guideline_name} v{version} ({specialty}).",
                "specialty": specialty,
                "guideline_name": guideline_name,
                "version": version,
                "details": status.get("details"),
                "steps_completed": status.get("steps_completed", []),
                "created_at": status.get("created_at"),
                "completed_at": status.get("updated_at"),
            }

        except Exception as exc:
            logger.exception(
                "Protocol ingestion failed: specialty=%s, guideline=%s",
                specialty,
                guideline_name,
            )
            return {
                "document_id": None,
                "status": IngestionStatus.FAILED.value,
                "message": f"Protocol ingestion failed: {str(exc)}",
                "specialty": specialty,
                "guideline_name": guideline_name,
                "version": version,
                "error": str(exc),
            }

    async def batch_ingest_literature(
        self,
        query: str,
        max_articles: int = 100,
        articles: list[dict] | None = None,
    ) -> dict:
        """Fetch and ingest PubMed articles for a clinical topic.

        If articles are not provided directly, this method simulates fetching
        from PubMed using the Entrez API. In production, integrate with
        Bio.Entrez or the PubMed E-utilities API.

        Args:
            query: PubMed search query string (e.g., 'acute coronary syndrome treatment')
            max_articles: Maximum number of articles to fetch and ingest
            articles: Optional pre-fetched list of article dicts to ingest directly

        Returns:
            dict with batch statistics including document IDs and status
        """
        if not query or not query.strip():
            raise ValueError("Search query must not be empty.")

        max_articles = min(max_articles, self.MAX_PUBMED_BATCH_SIZE)

        logger.info(
            "Starting batch literature ingestion: query='%s', max_articles=%d",
            query,
            max_articles,
        )

        if articles is None:
            # Simulate PubMed article retrieval
            # In production, use Bio.Entrez or PubMed E-utilities API
            articles = self._simulate_pubmed_fetch(query, max_articles)

        if not articles:
            return {
                "status": "no_results",
                "message": f"No articles found for query: '{query}'",
                "query": query,
                "articles_found": 0,
                "document_ids": [],
            }

        # Limit to max_articles
        articles = articles[:max_articles]

        try:
            document_ids = await self.pipeline.ingest_pubmed_articles(articles)

            # Gather statuses
            succeeded = 0
            failed = 0
            for doc_id in document_ids:
                status = self.pipeline.get_ingestion_status(doc_id)
                if status.get("status") == IngestionStatus.COMPLETED.value:
                    succeeded += 1
                elif status.get("status") == IngestionStatus.FAILED.value:
                    failed += 1

            return {
                "status": "completed",
                "message": (
                    f"Batch literature ingestion completed. "
                    f"{succeeded} succeeded, {failed} failed out of {len(articles)} articles."
                ),
                "query": query,
                "articles_found": len(articles),
                "articles_ingested": succeeded,
                "articles_failed": failed,
                "document_ids": document_ids,
            }

        except Exception as exc:
            logger.exception("Batch literature ingestion failed for query: '%s'", query)
            return {
                "status": IngestionStatus.FAILED.value,
                "message": f"Batch literature ingestion failed: {str(exc)}",
                "query": query,
                "articles_found": len(articles),
                "error": str(exc),
                "document_ids": [],
            }

    def _simulate_pubmed_fetch(self, query: str, max_articles: int) -> list[dict]:
        """Simulate fetching articles from PubMed for development/testing.

        In production, replace with actual PubMed E-utilities API calls:
            1. ESearch to get PMIDs matching the query
            2. EFetch to retrieve article details
            3. Parse XML response into article dicts
        """
        logger.info(
            "Simulating PubMed fetch: query='%s', max_articles=%d",
            query,
            max_articles,
        )

        simulated_articles = [
            {
                "pmid": f"SIM{i:08d}",
                "title": f"Simulated Article {i}: {query}",
                "abstract": (
                    f"This is a simulated abstract for article {i} related to '{query}'. "
                    f"In a production environment, this would contain the actual abstract "
                    f"text retrieved from PubMed via the E-utilities API. The abstract "
                    f"would discuss clinical findings, methodology, and conclusions "
                    f"relevant to the search query."
                ),
                "authors": [
                    f"Author A{i}",
                    f"Author B{i}",
                    f"Author C{i}",
                ],
                "journal": f"Journal of Clinical Medicine (Simulated)",
                "publication_date": "2024-01-15",
                "mesh_terms": [
                    "Clinical Trial",
                    "Evidence-Based Medicine",
                    query.split()[0] if query.split() else "Medicine",
                ],
                "doi": f"10.1234/sim.{i:08d}",
            }
            for i in range(min(max_articles, 5))
        ]

        logger.info(
            "Simulated PubMed fetch returned %d articles", len(simulated_articles)
        )

        return simulated_articles

    def get_status(self, document_id: str) -> dict:
        """Get ingestion status for a document.

        Args:
            document_id: The unique identifier returned by an ingestion method

        Returns:
            dict with document_id, status, details, error, steps_completed, timestamps
        """
        if not document_id or not document_id.strip():
            return {
                "document_id": None,
                "status": "error",
                "message": "document_id must not be empty.",
            }

        status = self.pipeline.get_ingestion_status(document_id)

        if status.get("status") == "not_found":
            return {
                "document_id": document_id,
                "status": "not_found",
                "message": f"No ingestion record found for document_id '{document_id}'.",
            }

        return {
            "document_id": document_id,
            "status": status.get("status"),
            "details": status.get("details"),
            "error": status.get("error"),
            "steps_completed": status.get("steps_completed", []),
            "created_at": status.get("created_at"),
            "updated_at": status.get("updated_at"),
        }

    async def get_supported_document_types(self) -> list[dict]:
        """Return the list of supported document types with descriptions."""
        type_descriptions = {
            DocumentType.LAB_REPORT: "Laboratory test results (CBC, CMP, etc.)",
            DocumentType.PRESCRIPTION: "Medication prescriptions and orders",
            DocumentType.DISCHARGE_SUMMARY: "Hospital discharge summaries",
            DocumentType.RADIOLOGY_REPORT: "Radiology and imaging reports (X-ray, CT, MRI)",
            DocumentType.CLINICAL_GUIDELINE: "Clinical practice guidelines and protocols",
            DocumentType.PUBMED_ABSTRACT: "PubMed research article abstracts",
            DocumentType.GENERIC: "Generic clinical documents",
        }

        return [
            {
                "type": dt.value,
                "description": type_descriptions.get(dt, ""),
            }
            for dt in DocumentType
        ]
