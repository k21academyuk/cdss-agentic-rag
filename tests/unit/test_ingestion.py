"""Tests for the document ingestion pipeline.

Covers full pipeline ingestion, treatment protocol ingestion, PubMed
batch ingestion, medical entity extraction, status tracking, and
error handling at each pipeline stage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cdss.core.exceptions import DocumentProcessingError
from cdss.rag.chunker import DocumentChunk, MedicalDocumentChunker


# ═══════════════════════════════════════════════════════════════════════════════
# Ingestion Pipeline Implementation for Testing
# ═══════════════════════════════════════════════════════════════════════════════


class _IngestionPipeline:
    """Ingestion pipeline implementation with injectable dependencies."""

    def __init__(
        self,
        chunker: MedicalDocumentChunker,
        openai_client: AsyncMock,
        search_client: AsyncMock,
        cosmos_client: AsyncMock,
    ):
        self.chunker = chunker
        self.openai = openai_client
        self.search = search_client
        self.cosmos = cosmos_client
        self._statuses: dict[str, dict] = {}

    async def ingest_document(
        self,
        content: str,
        document_type: str,
        document_id: str = "doc-auto",
        metadata: dict | None = None,
    ) -> dict:
        """Full ingestion pipeline: chunk -> embed -> index."""
        self._statuses[document_id] = {"status": "in_progress", "stage": "chunking"}

        try:
            # Stage 1: Chunk
            chunks = self.chunker.chunk_document(
                content=content,
                document_type=document_type,
                document_id=document_id,
                metadata=metadata,
            )
            self._statuses[document_id]["stage"] = "embedding"
            self._statuses[document_id]["chunks_created"] = len(chunks)

            # Stage 2: Generate embeddings
            texts = [c.content for c in chunks]
            embeddings = await self.openai.generate_embeddings_batch(texts)
            self._statuses[document_id]["stage"] = "indexing"

            # Stage 3: Index to Azure AI Search
            documents = []
            for chunk, embedding in zip(chunks, embeddings):
                doc = {
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "content_vector": embedding,
                    "document_id": chunk.document_id,
                    "section_type": chunk.section_type,
                    "patient_id": chunk.patient_id,
                    "date": chunk.date,
                    "medical_codes": chunk.medical_codes,
                    "metadata": chunk.metadata,
                }
                documents.append(doc)

            index_result = await self.search.index_documents_batch(
                "patient_records", documents
            )
            self._statuses[document_id]["stage"] = "entity_extraction"

            # Stage 4: Extract medical entities
            entities = self._extract_medical_entities(content)
            self._statuses[document_id]["entities"] = entities

            self._statuses[document_id]["status"] = "completed"
            self._statuses[document_id]["stage"] = "done"

            return {
                "status": "completed",
                "document_id": document_id,
                "chunks_created": len(chunks),
                "index_result": index_result,
                "entities": entities,
            }

        except DocumentProcessingError:
            self._statuses[document_id]["status"] = "failed"
            raise
        except Exception as exc:
            self._statuses[document_id]["status"] = "failed"
            self._statuses[document_id]["error"] = str(exc)
            raise

    async def ingest_treatment_protocol(
        self,
        content: str,
        guideline_name: str,
        specialty: str,
        metadata: dict | None = None,
    ) -> dict:
        """Ingest a treatment protocol into the protocols index."""
        metadata = metadata or {}
        metadata["guideline_name"] = guideline_name
        metadata["specialty"] = specialty

        chunks = self.chunker.chunk_document(
            content=content,
            document_type="clinical_guideline",
            document_id=f"proto-{guideline_name}",
            metadata=metadata,
        )

        texts = [c.content for c in chunks]
        embeddings = await self.openai.generate_embeddings_batch(texts)

        documents = []
        for chunk, embedding in zip(chunks, embeddings):
            doc = {
                "id": chunk.chunk_id,
                "content": chunk.content,
                "content_vector": embedding,
                "specialty": specialty,
                "guideline": guideline_name,
                "metadata": chunk.metadata,
            }
            documents.append(doc)

        index_result = await self.search.index_documents_batch(
            "treatment_protocols", documents
        )

        return {
            "status": "completed",
            "guideline": guideline_name,
            "chunks_created": len(chunks),
            "index_result": index_result,
        }

    async def ingest_pubmed_articles(
        self, articles: list[dict]
    ) -> dict:
        """Batch ingest PubMed articles into the literature index."""
        total_chunks = 0
        for article in articles:
            abstract = article.get("abstract", "")
            if not abstract.strip():
                continue

            metadata = {
                "pmid": article.get("pmid", ""),
                "title": article.get("title", ""),
                "authors": article.get("authors", []),
                "journal": article.get("journal", ""),
                "publication_date": article.get("pub_date", ""),
                "mesh_terms": article.get("mesh_terms", []),
            }

            chunks = self.chunker.chunk_document(
                content=abstract,
                document_type="pubmed_abstract",
                document_id=f"pmid-{article.get('pmid', '')}",
                metadata=metadata,
            )

            texts = [c.content for c in chunks]
            embeddings = await self.openai.generate_embeddings_batch(texts)

            documents = []
            for chunk, embedding in zip(chunks, embeddings):
                doc = {
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "content_vector": embedding,
                    "pmid": article.get("pmid", ""),
                    "metadata": chunk.metadata,
                }
                documents.append(doc)

            await self.search.index_documents_batch("medical_literature", documents)
            total_chunks += len(chunks)

        return {
            "status": "completed",
            "articles_processed": len(articles),
            "total_chunks": total_chunks,
        }

    def _extract_medical_entities(self, content: str) -> dict:
        """Extract medical entities from document content."""
        import re

        entities: dict[str, list[str]] = {
            "conditions": [],
            "medications": [],
            "labs": [],
        }

        # ICD-10 codes -> conditions
        icd10_pattern = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,4})?)\b")
        for match in icd10_pattern.finditer(content):
            code = match.group(1)
            if len(code) >= 3:
                entities["conditions"].append(code)

        # Common medication patterns
        med_keywords = [
            "metformin", "lisinopril", "dapagliflozin", "insulin",
            "aspirin", "atorvastatin", "amlodipine", "warfarin",
        ]
        content_lower = content.lower()
        for med in med_keywords:
            if med in content_lower:
                entities["medications"].append(med)

        # LOINC codes -> labs
        loinc_pattern = re.compile(r"\b(\d{4,5}-\d)\b")
        for match in loinc_pattern.finditer(content):
            entities["labs"].append(match.group(1))

        return entities

    def get_ingestion_status(self, document_id: str) -> dict:
        """Return the current status of a document ingestion."""
        return self._statuses.get(document_id, {"status": "not_found"})


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def chunker() -> MedicalDocumentChunker:
    return MedicalDocumentChunker(default_chunk_size=512, default_overlap=128)


@pytest.fixture
def pipeline(chunker, mock_openai_client, mock_search_client, mock_cosmos_client) -> _IngestionPipeline:
    return _IngestionPipeline(
        chunker=chunker,
        openai_client=mock_openai_client,
        search_client=mock_search_client,
        cosmos_client=mock_cosmos_client,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestIngestDocument:
    """Test the full ingest_document pipeline."""

    async def test_full_pipeline(self, pipeline, mock_openai_client, mock_search_client):
        content = (
            "Patient ID: P-12345\n"
            "Date: 2025-01-15\n\n"
            "CBC:\n"
            "WBC: 7.5 K/uL (4.5-11.0)\n"
            "Hemoglobin: 14.2 g/dL\n\n"
            "Diagnosis: E11.9 Type 2 diabetes mellitus\n"
            "Medications: metformin 500mg BID"
        )

        result = await pipeline.ingest_document(
            content=content,
            document_type="lab_report",
            document_id="doc-test-001",
            metadata={"patient_id": "P-12345"},
        )

        assert result["status"] == "completed"
        assert result["chunks_created"] >= 1
        mock_openai_client.generate_embeddings_batch.assert_called()
        mock_search_client.index_documents_batch.assert_called()

    async def test_pipeline_chunks_are_indexed(self, pipeline, mock_search_client):
        content = "Simple lab report with WBC: 7.5 and RBC: 4.8"
        await pipeline.ingest_document(content, "lab_report", "doc-test-002")

        call_args = mock_search_client.index_documents_batch.call_args
        documents = call_args[0][1]
        assert len(documents) >= 1
        assert all("content_vector" in doc for doc in documents)
        assert all("content" in doc for doc in documents)

    async def test_pipeline_extracts_entities(self, pipeline):
        content = (
            "Patient has E11.9 diabetes and N18.3 CKD.\n"
            "Current medications: metformin and lisinopril.\n"
            "Lab results: LOINC 4548-4 HbA1c 7.2%"
        )
        result = await pipeline.ingest_document(content, "lab_report", "doc-test-003")

        entities = result["entities"]
        assert "E11.9" in entities["conditions"]
        assert "N18.3" in entities["conditions"]
        assert "metformin" in entities["medications"]
        assert "lisinopril" in entities["medications"]
        assert "4548-4" in entities["labs"]


class TestIngestTreatmentProtocol:
    """Test treatment protocol ingestion."""

    async def test_ingest_protocol(self, pipeline, mock_search_client):
        content = (
            "Recommendation 1: Use SGLT2 inhibitors for T2DM with CKD. Grade A.\n\n"
            "Recommendation 2: Monitor eGFR quarterly. Grade B."
        )

        result = await pipeline.ingest_treatment_protocol(
            content=content,
            guideline_name="ADA 2024",
            specialty="endocrinology",
        )

        assert result["status"] == "completed"
        assert result["guideline"] == "ADA 2024"
        assert result["chunks_created"] >= 1

        call_args = mock_search_client.index_documents_batch.call_args
        index_name = call_args[0][0]
        documents = call_args[0][1]
        assert index_name == "treatment_protocols"
        assert all(doc.get("specialty") == "endocrinology" for doc in documents)


class TestIngestPubmedArticles:
    """Test PubMed article batch ingestion."""

    async def test_batch_ingest(self, pipeline, sample_pubmed_articles, mock_search_client):
        result = await pipeline.ingest_pubmed_articles(sample_pubmed_articles)

        assert result["status"] == "completed"
        assert result["articles_processed"] == 2
        assert result["total_chunks"] >= 2
        assert mock_search_client.index_documents_batch.call_count == 2

    async def test_skips_empty_abstracts(self, pipeline, mock_search_client):
        articles = [
            {"pmid": "11111", "title": "No abstract", "abstract": ""},
            {"pmid": "22222", "title": "Has abstract", "abstract": "Some content here."},
        ]
        result = await pipeline.ingest_pubmed_articles(articles)

        assert result["articles_processed"] == 2
        assert result["total_chunks"] == 1  # only the one with abstract
        mock_search_client.index_documents_batch.assert_called_once()

    async def test_preserves_metadata(self, pipeline, mock_search_client):
        articles = [
            {
                "pmid": "32970396",
                "title": "DAPA-CKD",
                "abstract": "Study of dapagliflozin in CKD patients.",
                "authors": ["Heerspink HJL"],
                "journal": "N Engl J Med",
                "pub_date": "2020-10-08",
                "mesh_terms": ["Diabetes", "CKD"],
            }
        ]
        await pipeline.ingest_pubmed_articles(articles)

        call_args = mock_search_client.index_documents_batch.call_args
        documents = call_args[0][1]
        assert documents[0]["pmid"] == "32970396"


class TestExtractMedicalEntities:
    """Test medical entity extraction."""

    @pytest.fixture
    def pipeline_for_entities(self, pipeline):
        return pipeline

    def test_detects_conditions(self, pipeline_for_entities):
        content = "Diagnosed with E11.9 and I10 hypertension"
        entities = pipeline_for_entities._extract_medical_entities(content)
        assert "E11.9" in entities["conditions"]
        assert "I10" in entities["conditions"]

    def test_detects_medications(self, pipeline_for_entities):
        content = "Patient taking metformin, lisinopril, and aspirin daily."
        entities = pipeline_for_entities._extract_medical_entities(content)
        assert "metformin" in entities["medications"]
        assert "lisinopril" in entities["medications"]
        assert "aspirin" in entities["medications"]

    def test_detects_labs(self, pipeline_for_entities):
        content = "LOINC 4548-4 HbA1c: 7.2%, LOINC 2160-0 Creatinine: 1.8"
        entities = pipeline_for_entities._extract_medical_entities(content)
        assert "4548-4" in entities["labs"]
        assert "2160-0" in entities["labs"]

    def test_no_entities_in_plain_text(self, pipeline_for_entities):
        content = "The patient is feeling well and reports no complaints."
        entities = pipeline_for_entities._extract_medical_entities(content)
        assert len(entities["conditions"]) == 0
        assert len(entities["medications"]) == 0
        assert len(entities["labs"]) == 0


class TestGetIngestionStatus:
    """Test ingestion status tracking."""

    async def test_status_after_completion(self, pipeline):
        content = "WBC: 7.5 K/uL"
        await pipeline.ingest_document(content, "lab_report", "doc-status-001")

        status = pipeline.get_ingestion_status("doc-status-001")
        assert status["status"] == "completed"
        assert status["stage"] == "done"

    def test_status_not_found(self, pipeline):
        status = pipeline.get_ingestion_status("nonexistent-doc")
        assert status["status"] == "not_found"


class TestErrorHandling:
    """Test error handling at each pipeline stage."""

    async def test_chunking_error_empty_content(self, pipeline):
        with pytest.raises(DocumentProcessingError):
            await pipeline.ingest_document("", "lab_report", "doc-err-001")

        status = pipeline.get_ingestion_status("doc-err-001")
        assert status["status"] == "failed"

    async def test_embedding_error(self, pipeline, mock_openai_client):
        mock_openai_client.generate_embeddings_batch.side_effect = Exception("Embedding API down")

        with pytest.raises(Exception, match="Embedding API down"):
            await pipeline.ingest_document("Some content", "lab_report", "doc-err-002")

        status = pipeline.get_ingestion_status("doc-err-002")
        assert status["status"] == "failed"

    async def test_indexing_error(self, pipeline, mock_search_client):
        mock_search_client.index_documents_batch.side_effect = Exception("Search index unavailable")

        with pytest.raises(Exception, match="Search index unavailable"):
            await pipeline.ingest_document("Some content", "lab_report", "doc-err-003")

        status = pipeline.get_ingestion_status("doc-err-003")
        assert status["status"] == "failed"
