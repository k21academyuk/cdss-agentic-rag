"""Three-stage hybrid retrieval pipeline for the Clinical Decision Support System.

Implements a progressive retrieval strategy:
  Stage 1: Hybrid Search (BM25 + vector) via Azure AI Search -> top 50 candidates
  Stage 2: Semantic Reranking via Azure AI Search L2 reranker -> top 20
  Stage 3: LLM-based Relevance Filtering via GPT-4o-mini -> final top-k (score > threshold)

This pipeline maximizes both recall (through broad hybrid search) and precision
(through progressively stricter filtering).
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncAzureOpenAI

from cdss.clients.search_client import (
    INDEX_MEDICAL_LITERATURE,
    INDEX_PATIENT_RECORDS,
    INDEX_TREATMENT_PROTOCOLS,
    AzureSearchClient,
)
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError, RetrieverError
from cdss.core.logging import get_logger
from cdss.rag.embedder import EmbeddingService

logger = get_logger(__name__)

# Prompt template for Stage 3 LLM-based relevance scoring
_RELEVANCE_SCORING_SYSTEM_PROMPT = """You are a clinical relevance scoring system. Your task is to evaluate how relevant a retrieved document is to a clinical query.

Score each document on a scale from 0.0 to 1.0:
- 1.0: Directly answers the clinical question with specific, applicable information
- 0.8-0.9: Highly relevant with directly applicable clinical data
- 0.6-0.7: Moderately relevant with useful supporting information
- 0.4-0.5: Tangentially related but not directly applicable
- 0.2-0.3: Minimally related with limited clinical utility
- 0.0-0.1: Not relevant to the clinical question

Consider:
1. Clinical specificity: Does the document address the specific condition, drug, or procedure in the query?
2. Patient applicability: Is the information applicable to the patient context?
3. Evidence quality: Is the information from a reliable clinical source?
4. Actionability: Does it provide actionable clinical guidance?

Respond with ONLY a JSON array of objects, each with "index" (0-based) and "score" (float 0.0-1.0).
Example: [{"index": 0, "score": 0.85}, {"index": 1, "score": 0.42}]"""

_RELEVANCE_SCORING_USER_TEMPLATE = """Clinical Query: {query}

Documents to score:
{documents}

Score each document's relevance to the clinical query. Respond with ONLY the JSON array."""


