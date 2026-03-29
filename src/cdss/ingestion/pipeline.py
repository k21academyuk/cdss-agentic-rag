"""
Document Ingestion Pipeline for Clinical Decision Support System.

Pipeline flow:
    Source PDF -> Blob Storage -> Document Intelligence (OCR + Layout)
    -> Text Analytics for Health (NER) -> Chunking -> Embedding -> AI Search Index

Also stores embeddings in Cosmos DB for vector search.
"""

import asyncio
import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Supported document types for clinical ingestion."""

    LAB_REPORT = "lab_report"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    RADIOLOGY_REPORT = "radiology_report"
    CLINICAL_GUIDELINE = "clinical_guideline"
    PUBMED_ABSTRACT = "pubmed_abstract"
    GENERIC = "generic"


class IngestionStatus(str, Enum):
    """Status of a document through the ingestion pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


# Chunk size configuration per document type
CHUNK_CONFIG = {
    DocumentType.LAB_REPORT: {"max_tokens": 512, "overlap_tokens": 64},
    DocumentType.PRESCRIPTION: {"max_tokens": 256, "overlap_tokens": 32},
    DocumentType.DISCHARGE_SUMMARY: {"max_tokens": 1024, "overlap_tokens": 128},
    DocumentType.RADIOLOGY_REPORT: {"max_tokens": 512, "overlap_tokens": 64},
    DocumentType.CLINICAL_GUIDELINE: {"max_tokens": 1024, "overlap_tokens": 128},
    DocumentType.PUBMED_ABSTRACT: {"max_tokens": 512, "overlap_tokens": 64},
    DocumentType.GENERIC: {"max_tokens": 768, "overlap_tokens": 96},
}

