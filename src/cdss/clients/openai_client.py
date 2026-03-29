"""Azure OpenAI client wrapper for chat completions and embeddings."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncAzureOpenAI, APIStatusError, RateLimitError

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError
from cdss.core.logging import get_logger

logger = get_logger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 30.0

# Deployment name mapping
DEPLOYMENT_MAP = {
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
}

EMBEDDING_MODEL = "text-embedding-3-large"

# Maximum batch size for embedding requests
EMBEDDING_BATCH_SIZE = 16


class AzureOpenAIClient:
    """Wrapper for Azure OpenAI with GPT-4o, GPT-4o-mini, and embeddings.

    Provides chat completion, embedding generation, query classification,
    and document relevance evaluation with built-in retry logic for
    rate limit handling.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Azure OpenAI async client.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self._settings = settings or get_settings()

        self._client = AsyncAzureOpenAI(
            azure_endpoint=self._settings.azure_openai_endpoint,
            api_key=self._settings.azure_openai_api_key,
            api_version=self._settings.azure_openai_api_version,
        )

        self._max_retries = DEFAULT_MAX_RETRIES
        self._retry_base_delay = DEFAULT_RETRY_BASE_DELAY
        self._retry_max_delay = DEFAULT_RETRY_MAX_DELAY

        logger.info(
            "AzureOpenAIClient initialized",
            extra={
                "endpoint": self._settings.azure_openai_endpoint,
                "api_version": self._settings.azure_openai_api_version,
            }
        )

    async def _retry_with_backoff(self, coro_factory, operation_name: str) -> Any:
        """Execute an async operation with exponential backoff on rate limits.

        Args:
            coro_factory: A callable that returns a new coroutine on each invocation.
            operation_name: Human-readable name of the operation for logging.

        Returns:
            The result of the successful coroutine execution.

        Raises:
            AzureServiceError: If all retry attempts are exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return await coro_factory()

            except RateLimitError as exc:
                last_exception = exc
                retry_after = float(
                    exc.response.headers.get("Retry-After", self._retry_base_delay)
                    if exc.response
                    else self._retry_base_delay
                )
                delay = min(retry_after * (2 ** (attempt - 1)), self._retry_max_delay)

                logger.warning(
                    "Rate limit hit, retrying",
                    operation=operation_name,
                    attempt=attempt,
                    max_retries=self._max_retries,
                    retry_after_seconds=delay,
                )
                await asyncio.sleep(delay)

            except APIStatusError as exc:
                logger.error(
                    "Azure OpenAI API error",
                    operation=operation_name,
                    status_code=exc.status_code,
                    error=str(exc),
                )
                raise AzureServiceError(
                    f"{operation_name} failed with status {exc.status_code}: {exc}"
                ) from exc

            except Exception as exc:
                logger.error(
                    "Unexpected error in Azure OpenAI call",
                    operation=operation_name,
                    error=str(exc),
                )
                raise AzureServiceError(
                    f"{operation_name} failed unexpectedly: {exc}"
                ) from exc

        raise AzureServiceError(
            f"{operation_name} failed after {self._max_retries} retries: "
            f"{last_exception}"
        )

    def _resolve_deployment(self, model: str) -> str:
        """Resolve a model name to an Azure deployment name.

        Args:
            model: Model identifier (e.g., "gpt-4o", "gpt-4o-mini").

        Returns:
            The Azure deployment name.

        Raises:
            AzureServiceError: If the model name is not recognized.
        """
        deployment = DEPLOYMENT_MAP.get(model)
        if deployment is None:
            raise AzureServiceError(
                f"Unknown model: '{model}'. Valid models: {list(DEPLOYMENT_MAP.keys())}"
            )
        return deployment

    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        tools: list[dict] | None = None,
    ) -> dict:
        """Get chat completion from GPT-4o or GPT-4o-mini.

        Supports structured JSON output via response_format and
        function/tool calling via the tools parameter.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model to use ("gpt-4o" or "gpt-4o-mini").
            temperature: Sampling temperature (0.0-2.0). Lower is more deterministic.
            max_tokens: Maximum tokens in the response.
            response_format: Optional format specification, e.g. {"type": "json_object"}.
            tools: Optional list of tool/function definitions for tool calling.

        Returns:
            Dict with keys:
                - content (str): The assistant's response text.
                - tool_calls (list | None): Tool call objects if tools were invoked.
                - usage (dict): Token usage with prompt_tokens, completion_tokens, total_tokens.

        Raises:
            AzureServiceError: If the API call fails after retries.
        """
        deployment = self._resolve_deployment(model)

        kwargs: dict[str, Any] = {
            "model": deployment,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        logger.debug(
            "Requesting chat completion",
            model=model,
            deployment=deployment,
            message_count=len(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            has_tools=tools is not None,
            has_response_format=response_format is not None,
        )

        async def _make_request():
            return await self._client.chat.completions.create(**kwargs)

        response = await self._retry_with_backoff(
            _make_request, f"chat_completion({model})"
        )

        choice = response.choices[0]
        message = choice.message

        tool_calls_data = None
        if message.tool_calls:
            tool_calls_data = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        result = {
            "content": message.content or "",
            "tool_calls": tool_calls_data,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

        logger.info(
            "Chat completion received",
            model=model,
            prompt_tokens=result["usage"]["prompt_tokens"],
            completion_tokens=result["usage"]["completion_tokens"],
            has_tool_calls=tool_calls_data is not None,
            finish_reason=choice.finish_reason,
        )

        return result

    async def generate_embedding(
        self, text: str, dimensions: int = 3072
    ) -> list[float]:
        """Generate an embedding using text-embedding-3-large.

        Args:
            text: Input text to embed.
            dimensions: Desired embedding dimensions (default 3072 for
                        text-embedding-3-large).

        Returns:
            Embedding vector as a list of floats.

        Raises:
            AzureServiceError: If embedding generation fails after retries.
        """
        if not text.strip():
            logger.warning("Empty text provided for embedding, returning zero vector")
            return [0.0] * dimensions

        logger.debug(
            "Generating embedding",
            text_length=len(text),
            dimensions=dimensions,
        )

        async def _make_request():
            return await self._client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=dimensions,
            )

        response = await self._retry_with_backoff(
            _make_request, "generate_embedding"
        )

        embedding = response.data[0].embedding

        logger.debug(
            "Embedding generated",
            text_length=len(text),
            embedding_dimensions=len(embedding),
            usage_tokens=response.usage.total_tokens,
        )

        return embedding

    async def generate_embeddings_batch(
        self, texts: list[str], dimensions: int = 3072
    ) -> list[list[float]]:
        """Batch embedding generation for multiple texts.

        Handles batching to stay within API limits and processes
        batches concurrently where possible.

        Args:
            texts: List of input texts to embed.
            dimensions: Desired embedding dimensions.

        Returns:
            List of embedding vectors, one per input text, in the same order.

        Raises:
            AzureServiceError: If embedding generation fails after retries.
        """
        if not texts:
            return []

        logger.debug(
            "Generating batch embeddings",
            batch_size=len(texts),
            dimensions=dimensions,
        )

        all_embeddings: list[list[float]] = [[] for _ in texts]

        for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(texts))
            batch_texts = texts[batch_start:batch_end]

            # Replace empty strings with a single space to avoid API errors
            sanitized_texts = [t if t.strip() else " " for t in batch_texts]

            async def _make_request(inputs=sanitized_texts):
                return await self._client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=inputs,
                    dimensions=dimensions,
                )

            response = await self._retry_with_backoff(
                _make_request, f"generate_embeddings_batch(offset={batch_start})"
            )

            # Sort by index to preserve order
            sorted_data = sorted(response.data, key=lambda d: d.index)
            for i, datum in enumerate(sorted_data):
                original_text = batch_texts[i]
                if not original_text.strip():
                    all_embeddings[batch_start + i] = [0.0] * dimensions
                else:
                    all_embeddings[batch_start + i] = datum.embedding

            logger.debug(
                "Batch chunk embedded",
                batch_start=batch_start,
                batch_size=len(batch_texts),
                usage_tokens=response.usage.total_tokens,
            )

        logger.info(
            "Batch embeddings completed",
            total_texts=len(texts),
            dimensions=dimensions,
        )

        return all_embeddings

    async def classify_query(self, query: str) -> dict:
        """Use GPT-4o-mini to classify a clinical query type and extract entities.

        Analyzes the query to determine whether it relates to diagnosis,
        treatment, drug interaction checking, or general clinical questions,
        and extracts relevant medical entities.

        Args:
            query: The clinical query text to classify.

        Returns:
            Dict with keys:
                - query_type (str): One of "diagnosis", "treatment", "drug_check", "general".
                - entities (list[str]): Extracted medical entities (conditions, drugs, etc.).
                - required_agents (list[str]): Agent types needed to handle this query.

        Raises:
            AzureServiceError: If classification fails.
        """
        system_prompt = (
            "You are a clinical query classifier for a Clinical Decision Support System. "
            "Analyze the user's clinical query and classify it.\n\n"
            "Respond with a JSON object containing:\n"
            "- \"query_type\": one of \"diagnosis\", \"treatment\", \"drug_check\", or \"general\"\n"
            "- \"entities\": a list of extracted medical entities "
            "(conditions, symptoms, drugs, procedures)\n"
            "- \"required_agents\": a list of agent types needed from: "
            "[\"patient_history\", \"treatment_protocol\", \"drug_interaction\", "
            "\"medical_literature\", \"clinical_reasoning\"]\n\n"
            "Classification rules:\n"
            "- \"diagnosis\": queries about identifying conditions from symptoms or test results\n"
            "- \"treatment\": queries about treatment plans, protocols, or procedures\n"
            "- \"drug_check\": queries about drug interactions, contraindications, or dosing\n"
            "- \"general\": general clinical questions or queries spanning multiple categories"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        logger.debug("Classifying clinical query", query_length=len(query))

        result = await self.chat_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        try:
            classification = json.loads(result["content"])
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse classification response",
                content=result["content"],
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to parse query classification response: {exc}"
            ) from exc

        # Validate and normalize the classification
        valid_query_types = {"diagnosis", "treatment", "drug_check", "general"}
        query_type = classification.get("query_type", "general")
        if query_type not in valid_query_types:
            logger.warning(
                "Unknown query type returned, defaulting to 'general'",
                returned_type=query_type,
            )
            query_type = "general"

        normalized = {
            "query_type": query_type,
            "entities": classification.get("entities", []),
            "required_agents": classification.get("required_agents", []),
        }

        logger.info(
            "Query classified",
            query_type=normalized["query_type"],
            entity_count=len(normalized["entities"]),
            required_agents=normalized["required_agents"],
        )

        return normalized

    async def evaluate_relevance(self, query: str, document: str) -> float:
        """Use GPT-4o-mini to score how relevant a document is to a query.

        Args:
            query: The clinical query.
            document: The document text to evaluate.

        Returns:
            Relevance score between 0.0 (not relevant) and 1.0 (highly relevant).

        Raises:
            AzureServiceError: If relevance evaluation fails.
        """
        system_prompt = (
            "You are a clinical document relevance evaluator. "
            "Given a clinical query and a document, rate the relevance of the "
            "document to answering the query on a scale from 0.0 to 1.0.\n\n"
            "Scoring criteria:\n"
            "- 0.0-0.2: Not relevant, different topic entirely\n"
            "- 0.2-0.4: Tangentially related but not directly useful\n"
            "- 0.4-0.6: Somewhat relevant, contains related information\n"
            "- 0.6-0.8: Relevant, directly addresses part of the query\n"
            "- 0.8-1.0: Highly relevant, directly and thoroughly addresses the query\n\n"
            "Respond with a JSON object containing a single key \"relevance_score\" "
            "with a float value between 0.0 and 1.0."
        )

        user_content = (
            f"Clinical Query: {query}\n\n"
            f"Document:\n{document[:4000]}"  # Truncate to prevent token overflow
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        logger.debug(
            "Evaluating document relevance",
            query_length=len(query),
            document_length=len(document),
        )

        result = await self.chat_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=64,
            response_format={"type": "json_object"},
        )

        try:
            parsed = json.loads(result["content"])
            score = float(parsed.get("relevance_score", 0.0))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error(
                "Failed to parse relevance score",
                content=result["content"],
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to parse relevance evaluation response: {exc}"
            ) from exc

        # Clamp score to valid range
        score = max(0.0, min(1.0, score))

        logger.debug(
            "Document relevance evaluated",
            relevance_score=score,
        )

        return score
