"""RxNorm REST API client for drug name normalization and interaction lookup.

Provides async access to the NLM RxNorm REST API for resolving drug names
to RxCUIs (RxNorm Concept Unique Identifiers), retrieving drug properties,
checking drug-drug interactions, and performing fuzzy name matching.

See: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import CDSSError, RateLimitError

logger = logging.getLogger(__name__)


class RxNormClientError(CDSSError):
    """Raised when an RxNorm API call fails."""

    def __init__(
        self,
        message: str,
        endpoint: str = "",
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        super().__init__(message, details)


class RxNormClient:
    """Client for NLM RxNorm API -- drug name normalization and interaction checks.

    RxNorm is the standard nomenclature for clinical drugs in the US.
    This client resolves brand/generic drug names to standardized identifiers,
    retrieves drug metadata, and checks for drug-drug interactions.
    """

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 0.5

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            timeout=15.0,
            base_url=self.BASE_URL,
            headers={
                "User-Agent": "CDSS-Agentic-RAG/1.0",
                "Accept": "application/json",
            },
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _request_with_retry(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Execute a GET request with exponential-backoff retry.

        RxNorm is a free public API without strict rate limits, but network
        issues and transient 5xx errors are handled with retries.

        Args:
            url: Relative URL path (e.g., ``/rxcui.json``).
            params: Query string parameters.

        Returns:
            The successful ``httpx.Response``.

        Raises:
            RxNormClientError: On non-retryable HTTP errors or after all retries.
            RateLimitError: If rate limits are encountered and persist.
        """
        last_exception: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                response = await self._client.get(url, params=params)
                elapsed = time.monotonic() - start_time

                logger.debug(
                    "RxNorm GET %s completed in %.3fs (status=%d)",
                    url,
                    elapsed,
                    response.status_code,
                )

                # Handle rate limiting (unlikely for RxNorm but defensive)
                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get(
                            "Retry-After",
                            self.BASE_BACKOFF_SECONDS * (2 ** attempt),
                        )
                    )
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            "RxNorm rate limit hit (attempt %d/%d). Retrying in %.2fs.",
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        message=f"RxNorm rate limit exceeded after {self.MAX_RETRIES + 1} attempts",
                        retry_after=retry_after,
                        details={"endpoint": url},
                    )

                # Handle server errors with retry
                if response.status_code >= 500:
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                        logger.warning(
                            "RxNorm server error %d (attempt %d/%d). Retrying in %.2fs.",
                            response.status_code,
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "RxNorm GET %s failed with HTTP %d after %.3fs: %s",
                    url,
                    exc.response.status_code,
                    elapsed,
                    str(exc),
                )
                raise RxNormClientError(
                    message=f"RxNorm API returned HTTP {exc.response.status_code}",
                    endpoint=url,
                    status_code=exc.response.status_code,
                    details={"response_text": exc.response.text[:500]},
                ) from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - start_time
                logger.warning(
                    "RxNorm GET %s request error (attempt %d/%d) after %.3fs: %s",
                    url,
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                    elapsed,
                    str(exc),
                )
                last_exception = exc
                if attempt < self.MAX_RETRIES:
                    backoff = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue

        raise RxNormClientError(
            message=f"RxNorm request failed after {self.MAX_RETRIES + 1} attempts: {last_exception}",
            endpoint=url,
            details={"last_error": str(last_exception)},
        )

    # ── Public API ───────────────────────────────────────────────────────────

    async def normalize_drug_name(self, drug_name: str) -> dict[str, str] | None:
        """Normalize a drug name to its RxNorm Concept Unique Identifier (RxCUI).

        Performs an exact-match lookup against the RxNorm vocabulary. For fuzzy
        matching on misspelled or partial names, use ``approximate_match()``.

        Args:
            drug_name: Drug name to normalize (brand or generic).

        Returns:
            Dictionary with ``rxcui``, ``name``, and ``tty`` (term type) if
            found, or ``None`` if no match exists.

        Raises:
            RxNormClientError: If the API call fails.
        """
        params = {"name": drug_name}

        logger.info("RxNorm normalize: drug=%r", drug_name)

        response = await self._request_with_retry("/rxcui.json", params)
        data = response.json()

        id_group = data.get("idGroup", {})
        rxnorm_ids = id_group.get("rxnormId")

        if not rxnorm_ids:
            logger.info("RxNorm normalize: no exact match for drug=%r", drug_name)
            return None

        # Take the first (best) match
        rxcui = rxnorm_ids[0]

        # Fetch full properties to get the canonical name and term type
        properties = await self._get_rxcui_properties(rxcui)

        result = {
            "rxcui": rxcui,
            "name": properties.get("name", drug_name),
            "tty": properties.get("tty", ""),
        }

        logger.info(
            "RxNorm normalize: %r -> RxCUI %s (%s, tty=%s)",
            drug_name,
            result["rxcui"],
            result["name"],
            result["tty"],
        )
        return result

    async def _get_rxcui_properties(self, rxcui: str) -> dict[str, str]:
        """Fetch basic properties for an RxCUI (internal helper).

        Args:
            rxcui: RxNorm Concept Unique Identifier.

        Returns:
            Dictionary of property key-value pairs.
        """
        response = await self._request_with_retry(f"/rxcui/{rxcui}/properties.json")
        data = response.json()
        properties = data.get("properties", {})
        return properties

    async def get_drug_info(self, rxcui: str) -> dict[str, Any]:
        """Get comprehensive drug properties by RxCUI.

        Retrieves the full property set for a given RxCUI, including name,
        synonym, term type, source, and suppression status.

        Args:
            rxcui: RxNorm Concept Unique Identifier.

        Returns:
            Dictionary containing drug properties:
                - ``rxcui``: The RxCUI.
                - ``name``: Canonical drug name.
                - ``synonym``: Synonym if available.
                - ``tty``: Term type (e.g., SBD, SCD, IN, BN).
                - ``language``: Language code.
                - ``suppress``: Suppression status.
                - ``source``: Source vocabulary.

        Raises:
            RxNormClientError: If the API call fails or RxCUI is not found.
        """
        logger.info("RxNorm drug info: rxcui=%s", rxcui)

        response = await self._request_with_retry(f"/rxcui/{rxcui}/properties.json")
        data = response.json()

        properties = data.get("properties")
        if not properties:
            logger.warning("RxNorm drug info: no properties for rxcui=%s", rxcui)
            raise RxNormClientError(
                message=f"No properties found for RxCUI {rxcui}",
                endpoint=f"/rxcui/{rxcui}/properties.json",
                details={"rxcui": rxcui},
            )

        result: dict[str, Any] = {
            "rxcui": properties.get("rxcui", rxcui),
            "name": properties.get("name", ""),
            "synonym": properties.get("synonym", ""),
            "tty": properties.get("tty", ""),
            "language": properties.get("language", ""),
            "suppress": properties.get("suppress", ""),
            "source": properties.get("source", ""),
        }

        logger.info(
            "RxNorm drug info: rxcui=%s -> %s (tty=%s)",
            rxcui,
            result["name"],
            result["tty"],
        )
        return result

    async def find_interactions(self, rxcui_list: list[str]) -> list[dict[str, Any]]:
        """Find drug-drug interactions for a list of RxCUIs.

        Uses the RxNorm Interaction API to check for known interactions
        between multiple drugs simultaneously.

        Args:
            rxcui_list: List of RxCUI strings to check for pairwise interactions.
                Must contain at least 2 RxCUIs.

        Returns:
            List of interaction dictionaries, each containing:
                - ``drug_a``: Dict with ``rxcui`` and ``name`` of first drug.
                - ``drug_b``: Dict with ``rxcui`` and ``name`` of second drug.
                - ``severity``: Interaction severity (e.g., "high", "low").
                - ``description``: Human-readable description.
                - ``source``: Data source (e.g., DrugBank, ONCHigh).

        Raises:
            RxNormClientError: If the API call fails.
        """
        if len(rxcui_list) < 2:
            logger.info("RxNorm interactions: fewer than 2 RxCUIs, no interactions possible")
            return []

        rxcuis_param = "+".join(rxcui_list)
        params = {"rxcuis": rxcuis_param}

        logger.info(
            "RxNorm interactions: checking %d drugs (rxcuis=%s)",
            len(rxcui_list),
            rxcuis_param,
        )

        response = await self._request_with_retry("/interaction/list.json", params)
        data = response.json()

        interactions: list[dict[str, Any]] = []

        full_interaction_type_group = data.get("fullInteractionTypeGroup", [])
        for group in full_interaction_type_group:
            source_name = group.get("sourceName", "")
            full_interaction_types = group.get("fullInteractionType", [])

            for interaction_type in full_interaction_types:
                min_concept_item = interaction_type.get("minConceptItem", {})
                interaction_pairs = interaction_type.get("interactionPair", [])

                for pair in interaction_pairs:
                    # Extract the two interacting drugs
                    interaction_concepts = pair.get("interactionConcept", [])
                    if len(interaction_concepts) < 2:
                        continue

                    drug_a_info = interaction_concepts[0].get("minConceptItem", {})
                    drug_b_info = interaction_concepts[1].get("minConceptItem", {})

                    severity = pair.get("severity", "N/A")
                    description = pair.get("description", "")

                    interactions.append({
                        "drug_a": {
                            "rxcui": drug_a_info.get("rxcui", ""),
                            "name": drug_a_info.get("name", ""),
                        },
                        "drug_b": {
                            "rxcui": drug_b_info.get("rxcui", ""),
                            "name": drug_b_info.get("name", ""),
                        },
                        "severity": severity,
                        "description": description,
                        "source": source_name,
                    })

        logger.info(
            "RxNorm interactions: found %d interactions for %d drugs",
            len(interactions),
            len(rxcui_list),
        )
        return interactions

    async def get_related_drugs(
        self,
        rxcui: str,
        relation: str = "tradename",
    ) -> list[dict[str, str]]:
        """Get related drugs by relationship type (brand names, generics, ingredients).

        Args:
            rxcui: Source RxCUI.
            relation: Term type filter for related concepts. Common values:
                - ``"BN"`` -- Brand Name
                - ``"IN"`` -- Ingredient
                - ``"SBD"`` -- Semantic Branded Drug
                - ``"SCD"`` -- Semantic Clinical Drug
                - ``"SBDG"`` -- Semantic Branded Drug Group
                - ``"SCDG"`` -- Semantic Clinical Drug Group

        Returns:
            List of related drug dictionaries, each with:
                - ``rxcui``: RxCUI of the related drug.
                - ``name``: Name of the related drug.
                - ``tty``: Term type.

        Raises:
            RxNormClientError: If the API call fails.
        """
        params = {"tty": relation}

        logger.info(
            "RxNorm related drugs: rxcui=%s, relation=%s", rxcui, relation
        )

        response = await self._request_with_retry(
            f"/rxcui/{rxcui}/related.json", params
        )
        data = response.json()

        related: list[dict[str, str]] = []
        related_group = data.get("relatedGroup", {})
        concept_groups = related_group.get("conceptGroup", [])

        for group in concept_groups:
            tty = group.get("tty", "")
            concept_properties = group.get("conceptProperties", [])
            for prop in concept_properties:
                related.append({
                    "rxcui": prop.get("rxcui", ""),
                    "name": prop.get("name", ""),
                    "tty": tty,
                })

        logger.info(
            "RxNorm related drugs: found %d related concepts for rxcui=%s",
            len(related),
            rxcui,
        )
        return related

    async def approximate_match(self, drug_name: str) -> list[dict[str, Any]]:
        """Fuzzy-match a drug name when exact normalization fails.

        Uses the RxNorm approximate term API which employs spelling
        correction and string similarity to find candidate matches.

        Args:
            drug_name: Drug name string (may be misspelled or partial).

        Returns:
            List of candidate match dictionaries, each containing:
                - ``rxcui``: Candidate RxCUI.
                - ``name``: Canonical name for the candidate.
                - ``score``: Match confidence score (higher is better).
                - ``tty``: Term type.

        Raises:
            RxNormClientError: If the API call fails.
        """
        params = {"term": drug_name}

        logger.info("RxNorm approximate match: term=%r", drug_name)

        response = await self._request_with_retry("/approximateTerm.json", params)
        data = response.json()

        candidates: list[dict[str, Any]] = []
        approx_group = data.get("approximateGroup", {})
        candidate_list = approx_group.get("candidate", [])

        for candidate in candidate_list:
            rxcui = candidate.get("rxcui", "")
            score = candidate.get("score", "0")
            name = candidate.get("name", "")

            # The approximate API may not return name directly; fetch it
            if not name and rxcui:
                try:
                    props = await self._get_rxcui_properties(rxcui)
                    name = props.get("name", "")
                except RxNormClientError:
                    logger.warning(
                        "RxNorm approximate match: failed to fetch name for rxcui=%s",
                        rxcui,
                    )

            candidates.append({
                "rxcui": rxcui,
                "name": name,
                "score": int(score) if str(score).isdigit() else 0,
                "tty": candidate.get("tty", ""),
            })

        # Sort by score descending
        candidates.sort(key=lambda c: c["score"], reverse=True)

        logger.info(
            "RxNorm approximate match: found %d candidates for term=%r",
            len(candidates),
            drug_name,
        )
        return candidates

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._client.aclose()
        logger.debug("RxNormClient closed")

    async def __aenter__(self) -> RxNormClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