# Medical entity patterns for simulated NER
MEDICAL_ENTITY_PATTERNS = {
    "diseases": [
        (r"\b(diabetes mellitus(?:\s+type\s+[12])?)\b", "ICD-10:E11"),
        (r"\b(hypertension|high blood pressure)\b", "ICD-10:I10"),
        (r"\b(acute myocardial infarction|heart attack|AMI)\b", "ICD-10:I21"),
        (r"\b(chronic kidney disease|CKD)\b", "ICD-10:N18"),
        (r"\b(pneumonia)\b", "ICD-10:J18"),
        (r"\b(atrial fibrillation|AFib)\b", "ICD-10:I48"),
        (r"\b(congestive heart failure|CHF)\b", "ICD-10:I50"),
        (r"\b(chronic obstructive pulmonary disease|COPD)\b", "ICD-10:J44"),
        (r"\b(asthma)\b", "ICD-10:J45"),
        (r"\b(stroke|cerebrovascular accident|CVA)\b", "ICD-10:I63"),
        (r"\b(sepsis)\b", "ICD-10:A41"),
        (r"\b(pulmonary embolism|PE)\b", "ICD-10:I26"),
        (r"\b(deep vein thrombosis|DVT)\b", "ICD-10:I82"),
        (r"\b(anemia)\b", "ICD-10:D64"),
        (r"\b(hypothyroidism)\b", "ICD-10:E03"),
        (r"\b(hyperthyroidism)\b", "ICD-10:E05"),
        (r"\b(cirrhosis)\b", "ICD-10:K74"),
        (r"\b(pancreatitis)\b", "ICD-10:K85"),
        (r"\b(epilepsy)\b", "ICD-10:G40"),
        (r"\b(Parkinson(?:'s)?\s+disease)\b", "ICD-10:G20"),
        (r"\b(Alzheimer(?:'s)?\s+disease)\b", "ICD-10:G30"),
    ],
    "medications": [
        (r"\b(metformin)\b", "RxNorm:6809"),
        (r"\b(lisinopril)\b", "RxNorm:29046"),
        (r"\b(atorvastatin)\b", "RxNorm:83367"),
        (r"\b(amlodipine)\b", "RxNorm:17767"),
        (r"\b(metoprolol)\b", "RxNorm:6918"),
        (r"\b(omeprazole)\b", "RxNorm:7646"),
        (r"\b(levothyroxine)\b", "RxNorm:10582"),
        (r"\b(warfarin)\b", "RxNorm:11289"),
        (r"\b(heparin)\b", "RxNorm:5224"),
        (r"\b(insulin)\b", "RxNorm:5856"),
        (r"\b(aspirin)\b", "RxNorm:1191"),
        (r"\b(clopidogrel)\b", "RxNorm:32968"),
        (r"\b(amoxicillin)\b", "RxNorm:723"),
        (r"\b(ciprofloxacin)\b", "RxNorm:2551"),
        (r"\b(prednisone)\b", "RxNorm:8640"),
        (r"\b(furosemide)\b", "RxNorm:4603"),
        (r"\b(hydrochlorothiazide|HCTZ)\b", "RxNorm:5487"),
        (r"\b(gabapentin)\b", "RxNorm:25480"),
        (r"\b(sertraline)\b", "RxNorm:36437"),
        (r"\b(fluoxetine)\b", "RxNorm:4493"),
    ],
    "procedures": [
        (r"\b(complete blood count|CBC)\b", "CPT:85025"),
        (r"\b(basic metabolic panel|BMP)\b", "CPT:80048"),
        (r"\b(comprehensive metabolic panel|CMP)\b", "CPT:80053"),
        (r"\b(lipid panel)\b", "CPT:80061"),
        (r"\b(chest x-?ray|CXR)\b", "CPT:71046"),
        (r"\b(CT scan|computed tomography)\b", "CPT:70553"),
        (r"\b(MRI|magnetic resonance imaging)\b", "CPT:70553"),
        (r"\b(echocardiogram|echo)\b", "CPT:93306"),
        (r"\b(electrocardiogram|ECG|EKG)\b", "CPT:93000"),
        (r"\b(coronary angiography)\b", "CPT:93454"),
        (r"\b(colonoscopy)\b", "CPT:45378"),
        (r"\b(endoscopy)\b", "CPT:43239"),
        (r"\b(biopsy)\b", "CPT:88305"),
        (r"\b(urinalysis)\b", "CPT:81001"),
        (r"\b(hemoglobin A1c|HbA1c)\b", "CPT:83036"),
    ],
    "lab_tests": [
        (r"\b(hemoglobin|Hgb|Hb)\b", "LOINC:718-7"),
        (r"\b(hematocrit|Hct)\b", "LOINC:4544-3"),
        (r"\b(white blood cell|WBC)\b", "LOINC:6690-2"),
        (r"\b(platelet count)\b", "LOINC:777-3"),
        (r"\b(creatinine)\b", "LOINC:2160-0"),
        (r"\b(blood urea nitrogen|BUN)\b", "LOINC:3094-0"),
        (r"\b(glucose)\b", "LOINC:2345-7"),
        (r"\b(sodium|Na\+?)\b", "LOINC:2951-2"),
        (r"\b(potassium|K\+?)\b", "LOINC:2823-3"),
        (r"\b(troponin)\b", "LOINC:6598-7"),
        (r"\b(prothrombin time|PT)\b", "LOINC:5902-2"),
        (r"\b(INR)\b", "LOINC:6301-6"),
        (r"\b(ALT|alanine aminotransferase)\b", "LOINC:1742-6"),
        (r"\b(AST|aspartate aminotransferase)\b", "LOINC:1920-8"),
        (r"\b(bilirubin)\b", "LOINC:1975-2"),
        (r"\b(albumin)\b", "LOINC:1751-7"),
        (r"\b(TSH|thyroid stimulating hormone)\b", "LOINC:3016-3"),
        (r"\b(C-reactive protein|CRP)\b", "LOINC:1988-5"),
        (r"\b(D-dimer)\b", "LOINC:48065-7"),
        (r"\b(BNP|brain natriuretic peptide)\b", "LOINC:30934-4"),
    ],
    "anatomical_sites": [
        (r"\b(heart|cardiac)\b", "SNOMED-CT:80891009"),
        (r"\b(lung|pulmonary)\b", "SNOMED-CT:39607008"),
        (r"\b(liver|hepatic)\b", "SNOMED-CT:10200004"),
        (r"\b(kidney|renal)\b", "SNOMED-CT:64033007"),
        (r"\b(brain|cerebral)\b", "SNOMED-CT:12738006"),
        (r"\b(pancreas|pancreatic)\b", "SNOMED-CT:15776009"),
        (r"\b(thyroid)\b", "SNOMED-CT:69748006"),
        (r"\b(stomach|gastric)\b", "SNOMED-CT:69695003"),
        (r"\b(colon|colonic)\b", "SNOMED-CT:71854001"),
        (r"\b(bone marrow)\b", "SNOMED-CT:14016003"),
    ],
    "dosages": [
        (r"\b(\d+\s*(?:mg|mcg|g|mL|units?|IU)(?:\s*/\s*(?:day|hr|min|dose|kg))?)\b", None),
        (r"\b(\d+\s*(?:mg|mcg|g)\s+(?:once|twice|three times|four times)\s+(?:daily|weekly))\b", None),
        (r"\b((?:once|twice|three times)\s+(?:daily|weekly|monthly))\b", None),
        (r"\b(q\d+h|bid|tid|qid|prn|qd|qhs|qam|qpm)\b", None),
    ],
    "temporal_expressions": [
        (r"\b(\d+\s*(?:days?|weeks?|months?|years?)\s+ago)\b", None),
        (r"\b(since\s+\d{4})\b", None),
        (r"\b(for\s+\d+\s+(?:days?|weeks?|months?|years?))\b", None),
        (r"\b((?:post|pre)-?operative\s+day\s+\d+)\b", None),
        (r"\b(day\s+\d+\s+of\s+treatment)\b", None),
        (r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", None),
    ],
}


class DocumentIngestionPipeline:
    """Full document ingestion pipeline.

    Source PDF -> Blob Storage -> Document Intelligence (OCR + Layout)
    -> Text Analytics for Health (NER) -> Chunking -> Embedding -> AI Search Index

    Also stores embeddings in Cosmos DB for vector search.
    """

    def __init__(
        self,
        doc_intelligence_client: Any | None = None,
        blob_client: Any | None = None,
        search_client: Any | None = None,
        cosmos_client: Any | None = None,
        embedding_service: Any | None = None,
        chunker: Any | None = None,
        settings: Any | None = None,
    ):
        self.doc_intelligence_client = doc_intelligence_client
        self.blob_client = blob_client
        self.search_client = search_client
        self.cosmos_client = cosmos_client
        self.embedding_service = embedding_service
        self.chunker = chunker
        self.settings = settings or {}

        self._status_store: dict[str, dict] = {}

        self._default_search_index = self.settings.get(
            "search_index", "patient-records"
        )
        self._protocols_index = self.settings.get(
            "protocols_index", "treatment-protocols"
        )
        self._literature_index = self.settings.get(
            "literature_index", "medical-literature-cache"
        )
        self._blob_container = self.settings.get("blob_container", "staging-documents")
        self._cosmos_database = self.settings.get("cosmos_database", "cdss-db")
        self._cosmos_embeddings_container = self.settings.get(
            "cosmos_embeddings_container", "embedding-cache"
        )
        self._embedding_model = self.settings.get(
            "embedding_model", "text-embedding-3-large"
        )
        self._embedding_dimensions = self.settings.get("embedding_dimensions", 3072)

    def _update_status(
        self,
        document_id: str,
        status: IngestionStatus,
        details: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update ingestion status for a document."""
        now = datetime.now(timezone.utc).isoformat()
        if document_id not in self._status_store:
            self._status_store[document_id] = {
                "document_id": document_id,
                "status": status.value,
                "created_at": now,
                "updated_at": now,
                "details": details,
                "error": None,
                "steps_completed": [],
            }
        else:
            self._status_store[document_id]["status"] = status.value
            self._status_store[document_id]["updated_at"] = now
            if details:
                self._status_store[document_id]["details"] = details
            if error:
                self._status_store[document_id]["error"] = error

        if status not in (IngestionStatus.FAILED, IngestionStatus.PENDING):
            self._status_store[document_id]["steps_completed"].append(
                {"step": status.value, "timestamp": now}
            )

        logger.info(
            "Document %s status: %s - %s", document_id, status.value, details or ""
        )

    def _resolve_index_for_document_type(self, document_type: str) -> str:
        """Resolve the target Azure Search index for a document type."""
        if document_type == DocumentType.CLINICAL_GUIDELINE.value:
            return self._protocols_index
        if document_type == DocumentType.PUBMED_ABSTRACT.value:
            return self._literature_index
        return self._default_search_index

    async def ingest_document(
        self,
        document_bytes: bytes,
        document_type: str,
        patient_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Ingest a document through the full pipeline. Returns document_id.

        Pipeline steps:
        1. Upload to Blob Storage (staging)
        2. Analyze with Document Intelligence (layout + OCR)
        3. Extract medical entities (simulated Text Analytics for Health NER)
        4. Chunk using domain-aware rules
        5. Generate embeddings for each chunk
        6. Index chunks in AI Search
        7. Store embeddings in Cosmos DB
        """
        document_id = str(uuid4())
        doc_type_enum = DocumentType(document_type)
        effective_metadata = metadata or {}
        effective_metadata.update(
            {
                "document_id": document_id,
                "document_type": doc_type_enum.value,
                "patient_id": patient_id,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": hashlib.sha256(document_bytes).hexdigest(),
                "size_bytes": len(document_bytes),
            }
        )

        self._update_status(document_id, IngestionStatus.PENDING, "Ingestion queued")

        try:
            # Step 1: Upload to Blob Storage
            self._update_status(
                document_id,
                IngestionStatus.PROCESSING,
                "Uploading to Blob Storage",
            )
            blob_url = await self._upload_to_blob(
                document_id, document_bytes, effective_metadata
            )
            effective_metadata["blob_url"] = blob_url

            # Step 2: Analyze with Document Intelligence
            self._update_status(
                document_id,
                IngestionStatus.PROCESSING,
                "Analyzing with Document Intelligence",
            )
            analysis_result = await self._analyze_document(document_bytes)
            extracted_text = analysis_result.get("content", "")
            tables = analysis_result.get("tables", [])
            key_value_pairs = analysis_result.get("key_value_pairs", [])

            effective_metadata["page_count"] = analysis_result.get("page_count", 0)
            effective_metadata["has_tables"] = len(tables) > 0
            effective_metadata["has_key_value_pairs"] = len(key_value_pairs) > 0

            # Step 3: Extract medical entities
            self._update_status(
                document_id,
                IngestionStatus.PROCESSING,
                "Extracting medical entities",
            )
            entities = self._extract_medical_entities(extracted_text)
            effective_metadata["entities"] = entities
            effective_metadata["entity_count"] = len(entities)

            # Build enriched text with entity annotations
            enriched_text = self._build_enriched_text(
                extracted_text, entities, tables, key_value_pairs
            )

            # Step 4-5: Chunk and embed
            self._update_status(
                document_id, IngestionStatus.CHUNKING, "Chunking document"
            )
            chunks = await self._chunk_and_embed(
                enriched_text, doc_type_enum.value, document_id, effective_metadata
            )

            # Step 6: Index in AI Search
            self._update_status(
                document_id,
                IngestionStatus.INDEXING,
                f"Indexing {len(chunks)} chunks in AI Search",
            )
            target_index = self._resolve_index_for_document_type(doc_type_enum.value)
            index_result = await self._index_chunks(chunks, target_index)

            # Step 7: Store embeddings in Cosmos DB
            self._update_status(
                document_id,
                IngestionStatus.INDEXING,
                "Storing embeddings in Cosmos DB",
            )
            await self._store_embeddings(chunks, patient_id)

            # Mark as completed
            self._update_status(
                document_id,
                IngestionStatus.COMPLETED,
                f"Successfully ingested {len(chunks)} chunks. "
                f"Index result: {index_result.get('succeeded', 0)} succeeded, "
                f"{index_result.get('failed', 0)} failed.",
            )

            return document_id

        except Exception as exc:
            logger.exception("Ingestion failed for document %s", document_id)
            self._update_status(
                document_id,
                IngestionStatus.FAILED,
                "Ingestion pipeline failed",
                error=str(exc),
            )
            raise

    async def ingest_treatment_protocol(
        self,
        pdf_bytes: bytes,
        specialty: str,
        guideline_name: str,
        version: str,
        metadata: dict | None = None,
    ) -> str:
        """Specialized ingestion for treatment protocols into the protocols index.

        Treatment protocols are chunked with larger overlap to preserve
        decision trees and clinical pathways context.
        """
        document_id = str(uuid4())
        effective_metadata = metadata or {}
        effective_metadata.update(
            {
                "document_id": document_id,
                "document_type": DocumentType.CLINICAL_GUIDELINE.value,
                "specialty": specialty,
                "guideline_name": guideline_name,
                "version": version,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": hashlib.sha256(pdf_bytes).hexdigest(),
                "size_bytes": len(pdf_bytes),
                "is_protocol": True,
            }
        )

        self._update_status(
            document_id, IngestionStatus.PENDING, "Protocol ingestion queued"
        )

        try:
            # Step 1: Upload to Blob Storage (protocols container)
            self._update_status(
                document_id,
                IngestionStatus.PROCESSING,
                "Uploading protocol to Blob Storage",
            )
            blob_url = await self._upload_to_blob(
                document_id,
                pdf_bytes,
                effective_metadata,
            )
            effective_metadata["blob_url"] = blob_url

            # Step 2: Analyze with Document Intelligence
            self._update_status(
                document_id,
                IngestionStatus.PROCESSING,
                "Analyzing protocol with Document Intelligence",
            )
            analysis_result = await self._analyze_document(pdf_bytes)
            extracted_text = analysis_result.get("content", "")
            tables = analysis_result.get("tables", [])
            key_value_pairs = analysis_result.get("key_value_pairs", [])

            # Step 3: Extract medical entities
            entities = self._extract_medical_entities(extracted_text)
            effective_metadata["entities"] = entities

            enriched_text = self._build_enriched_text(
                extracted_text, entities, tables, key_value_pairs
            )

            # Steps 4-5: Chunk with larger overlap for protocols
            self._update_status(
                document_id, IngestionStatus.CHUNKING, "Chunking protocol"
            )
            chunks = await self._chunk_and_embed(
                enriched_text,
                DocumentType.CLINICAL_GUIDELINE.value,
                document_id,
                effective_metadata,
            )

            # Add protocol-specific fields to each chunk
            for chunk in chunks:
                chunk["specialty"] = specialty
                chunk["guideline_name"] = guideline_name
                chunk["version"] = version
                chunk["is_protocol"] = True

            # Step 6: Index in protocols index
            self._update_status(
                document_id,
                IngestionStatus.INDEXING,
                f"Indexing {len(chunks)} protocol chunks",
            )
            index_result = await self._index_chunks(chunks, self._protocols_index)

            # Step 7: Store embeddings
            await self._store_embeddings(chunks, patient_id=None)

            self._update_status(
                document_id,
                IngestionStatus.COMPLETED,
                f"Protocol ingested: {len(chunks)} chunks. "
                f"{index_result.get('succeeded', 0)} indexed.",
            )

            return document_id

        except Exception as exc:
            logger.exception("Protocol ingestion failed for %s", document_id)
            self._update_status(
                document_id,
                IngestionStatus.FAILED,
                "Protocol ingestion failed",
                error=str(exc),
            )
            raise

    async def ingest_pubmed_articles(self, articles: list[dict]) -> list[str]:
        """Batch ingest PubMed articles into the literature cache index.

        Each article dict should have:
            - pmid: PubMed ID
            - title: Article title
            - abstract: Article abstract text
            - authors: List of author names
            - journal: Journal name
            - publication_date: Publication date string
            - mesh_terms: List of MeSH terms
            - doi: Digital Object Identifier (optional)
        """
        document_ids: list[str] = []
        batch_id = str(uuid4())

        logger.info(
            "Starting batch PubMed ingestion: %d articles, batch_id=%s",
            len(articles),
            batch_id,
        )

        all_chunks: list[dict] = []

        for article in articles:
            document_id = str(uuid4())
            document_ids.append(document_id)

            pmid = article.get("pmid", "unknown")
            title = article.get("title", "")
            abstract_text = article.get("abstract", "")
            authors = article.get("authors", [])
            journal = article.get("journal", "")
            publication_date = article.get("publication_date", "")
            mesh_terms = article.get("mesh_terms", [])
            doi = article.get("doi", "")

            self._update_status(
                document_id,
                IngestionStatus.PENDING,
                f"PubMed article {pmid} queued",
            )

            try:
                # Build combined text for embedding
                combined_text = (
                    f"Title: {title}\n\n"
                    f"Authors: {', '.join(authors)}\n"
                    f"Journal: {journal}\n"
                    f"Published: {publication_date}\n"
                    f"PMID: {pmid}\n"
                    f"DOI: {doi}\n\n"
                    f"Abstract:\n{abstract_text}\n\n"
                    f"MeSH Terms: {', '.join(mesh_terms)}"
                )

                # Extract entities from abstract
                entities = self._extract_medical_entities(abstract_text)

                article_metadata = {
                    "document_id": document_id,
                    "document_type": DocumentType.PUBMED_ABSTRACT.value,
                    "pmid": pmid,
                    "title": title,
                    "authors": authors,
                    "journal": journal,
                    "publication_date": publication_date,
                    "mesh_terms": mesh_terms,
                    "doi": doi,
                    "entities": entities,
                    "batch_id": batch_id,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "content_hash": hashlib.sha256(
                        combined_text.encode("utf-8")
                    ).hexdigest(),
                }

                # Chunk and embed
                self._update_status(
                    document_id,
                    IngestionStatus.EMBEDDING,
                    f"Embedding PubMed article {pmid}",
                )
                chunks = await self._chunk_and_embed(
                    combined_text,
                    DocumentType.PUBMED_ABSTRACT.value,
                    document_id,
                    article_metadata,
                )

                # Add PubMed-specific fields
                for chunk in chunks:
                    chunk["pmid"] = pmid
                    chunk["title"] = title
                    chunk["journal"] = journal
                    chunk["publication_date"] = publication_date
                    chunk["mesh_terms"] = mesh_terms

                all_chunks.extend(chunks)

                self._update_status(
                    document_id,
                    IngestionStatus.COMPLETED,
                    f"PubMed article {pmid} processed: {len(chunks)} chunks",
                )

            except Exception as exc:
                logger.exception("Failed to process PubMed article %s", pmid)
                self._update_status(
                    document_id,
                    IngestionStatus.FAILED,
                    f"Failed to process PubMed article {pmid}",
                    error=str(exc),
                )

        # Batch index all chunks
        if all_chunks:
            try:
                logger.info(
                    "Batch indexing %d chunks from %d articles",
                    len(all_chunks),
                    len(articles),
                )
                index_result = await self._index_chunks(
                    all_chunks, self._literature_index
                )
                logger.info(
                    "Batch index result: %d succeeded, %d failed",
                    index_result.get("succeeded", 0),
                    index_result.get("failed", 0),
                )
            except Exception as exc:
                logger.exception("Batch indexing failed for PubMed articles")
                for doc_id in document_ids:
                    if (
                        self._status_store.get(doc_id, {}).get("status")
                        != IngestionStatus.FAILED.value
                    ):
                        self._update_status(
                            doc_id,
                            IngestionStatus.FAILED,
                            "Batch indexing failed",
                            error=str(exc),
                        )

        return document_ids

    def get_ingestion_status(self, document_id: str) -> dict:
        """Get current ingestion status for a document.

        Returns:
            dict with keys: document_id, status, created_at, updated_at,
            details, error, steps_completed
        """
        if document_id not in self._status_store:
            return {
                "document_id": document_id,
                "status": "not_found",
                "error": f"No ingestion record found for document_id={document_id}",
            }
        return self._status_store[document_id].copy()

    async def _upload_to_blob(
        self, document_id: str, document_bytes: bytes, metadata: dict
    ) -> str:
        """Step 1: Upload raw document to Blob Storage staging container.

        Returns the blob URL for the uploaded document.
        """
        blob_name = (
            f"{metadata.get('document_type', 'generic')}/"
            f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
            f"{document_id}.pdf"
        )

        sanitized_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized_metadata[key] = str(value)
            elif isinstance(value, list):
                sanitized_metadata[key] = json.dumps(value)

        if self.blob_client is not None:
            try:
                if hasattr(self.blob_client, "upload_protocol"):
                    blob_url = await self.blob_client.upload_protocol(
                        blob_name=blob_name,
                        content=document_bytes,
                        metadata=sanitized_metadata,
                    )
                    logger.info(
                        "Uploaded document %s to blob via BlobStorageClient wrapper: %s",
                        document_id,
                        blob_url,
                    )
                    return blob_url

                container_client = self.blob_client.get_container_client(
                    self._blob_container
                )
                blob_client = container_client.get_blob_client(blob_name)
                await blob_client.upload_blob(
                    data=document_bytes,
                    metadata=sanitized_metadata,
                    overwrite=True,
                    content_settings={
                        "content_type": "application/pdf",
                    },
                )
                blob_url = blob_client.url
                logger.info("Uploaded document %s to blob: %s", document_id, blob_url)
                return blob_url
            except Exception as exc:
                logger.error(
                    "Blob upload failed for %s: %s", document_id, str(exc)
                )
                raise
        else:
            # Simulated upload for development/testing
            blob_url = (
                f"https://cdssstorage.blob.core.windows.net/"
                f"{self._blob_container}/{blob_name}"
            )
            logger.info(
                "Simulated blob upload for %s: %s", document_id, blob_url
            )
            return blob_url

    async def _analyze_document(self, document_bytes: bytes) -> dict:
        """Step 2: Analyze document with Azure Document Intelligence.

        Uses the prebuilt-layout model for OCR + layout analysis.
        Returns extracted text, tables, and key-value pairs.
        """
        if self.doc_intelligence_client is not None:
            try:
                if hasattr(self.doc_intelligence_client, "analyze_document"):
                    analysis_result = await self.doc_intelligence_client.analyze_document(
                        document_bytes=document_bytes,
                        model_id="prebuilt-layout",
                    )
                    return {
                        "content": analysis_result.get("content", ""),
                        "tables": analysis_result.get("tables", []),
                        "key_value_pairs": analysis_result.get("key_value_pairs", []),
                        "page_count": len(analysis_result.get("pages", [])),
                    }

                begin_call = None
                try:
                    begin_call = self.doc_intelligence_client.begin_analyze_document(
                        model_id="prebuilt-layout",
                        body=document_bytes,
                        content_type="application/pdf",
                    )
                except TypeError:
                    begin_call = self.doc_intelligence_client.begin_analyze_document(
                        model_id="prebuilt-layout",
                        document=io.BytesIO(document_bytes),
                        content_type="application/pdf",
                    )

                poller = await begin_call if asyncio.iscoroutine(begin_call) else begin_call
                result_call = poller.result()
                result = await result_call if asyncio.iscoroutine(result_call) else result_call

                content = result.content if result.content else ""

                tables = []
                if result.tables:
                    for table in result.tables:
                        table_data = {
                            "row_count": table.row_count,
                            "column_count": table.column_count,
                            "cells": [],
                        }
                        for cell in table.cells:
                            table_data["cells"].append(
                                {
                                    "row_index": cell.row_index,
                                    "column_index": cell.column_index,
                                    "content": cell.content,
                                    "kind": cell.kind if hasattr(cell, "kind") else "content",
                                }
                            )
                        tables.append(table_data)

                key_value_pairs = []
                if result.key_value_pairs:
                    for kv in result.key_value_pairs:
                        key_text = kv.key.content if kv.key else ""
                        value_text = kv.value.content if kv.value else ""
                        key_value_pairs.append(
                            {"key": key_text, "value": value_text}
                        )

                page_count = len(result.pages) if result.pages else 0

                return {
                    "content": content,
                    "tables": tables,
                    "key_value_pairs": key_value_pairs,
                    "page_count": page_count,
                }

            except Exception as exc:
                logger.error("Document Intelligence analysis failed: %s", str(exc))
                raise
        else:
            # Simulated analysis for development/testing
            text_content = document_bytes.decode("utf-8", errors="replace")
            logger.info(
                "Simulated Document Intelligence analysis: %d chars extracted",
                len(text_content),
            )
            return {
                "content": text_content,
                "tables": [],
                "key_value_pairs": [],
                "page_count": max(1, len(document_bytes) // 3000),
            }

    def _extract_medical_entities(self, text: str) -> list[dict]:
        """Step 3: Extract medical entities using regex-based NER simulation.

        In production, this would use Azure Text Analytics for Health.

        Tags entities with standardized codes:
            - diseases (ICD-10)
            - medications (RxNorm)
            - procedures (CPT)
            - lab_tests (LOINC)
            - anatomical_sites (SNOMED-CT)
            - dosages
            - temporal_expressions
        """
        entities: list[dict] = []
        seen_spans: set[tuple[int, int]] = set()

        for category, patterns in MEDICAL_ENTITY_PATTERNS.items():
            for pattern_tuple in patterns:
                pattern = pattern_tuple[0]
                code = pattern_tuple[1]

                for match in re.finditer(pattern, text, re.IGNORECASE):
                    start = match.start()
                    end = match.end()

                    # Skip overlapping entities
                    span = (start, end)
                    is_overlapping = False
                    for existing_start, existing_end in seen_spans:
                        if start < existing_end and end > existing_start:
                            is_overlapping = True
                            break

                    if is_overlapping:
                        continue

                    seen_spans.add(span)

                    entity = {
                        "text": match.group(0),
                        "category": category,
                        "offset": start,
                        "length": end - start,
                        "confidence_score": 0.85,
                    }

                    if code:
                        code_system, code_value = code.split(":", 1)
                        entity["coding"] = {
                            "system": code_system,
                            "code": code_value,
                        }

                    entities.append(entity)

        # Sort entities by their position in the text
        entities.sort(key=lambda e: e["offset"])

        logger.info(
            "Extracted %d medical entities across %d categories",
            len(entities),
            len(set(e["category"] for e in entities)),
        )

        return entities

    def _build_enriched_text(
        self,
        text: str,
        entities: list[dict],
        tables: list[dict],
        key_value_pairs: list[dict],
    ) -> str:
        """Build enriched text combining extracted content, entities, and structured data."""
        sections = [text]

        # Append table data as structured text
        if tables:
            sections.append("\n\n--- EXTRACTED TABLES ---")
            for idx, table in enumerate(tables):
                sections.append(f"\nTable {idx + 1} ({table['row_count']} rows x {table['column_count']} columns):")
                # Reconstruct table as text
                grid: dict[tuple[int, int], str] = {}
                for cell in table.get("cells", []):
                    grid[(cell["row_index"], cell["column_index"])] = cell["content"]

                for row in range(table["row_count"]):
                    row_cells = []
                    for col in range(table["column_count"]):
                        row_cells.append(grid.get((row, col), ""))
                    sections.append(" | ".join(row_cells))

        # Append key-value pairs
        if key_value_pairs:
            sections.append("\n\n--- KEY-VALUE PAIRS ---")
            for kv in key_value_pairs:
                if kv["key"] and kv["value"]:
                    sections.append(f"{kv['key']}: {kv['value']}")

        # Append entity summary
        if entities:
            sections.append("\n\n--- MEDICAL ENTITIES ---")
            by_category: dict[str, list[str]] = {}
            for entity in entities:
                cat = entity["category"]
                entry = entity["text"]
                if "coding" in entity:
                    entry += f" [{entity['coding']['system']}:{entity['coding']['code']}]"
                by_category.setdefault(cat, []).append(entry)

            for category, items in by_category.items():
                unique_items = list(dict.fromkeys(items))
                sections.append(f"{category}: {', '.join(unique_items)}")

        return "\n".join(sections)

    async def _chunk_and_embed(
        self,
        content: str,
        document_type: str,
        document_id: str,
        metadata: dict,
    ) -> list[dict]:
        """Steps 4-5: Chunk document using domain-aware rules and generate embeddings.

        Chunking strategy varies by document type:
        - Lab reports: Chunk by test/result sections
        - Prescriptions: Keep each prescription as one chunk
        - Discharge summaries: Chunk by clinical sections (HPI, assessment, plan)
        - Radiology reports: Chunk by findings/impression sections
        - Clinical guidelines: Chunk by recommendation sections with larger overlap
        - PubMed abstracts: Usually a single chunk unless very long
        """
        doc_type_enum = DocumentType(document_type)
        config = CHUNK_CONFIG.get(doc_type_enum, CHUNK_CONFIG[DocumentType.GENERIC])
        max_tokens = config["max_tokens"]
        overlap_tokens = config["overlap_tokens"]

        # Approximate tokens as words (rough 1:1.3 ratio)
        max_chars = max_tokens * 4
        overlap_chars = overlap_tokens * 4

        chunks: list[dict] = []

        if self.chunker is not None:
            # Use provided chunker (e.g., semantic chunker)
            raw_chunks = self.chunker.chunk(
                content, max_tokens=max_tokens, overlap_tokens=overlap_tokens
            )
        else:
            # Default: section-aware sliding window chunking
            raw_chunks = self._default_chunk(content, max_chars, overlap_chars)

        self._update_status(
            document_id,
            IngestionStatus.EMBEDDING,
            f"Generating embeddings for {len(raw_chunks)} chunks",
        )

        for idx, chunk_text in enumerate(raw_chunks):
            chunk_id = f"{document_id}_chunk_{idx:04d}"

            # Generate embedding
            embedding = await self._generate_embedding(chunk_text)

            chunk_doc = {
                "id": chunk_id,
                "document_id": document_id,
                "chunk_index": idx,
                "total_chunks": len(raw_chunks),
                "content": chunk_text,
                "content_vector": embedding,
                "document_type": document_type,
                "patient_id": metadata.get("patient_id"),
                "ingested_at": metadata.get("ingested_at", datetime.now(timezone.utc).isoformat()),
                "content_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                "char_count": len(chunk_text),
                "metadata": json.dumps(
                    {
                        k: v
                        for k, v in metadata.items()
                        if k
                        not in ("entities", "content_vector", "document_bytes")
                        and isinstance(v, (str, int, float, bool, list))
                    }
                ),
            }

            # Include entity references in the chunk
            entities = metadata.get("entities", [])
            chunk_entities = [
                e
                for e in entities
                if e["text"].lower() in chunk_text.lower()
            ]
            if chunk_entities:
                chunk_doc["entity_names"] = list(
                    set(e["text"] for e in chunk_entities)
                )
                chunk_doc["entity_codes"] = list(
                    set(
                        f"{e['coding']['system']}:{e['coding']['code']}"
                        for e in chunk_entities
                        if "coding" in e
                    )
                )

            chunks.append(chunk_doc)

        logger.info(
            "Created %d chunks for document %s (type=%s)",
            len(chunks),
            document_id,
            document_type,
        )

        return chunks

    def _default_chunk(
        self, text: str, max_chars: int, overlap_chars: int
    ) -> list[str]:
        """Default section-aware sliding window chunking.

        Attempts to split on section boundaries (double newlines, headers)
        before falling back to character-level splitting.
        """
        # Try to split on section boundaries first
        section_patterns = [
            r"\n\n(?=[A-Z][A-Z\s]+:)",  # SECTION HEADER:
            r"\n\n(?=\d+\.?\s+[A-Z])",  # Numbered sections
            r"\n\n(?=#{1,3}\s)",  # Markdown headers
            r"\n\n",  # Double newline
        ]

        sections: list[str] = []
        remaining = text

        for pattern in section_patterns:
            if len(remaining) <= max_chars:
                break
            parts = re.split(pattern, remaining)
            if len(parts) > 1:
                sections = parts
                remaining = ""
                break

        if remaining:
            sections = [remaining]

        # Merge small sections and split large ones
        chunks: list[str] = []
        current_chunk = ""

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(current_chunk) + len(section) + 2 <= max_chars:
                if current_chunk:
                    current_chunk += "\n\n" + section
                else:
                    current_chunk = section
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # If single section exceeds max_chars, split it
                if len(section) > max_chars:
                    sub_chunks = self._split_long_text(
                        section, max_chars, overlap_chars
                    )
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    # Overlap: carry the tail of the previous chunk
                    if chunks and overlap_chars > 0:
                        overlap_text = chunks[-1][-overlap_chars:]
                        current_chunk = overlap_text + "\n\n" + section
                    else:
                        current_chunk = section

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Ensure we return at least one chunk
        if not chunks:
            chunks = [text.strip() or "(empty document)"]

        return chunks

    def _split_long_text(
        self, text: str, max_chars: int, overlap_chars: int
    ) -> list[str]:
        """Split a long text block into overlapping chunks at sentence boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = current + " " + sentence if current else sentence
            else:
                if current:
                    chunks.append(current.strip())
                # Start new chunk with overlap
                if overlap_chars > 0 and current:
                    overlap = current[-overlap_chars:]
                    current = overlap + " " + sentence
                else:
                    current = sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for a text chunk."""
        if self.embedding_service is not None:
            try:
                if hasattr(self.embedding_service, "generate_embedding"):
                    return await self.embedding_service.generate_embedding(
                        text=text,
                        dimensions=self._embedding_dimensions,
                    )

                response = await self.embedding_service.embeddings.create(
                    input=text,
                    model=self._embedding_model,
                    dimensions=self._embedding_dimensions,
                )
                return response.data[0].embedding
            except Exception as exc:
                logger.error("Embedding generation failed: %s", str(exc))
                raise
        else:
            # Simulated embedding for development/testing
            # Generate a deterministic pseudo-embedding from content hash
            content_hash = hashlib.sha256(text.encode("utf-8")).digest()
            import struct

            embedding = []
            for i in range(self._embedding_dimensions):
                byte_idx = i % len(content_hash)
                val = (content_hash[byte_idx] + i) % 256
                # Normalize to [-1, 1]
                embedding.append((val / 128.0) - 1.0)
            return embedding

    async def _index_chunks(self, chunks: list[dict], index_name: str) -> dict:
        """Step 6: Index chunks in Azure AI Search.

        Uses the merge-or-upload action to handle both new and updated documents.
        Batches chunks in groups of 1000 (AI Search batch limit).
        """
        if not chunks:
            return {"succeeded": 0, "failed": 0}

        if self.search_client is not None:
            try:
                batch_size = 1000
                total_succeeded = 0
                total_failed = 0

                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i : i + batch_size]

                    # Prepare documents for indexing
                    index_docs = []
                    for chunk in batch:
                        doc = {
                            "@search.action": "mergeOrUpload",
                            "id": chunk["id"],
                            "document_id": chunk["document_id"],
                            "chunk_index": chunk["chunk_index"],
                            "content": chunk["content"],
                            "content_vector": chunk["content_vector"],
                            "document_type": chunk["document_type"],
                            "ingested_at": chunk["ingested_at"],
                            "metadata": chunk.get("metadata", "{}"),
                        }

                        if chunk.get("patient_id"):
                            doc["patient_id"] = chunk["patient_id"]
                        if chunk.get("entity_names"):
                            doc["entity_names"] = chunk["entity_names"]
                        if chunk.get("entity_codes"):
                            doc["entity_codes"] = chunk["entity_codes"]

                        # Protocol-specific fields
                        if chunk.get("specialty"):
                            doc["specialty"] = chunk["specialty"]
                        if chunk.get("guideline_name"):
                            doc["guideline_name"] = chunk["guideline_name"]
                        if chunk.get("version"):
                            doc["version"] = chunk["version"]

                        # PubMed-specific fields
                        if chunk.get("pmid"):
                            doc["pmid"] = chunk["pmid"]
                        if chunk.get("title"):
                            doc["title"] = chunk["title"]
                        if chunk.get("journal"):
                            doc["journal"] = chunk["journal"]
                        if chunk.get("mesh_terms"):
                            doc["mesh_terms"] = chunk["mesh_terms"]

                        index_docs.append(doc)

                    if hasattr(self.search_client, "index_documents_batch"):
                        result_summary = await self.search_client.index_documents_batch(
                            index_name=index_name,
                            documents=index_docs,
                        )
                        succeeded = int(result_summary.get("succeeded", 0))
                        failed = int(result_summary.get("failed", 0))
                    else:
                        result = await self.search_client.upload_documents(
                            documents=index_docs
                        )
                        succeeded = sum(1 for r in result if r.succeeded)
                        failed = sum(1 for r in result if not r.succeeded)
                    total_succeeded += succeeded
                    total_failed += failed

                    logger.info(
                        "Indexed batch %d-%d in '%s': %d succeeded, %d failed",
                        i,
                        i + len(batch),
                        index_name,
                        succeeded,
                        failed,
                    )

                return {"succeeded": total_succeeded, "failed": total_failed}

            except Exception as exc:
                logger.error(
                    "AI Search indexing failed for index '%s': %s",
                    index_name,
                    str(exc),
                )
                raise
        else:
            # Simulated indexing for development/testing
            logger.info(
                "Simulated indexing of %d chunks into index '%s'",
                len(chunks),
                index_name,
            )
            return {"succeeded": len(chunks), "failed": 0}

    async def _store_embeddings(
        self, chunks: list[dict], patient_id: str | None
    ) -> None:
        """Step 7: Store embeddings in Cosmos DB for vector search.

        Stores each chunk with its embedding vector in the embedding-cache container.
        Uses document_id + chunk_index as partition key for efficient retrieval.
        """
        if not chunks:
            return

        if self.cosmos_client is not None:
            try:
                cosmos_docs = []
                for chunk in chunks:
                    cosmos_docs.append(
                        {
                            "id": chunk["id"],
                            "document_id": chunk["document_id"],
                            "chunk_index": chunk["chunk_index"],
                            "content": chunk["content"],
                            "content_vector": chunk["content_vector"],
                            "document_type": chunk["document_type"],
                            "patient_id": patient_id,
                            "ingested_at": chunk["ingested_at"],
                            "content_hash": chunk.get("content_hash", ""),
                            "entity_names": chunk.get("entity_names", []),
                            "entity_codes": chunk.get("entity_codes", []),
                            "metadata": chunk.get("metadata", "{}"),
                            "ttl": -1,
                        }
                    )

                if hasattr(self.cosmos_client, "upsert_embedding_documents"):
                    await self.cosmos_client.upsert_embedding_documents(cosmos_docs)
                    logger.info(
                        "Stored %d embeddings via CosmosDBClient wrapper (patient_id=%s)",
                        len(cosmos_docs),
                        patient_id,
                    )
                    return

                database = self.cosmos_client.get_database_client(
                    self._cosmos_database
                )
                container = database.get_container_client(
                    self._cosmos_embeddings_container
                )

                for cosmos_doc in cosmos_docs:
                    await container.upsert_item(body=cosmos_doc)

                logger.info(
                    "Stored %d embeddings in Cosmos DB (patient_id=%s)",
                    len(chunks),
                    patient_id,
                )

            except Exception as exc:
                logger.error(
                    "Cosmos DB storage failed: %s", str(exc)
                )
                raise
        else:
            # Simulated storage for development/testing
            logger.info(
                "Simulated Cosmos DB storage of %d embeddings (patient_id=%s)",
                len(chunks),
                patient_id,
            )
