"""RAG (Retrieval-Augmented Generation) pipeline for the Clinical Decision Support System.

This package provides the complete RAG pipeline for medical document processing:

- **MedicalDocumentChunker**: Domain-aware chunking for medical documents
  (lab reports, discharge summaries, radiology reports, clinical guidelines,
  prescriptions, PubMed abstracts) with section-aware splitting and
  medical code extraction.

- **DocumentChunk**: Data class representing a single chunk with full
  provenance metadata including section type, patient ID, medical codes,
  and confidence score.

- **EmbeddingService**: Embedding generation using Azure OpenAI
  text-embedding-3-large with Cosmos DB caching and Float16 compression.

- **HybridRetriever**: Three-stage retrieval pipeline combining hybrid
  search (BM25 + vector), semantic reranking, and LLM-based relevance
  filtering for maximum precision.

- **CrossSourceFusion**: Weighted cross-source fusion that combines
  results from patient records, drug interactions, treatment protocols,
  and medical literature into a structured context for the synthesis LLM.
"""

from cdss.rag.chunker import DocumentChunk, MedicalDocumentChunker
from cdss.rag.embedder import EmbeddingService
from cdss.rag.fusion import CrossSourceFusion
from cdss.rag.retriever import HybridRetriever

__all__ = [
    "DocumentChunk",
    "MedicalDocumentChunker",
    "EmbeddingService",
    "HybridRetriever",
    "CrossSourceFusion",
]