class HybridRetriever:
    """Three-stage retrieval: Hybrid Search -> Semantic Reranking -> Agent-Level Filtering.

    Orchestrates the full retrieval pipeline across Azure AI Search indexes,
    combining broad recall with precise relevance filtering.

    Attributes:
        _search_client: Azure AI Search client for hybrid search.
        _openai_client: Azure OpenAI client for LLM-based filtering.
        _embedding_service: Service for generating query embeddings.
        _settings: Application settings.
    """

    def __init__(
        self,
        search_client: AzureSearchClient | None = None,
        openai_client: AsyncAzureOpenAI | None = None,
        embedding_service: EmbeddingService | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            search_client: Pre-configured AzureSearchClient. Created from
                settings if None.
            openai_client: Pre-configured AsyncAzureOpenAI client for Stage 3
                LLM filtering. Created from settings if None.
            embedding_service: Pre-configured EmbeddingService for query
                embedding generation. Created from settings if None.
            settings: Application settings. Loaded from environment if None.
        """
        self._settings = settings or get_settings()

        if search_client is not None:
            self._search_client = search_client
        else:
            self._search_client = AzureSearchClient(settings=self._settings)

        if openai_client is not None:
            self._openai_client = openai_client
        else:
            self._openai_client = AsyncAzureOpenAI(
                azure_endpoint=self._settings.azure_openai_endpoint,
                api_key=self._settings.azure_openai_api_key,
                api_version=self._settings.azure_openai_api_version,
            )

        if embedding_service is not None:
            self._embedding_service = embedding_service
        else:
            self._embedding_service = EmbeddingService(
                openai_client=self._openai_client,
                settings=self._settings,
            )

        self._mini_deployment = self._settings.azure_openai_mini_deployment_name

        logger.info(
            "HybridRetriever initialized",
            extra={"mini_deployment": self._mini_deployment},
        )

    async def retrieve(
        self,
        query: str,
        index_name: str,
        filters: str | None = None,
        top_k: int = 10,
        rerank: bool = True,
        relevance_threshold: float = 0.7,
    ) -> list[dict]:
        """Full three-stage retrieval pipeline.

        Stage 1: Hybrid search (BM25 + vector) -> top 50 candidates
        Stage 2: Semantic reranking -> top 20
        Stage 3: LLM-based relevance filtering -> final top-k (score > threshold)

        Args:
            query: Clinical query text.
            index_name: Azure AI Search index to query.
            filters: Optional OData filter expression.
            top_k: Maximum number of final results to return.
            rerank: Whether to apply Stage 2 semantic reranking.
            relevance_threshold: Minimum relevance score (0.0-1.0) for Stage 3.

        Returns:
            List of result dicts ordered by relevance, each containing:
                id, content, score, reranker_score, relevance_score, metadata.

        Raises:
            RetrieverError: If any stage of the pipeline fails.
        """
        pipeline_start = time.monotonic()

        logger.info(
            "Starting retrieval pipeline",
            extra={
                "query_length": len(query),
                "index_name": index_name,
                "top_k": top_k,
                "rerank": rerank,
                "relevance_threshold": relevance_threshold,
            },
        )

        try:
            # Generate query embedding
            query_vector = await self._embedding_service.generate_embedding(query)

            # Stage 1: Hybrid search -> top 50
            stage1_start = time.monotonic()
            stage1_results = await self._stage1_hybrid_search(
                query=query,
                query_vector=query_vector,
                index_name=index_name,
                filters=filters,
                top=50,
            )
            stage1_elapsed = (time.monotonic() - stage1_start) * 1000

            logger.info(
                "Stage 1 (hybrid search) complete",
                extra={
                    "results_count": len(stage1_results),
                    "elapsed_ms": round(stage1_elapsed, 2),
                },
            )

            if not stage1_results:
                logger.warning(
                    "No results from Stage 1 hybrid search",
                    extra={"query": query[:200], "index_name": index_name},
                )
                return []

            # Stage 2: Semantic reranking -> top 20
            if rerank:
                stage2_start = time.monotonic()
                stage2_results = await self._stage2_semantic_rerank(
                    results=stage1_results, top=20
                )
                stage2_elapsed = (time.monotonic() - stage2_start) * 1000

                logger.info(
                    "Stage 2 (semantic rerank) complete",
                    extra={
                        "input_count": len(stage1_results),
                        "output_count": len(stage2_results),
                        "elapsed_ms": round(stage2_elapsed, 2),
                    },
                )
            else:
                stage2_results = stage1_results[:20]

            if not stage2_results:
                return []

            # Stage 3: LLM relevance filtering -> final top-k
            stage3_start = time.monotonic()
            stage3_results = await self._stage3_llm_relevance_filter(
                query=query,
                results=stage2_results,
                threshold=relevance_threshold,
            )
            stage3_elapsed = (time.monotonic() - stage3_start) * 1000

            # Limit to top_k
            final_results = stage3_results[:top_k]

            pipeline_elapsed = (time.monotonic() - pipeline_start) * 1000

            logger.info(
                "Retrieval pipeline complete",
                extra={
                    "stage1_count": len(stage1_results),
                    "stage2_count": len(stage2_results),
                    "stage3_count": len(stage3_results),
                    "final_count": len(final_results),
                    "stage3_elapsed_ms": round(stage3_elapsed, 2),
                    "total_elapsed_ms": round(pipeline_elapsed, 2),
                },
            )

            return final_results

        except RetrieverError:
            raise
        except AzureServiceError:
            raise
        except Exception as exc:
            logger.error(
                "Retrieval pipeline failed",
                extra={"error": str(exc), "index_name": index_name},
            )
            raise RetrieverError(
                message=f"Retrieval pipeline failed: {exc}",
                retriever_name="HybridRetriever",
                index_name=index_name,
            ) from exc

    async def _stage1_hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        index_name: str,
        filters: str | None,
        top: int = 50,
    ) -> list[dict]:
        """Stage 1: Hybrid search via Azure AI Search.

        Combines BM25 keyword search with vector similarity search using
        Reciprocal Rank Fusion. Returns the top candidates for further
        refinement.

        Args:
            query: Clinical query text for BM25 component.
            query_vector: Embedding vector for vector search component.
            index_name: Azure AI Search index name.
            filters: Optional OData filter expression.
            top: Maximum number of candidates to return.

        Returns:
            List of result dicts from hybrid search.

        Raises:
            RetrieverError: If the search operation fails.
        """
        try:
            results = await self._search_client.hybrid_search(
                index_name=index_name,
                query=query,
                query_vector=query_vector,
                filters=filters,
                top=top,
            )
            return results

        except RetrieverError:
            raise
        except Exception as exc:
            raise RetrieverError(
                message=f"Stage 1 hybrid search failed: {exc}",
                retriever_name="HybridRetriever",
                index_name=index_name,
            ) from exc

    async def _stage2_semantic_rerank(
        self, results: list[dict], top: int = 20
    ) -> list[dict]:
        """Stage 2: Semantic reranking using Azure AI Search L2 reranker scores.

        The reranker scores are already included in the search results from
        Azure AI Search's built-in semantic ranking. This stage sorts by
        the reranker score and takes the top N results.

        Args:
            results: Results from Stage 1, each containing a "reranker_score" field.
            top: Maximum number of reranked results to return.

        Returns:
            Top results sorted by semantic reranker score (descending).
        """
        # Filter results that have a valid reranker score
        scored_results = []
        unscored_results = []

        for result in results:
            reranker_score = result.get("reranker_score", 0.0)
            if reranker_score and reranker_score > 0.0:
                scored_results.append(result)
            else:
                unscored_results.append(result)

        # Sort scored results by reranker score descending
        scored_results.sort(key=lambda r: r.get("reranker_score", 0.0), reverse=True)

        # Combine: scored results first, then unscored (sorted by hybrid score)
        unscored_results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        combined = scored_results + unscored_results

        reranked = combined[:top]

        logger.debug(
            "Semantic rerank applied",
            extra={
                "input_count": len(results),
                "scored_count": len(scored_results),
                "unscored_count": len(unscored_results),
                "output_count": len(reranked),
                "top_score": reranked[0].get("reranker_score", 0.0) if reranked else 0.0,
            },
        )

        return reranked

    async def _stage3_llm_relevance_filter(
        self,
        query: str,
        results: list[dict],
        threshold: float = 0.7,
    ) -> list[dict]:
        """Stage 3: LLM-based relevance scoring and filtering.

        Uses GPT-4o-mini to evaluate each result's relevance to the clinical
        query. Results scoring below the threshold are filtered out. Remaining
        results are sorted by relevance score descending.

        Args:
            query: Original clinical query.
            results: Results from Stage 2.
            threshold: Minimum relevance score to keep (0.0-1.0).

        Returns:
            Filtered and re-sorted results with added "relevance_score" field.

        Raises:
            RetrieverError: If the LLM scoring call fails.
        """
        if not results:
            return []

        # Build document summaries for the LLM
        document_texts: list[str] = []
        for i, result in enumerate(results):
            content = result.get("content", "")
            # Truncate long content to fit context window
            truncated = content[:1500] if len(content) > 1500 else content
            document_texts.append(f"[Document {i}]\n{truncated}\n")

        documents_block = "\n".join(document_texts)

        user_message = _RELEVANCE_SCORING_USER_TEMPLATE.format(
            query=query,
            documents=documents_block,
        )

        try:
            response = await self._openai_client.chat.completions.create(
                model=self._mini_deployment,
                messages=[
                    {"role": "system", "content": _RELEVANCE_SCORING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            response_text = response.choices[0].message.content or "[]"

            # Parse scores from LLM response
            scores = self._parse_relevance_scores(response_text, len(results))

        except Exception as exc:
            logger.warning(
                "Stage 3 LLM relevance scoring failed, falling back to Stage 2 ordering",
                extra={"error": str(exc)},
            )
            # On LLM failure, keep all results with a default score
            for result in results:
                result["relevance_score"] = result.get("reranker_score", 0.5)
            return results

        # Apply scores to results
        scored_results: list[dict] = []
        for i, result in enumerate(results):
            score = scores.get(i, 0.0)
            result["relevance_score"] = score
            if score >= threshold:
                scored_results.append(result)

        # Sort by relevance score descending
        scored_results.sort(key=lambda r: r.get("relevance_score", 0.0), reverse=True)

        logger.info(
            "Stage 3 LLM relevance filtering complete",
            extra={
                "input_count": len(results),
                "above_threshold": len(scored_results),
                "threshold": threshold,
                "top_score": scored_results[0].get("relevance_score", 0.0)
                if scored_results
                else 0.0,
            },
        )

        return scored_results

    def _parse_relevance_scores(
        self, response_text: str, expected_count: int
    ) -> dict[int, float]:
        """Parse relevance scores from the LLM JSON response.

        Handles various response formats gracefully, including nested JSON
        and malformed outputs.

        Args:
            response_text: Raw LLM response text.
            expected_count: Expected number of score entries.

        Returns:
            Dict mapping document index to relevance score.
        """
        scores: dict[int, float] = {}

        try:
            parsed = json.loads(response_text)

            # Handle both direct array and wrapped object formats
            if isinstance(parsed, list):
                score_list = parsed
            elif isinstance(parsed, dict):
                # Try common wrapper keys
                score_list = (
                    parsed.get("scores")
                    or parsed.get("results")
                    or parsed.get("documents")
                    or []
                )
                if not score_list and len(parsed) == 1:
                    # Single key wrapper
                    score_list = next(iter(parsed.values()))
                    if not isinstance(score_list, list):
                        score_list = []
            else:
                score_list = []

            for entry in score_list:
                if isinstance(entry, dict):
                    idx = entry.get("index")
                    score = entry.get("score", 0.0)
                    if idx is not None and isinstance(idx, int) and 0 <= idx < expected_count:
                        scores[idx] = max(0.0, min(1.0, float(score)))

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "Failed to parse LLM relevance scores",
                extra={
                    "error": str(exc),
                    "response_preview": response_text[:500],
                },
            )

        return scores

    # ── Convenience methods for specific indexes ─────────────────────────────

    async def retrieve_patient_records(
        self,
        query: str,
        patient_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve from the patient records index.

        Args:
            query: Clinical query about a patient.
            patient_id: Optional patient ID to filter results.
            top_k: Maximum number of results.

        Returns:
            List of relevant patient record results.

        Raises:
            RetrieverError: If retrieval fails.
        """
        filters = None
        if patient_id is not None:
            filters = f"patient_id eq '{patient_id}'"

        logger.info(
            "Retrieving patient records",
            extra={
                "patient_id": patient_id,
                "query_length": len(query),
                "top_k": top_k,
            },
        )

        return await self.retrieve(
            query=query,
            index_name=INDEX_PATIENT_RECORDS,
            filters=filters,
            top_k=top_k,
        )

    async def retrieve_protocols(
        self,
        query: str,
        specialty: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve from the treatment protocols index.

        Args:
            query: Clinical query about treatments or guidelines.
            specialty: Optional medical specialty to filter by.
            top_k: Maximum number of results.

        Returns:
            List of relevant treatment protocol results.

        Raises:
            RetrieverError: If retrieval fails.
        """
        filters = None
        if specialty is not None:
            filters = f"specialty eq '{specialty}'"

        logger.info(
            "Retrieving treatment protocols",
            extra={
                "specialty": specialty,
                "query_length": len(query),
                "top_k": top_k,
            },
        )

        return await self.retrieve(
            query=query,
            index_name=INDEX_TREATMENT_PROTOCOLS,
            filters=filters,
            top_k=top_k,
        )

    async def retrieve_literature(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve from the medical literature cache index.

        Args:
            query: Clinical or research query.
            top_k: Maximum number of results.

        Returns:
            List of relevant medical literature results.

        Raises:
            RetrieverError: If retrieval fails.
        """
        logger.info(
            "Retrieving medical literature",
            extra={
                "query_length": len(query),
                "top_k": top_k,
            },
        )

        return await self.retrieve(
            query=query,
            index_name=INDEX_MEDICAL_LITERATURE,
            top_k=top_k,
        )
