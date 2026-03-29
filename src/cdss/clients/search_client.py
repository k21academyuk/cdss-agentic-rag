"""Azure AI Search client wrapper for hybrid search with semantic ranking."""

from __future__ import annotations

from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import RetrieverError
from cdss.core.logging import get_logger

logger = get_logger(__name__)

# Logical index identifiers used across the Python codebase.
INDEX_PATIENT_RECORDS = "patient_records"
INDEX_TREATMENT_PROTOCOLS = "treatment_protocols"
INDEX_MEDICAL_LITERATURE = "medical_literature"

ALL_INDEXES = [INDEX_PATIENT_RECORDS, INDEX_TREATMENT_PROTOCOLS, INDEX_MEDICAL_LITERATURE]


class AzureSearchClient:
    """Wrapper for Azure AI Search with hybrid search + semantic ranking.

    Provides hybrid search (BM25 + vector) with optional semantic reranking
    across patient records, treatment protocols, and medical literature indexes.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Azure AI Search client with connections to all indexes.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self._settings = settings or get_settings()
        self._credential = AzureKeyCredential(self._settings.azure_search_api_key)
        self._endpoint = self._settings.azure_search_endpoint
        self._index_name_map: dict[str, str] = {
            INDEX_PATIENT_RECORDS: self._settings.azure_search_patient_records_index,
            INDEX_TREATMENT_PROTOCOLS: self._settings.azure_search_treatment_protocols_index,
            INDEX_MEDICAL_LITERATURE: self._settings.azure_search_medical_literature_index,
        }
        patient_semantic = self._settings.azure_search_patient_records_semantic_config
        protocols_semantic = self._settings.azure_search_treatment_protocols_semantic_config
        literature_semantic = self._settings.azure_search_medical_literature_semantic_config
        self._semantic_config_map: dict[str, str] = {
            INDEX_PATIENT_RECORDS: patient_semantic,
            self._settings.azure_search_patient_records_index: patient_semantic,
            INDEX_TREATMENT_PROTOCOLS: protocols_semantic,
            self._settings.azure_search_treatment_protocols_index: protocols_semantic,
            INDEX_MEDICAL_LITERATURE: literature_semantic,
            self._settings.azure_search_medical_literature_index: literature_semantic,
        }

        self._clients: dict[str, SearchClient] = {}
        for logical_index_name, physical_index_name in self._index_name_map.items():
            client = SearchClient(
                endpoint=self._endpoint,
                index_name=physical_index_name,
                credential=self._credential,
            )
            self._clients[logical_index_name] = client
            self._clients[physical_index_name] = client

        logger.info(
            "AzureSearchClient initialized",
            endpoint=self._endpoint,
            indexes=self._index_name_map,
        )

    def _get_client(self, index_name: str) -> SearchClient:
        """Get the SearchClient for a specific index.

        Args:
            index_name: Name of the search index.

        Returns:
            The SearchClient instance for the given index.

        Raises:
            RetrieverError: If the index name is not recognized.
        """
        client = self._clients.get(index_name)
        if client is None:
            raise RetrieverError(
                f"Unknown search index: '{index_name}'. "
                f"Valid indexes: {ALL_INDEXES}"
            )
        return client

    def resolve_index_name(self, index_name: str) -> str:
        """Resolve logical or physical index identifier to physical index name."""
        if index_name in self._index_name_map:
            return self._index_name_map[index_name]
        return index_name

    async def hybrid_search(
        self,
        index_name: str,
        query: str,
        query_vector: list[float] | None = None,
        filters: str | None = None,
        top: int = 50,
        semantic_config: str | None = None,
    ) -> list[dict]:
        """Perform hybrid search (BM25 + vector) with optional semantic reranking.

        Combines keyword-based BM25 scoring with vector similarity search.
        When a query vector is provided, results are fused using Reciprocal
        Rank Fusion (RRF). Semantic reranking is applied on top for improved
        relevance.

        Args:
            index_name: Name of the search index to query.
            query: The text query for BM25 keyword search.
            query_vector: Optional embedding vector for vector search.
            filters: Optional OData filter expression.
            top: Maximum number of results to return.
            semantic_config: Name of the semantic configuration to use.
                If omitted, uses the index-specific configured default.

        Returns:
            List of result dicts with keys: id, score, reranker_score,
            content, metadata.

        Raises:
            RetrieverError: If the search operation fails.
        """
        client = self._get_client(index_name)

        try:
            resolved_semantic_config = semantic_config or self._semantic_config_map.get(index_name, "default")
            search_kwargs: dict[str, Any] = {
                "search_text": query,
                "query_type": "semantic",
                "semantic_configuration_name": resolved_semantic_config,
                "top": top,
                "include_total_count": True,
            }

            if query_vector is not None:
                vector_query = VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=top,
                    fields="content_vector",
                )
                search_kwargs["vector_queries"] = [vector_query]

            if filters is not None:
                search_kwargs["filter"] = filters

            logger.debug(
                "Executing hybrid search",
                index=index_name,
                semantic_config=resolved_semantic_config,
                query_length=len(query),
                has_vector=query_vector is not None,
                has_filter=filters is not None,
                top=top,
            )

            results = client.search(**search_kwargs)

            search_results: list[dict] = []
            for result in results:
                doc = {
                    "id": result.get("id", ""),
                    "score": result.get("@search.score", 0.0),
                    "reranker_score": result.get("@search.reranker_score", 0.0),
                    "content": result.get("content", ""),
                    "metadata": {
                        key: value
                        for key, value in result.items()
                        if key
                        not in (
                            "id",
                            "@search.score",
                            "@search.reranker_score",
                            "content",
                            "content_vector",
                        )
                    },
                }
                search_results.append(doc)

            logger.info(
                "Hybrid search completed",
                index=index_name,
                results_count=len(search_results),
                total_count=results.get_count(),
            )

            return search_results

        except Exception as exc:
            logger.error(
                "Hybrid search failed",
                index=index_name,
                error=str(exc),
            )
            raise RetrieverError(
                f"Hybrid search failed on index '{index_name}': {exc}"
            ) from exc

    async def search_document_chunks(
        self,
        index_name: str,
        document_id: str,
        search_text: str = "*",
        top: int = 5,
        search_mode: str = "all",
        query_type: str = "simple",
    ) -> list[dict]:
        """Search chunks for a specific ingested document ID.

        Uses a strict ``document_id`` filter and supports either wildcard
        (index proof) or phrase search (retrieval proof).
        """
        client = self._get_client(index_name)
        escaped_document_id = document_id.replace("'", "''")
        safe_search_text = search_text.strip() or "*"
        safe_search_mode = search_mode if search_mode in {"all", "any"} else "all"
        safe_query_type = query_type if query_type in {"simple", "semantic"} else "simple"

        try:
            results = client.search(
                search_text=safe_search_text,
                query_type=safe_query_type,
                search_mode=safe_search_mode,
                filter=f"document_id eq '{escaped_document_id}'",
                top=top,
                include_total_count=True,
            )

            search_results: list[dict] = []
            for result in results:
                search_results.append(
                    {
                        "id": result.get("id", ""),
                        "score": result.get("@search.score", 0.0),
                        "document_id": result.get("document_id", ""),
                        "chunk_index": result.get("chunk_index"),
                        "content": result.get("content", ""),
                        "document_type": result.get("document_type", ""),
                        "patient_id": result.get("patient_id"),
                        "pmid": result.get("pmid"),
                        "title": result.get("title"),
                        "guideline_name": result.get("guideline_name"),
                        "specialty": result.get("specialty"),
                    }
                )

            logger.info(
                "Document chunk search completed",
                index=index_name,
                document_id=document_id,
                search_text=safe_search_text,
                search_mode=safe_search_mode,
                query_type=safe_query_type,
                results_count=len(search_results),
            )
            return search_results
        except Exception as exc:
            logger.error(
                "Document chunk search failed",
                index=index_name,
                document_id=document_id,
                search_text=safe_search_text,
                search_mode=safe_search_mode,
                query_type=safe_query_type,
                error=str(exc),
            )
            raise RetrieverError(
                f"Document chunk search failed on index '{index_name}': {exc}"
            ) from exc

    async def delete_document_chunks(
        self,
        index_name: str,
        document_id: str,
        batch_size: int = 1000,
        max_batches: int = 50,
    ) -> dict[str, Any]:
        """Delete all chunks for a specific ingested document ID.

        Deletes in batches to handle large documents safely.

        Returns:
            Dictionary with delete summary metadata.
        """
        client = self._get_client(index_name)
        escaped_document_id = document_id.replace("'", "''")
        total_deleted = 0
        total_failed = 0
        batches_processed = 0

        try:
            while batches_processed < max_batches:
                search_results = client.search(
                    search_text="*",
                    query_type="simple",
                    search_mode="all",
                    filter=f"document_id eq '{escaped_document_id}'",
                    top=batch_size,
                    select=["id"],
                )

                ids_to_delete = [
                    result.get("id", "")
                    for result in search_results
                    if result.get("id")
                ]

                if not ids_to_delete:
                    break

                delete_results = client.delete_documents(
                    documents=[{"id": doc_id} for doc_id in ids_to_delete]
                )
                batch_deleted = sum(1 for result in delete_results if result.succeeded)
                batch_failed = sum(1 for result in delete_results if not result.succeeded)

                total_deleted += batch_deleted
                total_failed += batch_failed
                batches_processed += 1

                logger.info(
                    "Document chunk delete batch completed",
                    index=index_name,
                    document_id=document_id,
                    batch_size=len(ids_to_delete),
                    deleted=batch_deleted,
                    failed=batch_failed,
                )

                # If fewer than batch_size were found, we've likely exhausted all hits.
                if len(ids_to_delete) < batch_size:
                    break

            return {
                "document_id": document_id,
                "index_name": index_name,
                "deleted_count": total_deleted,
                "failed_count": total_failed,
                "batches_processed": batches_processed,
            }

        except Exception as exc:
            logger.error(
                "Document chunk deletion failed",
                index=index_name,
                document_id=document_id,
                error=str(exc),
            )
            raise RetrieverError(
                f"Document chunk deletion failed on index '{index_name}': {exc}"
            ) from exc

    async def search_patient_records(
        self,
        query: str,
        patient_id: str | None = None,
        query_vector: list[float] | None = None,
        top: int = 20,
    ) -> list[dict]:
        """Search patient records index with optional patient_id filter.

        Args:
            query: Clinical query text.
            patient_id: Optional patient identifier to filter results.
            query_vector: Optional embedding vector for vector search.
            top: Maximum number of results to return.

        Returns:
            List of matching patient record documents.

        Raises:
            RetrieverError: If the search fails.
        """
        filters = None
        if patient_id is not None:
            filters = f"patient_id eq '{patient_id}'"

        logger.debug(
            "Searching patient records",
            patient_id=patient_id,
            query_length=len(query),
        )

        return await self.hybrid_search(
            index_name=INDEX_PATIENT_RECORDS,
            query=query,
            query_vector=query_vector,
            filters=filters,
            top=top,
            semantic_config=self._settings.azure_search_patient_records_semantic_config,
        )

    async def search_treatment_protocols(
        self,
        query: str,
        specialty: str | None = None,
        query_vector: list[float] | None = None,
        top: int = 20,
    ) -> list[dict]:
        """Search treatment protocols index with optional specialty filter.

        Args:
            query: Clinical query text about treatments or protocols.
            specialty: Optional medical specialty to filter by (e.g., "cardiology").
            query_vector: Optional embedding vector for vector search.
            top: Maximum number of results to return.

        Returns:
            List of matching treatment protocol documents.

        Raises:
            RetrieverError: If the search fails.
        """
        filters = None
        if specialty is not None:
            filters = f"specialty eq '{specialty}'"

        logger.debug(
            "Searching treatment protocols",
            specialty=specialty,
            query_length=len(query),
        )

        return await self.hybrid_search(
            index_name=INDEX_TREATMENT_PROTOCOLS,
            query=query,
            query_vector=query_vector,
            filters=filters,
            top=top,
            semantic_config=self._settings.azure_search_treatment_protocols_semantic_config,
        )

    async def search_medical_literature(
        self,
        query: str,
        query_vector: list[float] | None = None,
        top: int = 20,
    ) -> list[dict]:
        """Search cached medical literature index.

        Args:
            query: Clinical or research query text.
            query_vector: Optional embedding vector for vector search.
            top: Maximum number of results to return.

        Returns:
            List of matching medical literature documents.

        Raises:
            RetrieverError: If the search fails.
        """
        logger.debug(
            "Searching medical literature",
            query_length=len(query),
        )

        return await self.hybrid_search(
            index_name=INDEX_MEDICAL_LITERATURE,
            query=query,
            query_vector=query_vector,
            top=top,
            semantic_config=self._settings.azure_search_medical_literature_semantic_config,
        )

    async def index_document(self, index_name: str, document: dict) -> None:
        """Index a single document into the specified search index.

        Args:
            index_name: Name of the target search index.
            document: Document dict to index. Must include an 'id' field.

        Raises:
            RetrieverError: If the indexing operation fails.
        """
        client = self._get_client(index_name)

        try:
            result = client.upload_documents(documents=[document])

            succeeded = sum(1 for r in result if r.succeeded)
            if succeeded == 0:
                error_messages = [r.error_message or "unknown error" for r in result if not r.succeeded]
                raise RetrieverError(
                    f"Document indexing failed: {'; '.join(error_messages)}"
                )

            logger.info(
                "Document indexed successfully",
                index=index_name,
                document_id=document.get("id", "unknown"),
            )

        except RetrieverError:
            raise
        except Exception as exc:
            logger.error(
                "Document indexing failed",
                index=index_name,
                document_id=document.get("id", "unknown"),
                error=str(exc),
            )
            raise RetrieverError(
                f"Failed to index document in '{index_name}': {exc}"
            ) from exc

    async def index_documents_batch(
        self, index_name: str, documents: list[dict]
    ) -> dict:
        """Batch index documents into the specified search index.

        Args:
            index_name: Name of the target search index.
            documents: List of document dicts to index. Each must include an 'id' field.

        Returns:
            Dict with keys: total, succeeded, failed, errors.

        Raises:
            RetrieverError: If the batch indexing operation fails entirely.
        """
        client = self._get_client(index_name)

        if not documents:
            logger.warning("Empty document batch provided, skipping indexing")
            return {"total": 0, "succeeded": 0, "failed": 0, "errors": []}

        try:
            batch_size = 1000
            total_succeeded = 0
            total_failed = 0
            all_errors: list[str] = []

            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]
                results = client.upload_documents(documents=batch)

                for result in results:
                    if result.succeeded:
                        total_succeeded += 1
                    else:
                        total_failed += 1
                        all_errors.append(
                            f"Document '{result.key}': {result.error_message}"
                        )

                logger.debug(
                    "Batch chunk indexed",
                    index=index_name,
                    batch_start=i,
                    batch_size=len(batch),
                )

            summary = {
                "total": len(documents),
                "succeeded": total_succeeded,
                "failed": total_failed,
                "errors": all_errors,
            }

            logger.info(
                "Batch indexing completed",
                index=index_name,
                total=summary["total"],
                succeeded=summary["succeeded"],
                failed=summary["failed"],
            )

            return summary

        except Exception as exc:
            logger.error(
                "Batch indexing failed",
                index=index_name,
                total_documents=len(documents),
                error=str(exc),
            )
            raise RetrieverError(
                f"Batch indexing failed on '{index_name}': {exc}"
            ) from exc
