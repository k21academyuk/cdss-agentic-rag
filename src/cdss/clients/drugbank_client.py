"""DrugBank Clinical API client for drug-drug interaction checking.

Provides async access to the DrugBank REST API for comprehensive drug
interaction data, drug search, and detailed pharmacological information.
Requires an API key for authentication.

See: https://docs.drugbank.com/v1/
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


class DrugBankClientError(CDSSError):
    """Raised when a DrugBank API call fails."""

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


class DrugBankClient:
    """Client for DrugBank Clinical API -- drug-drug interaction checking.

    DrugBank provides curated pharmacological data including drug-drug
    interactions with severity classifications, clinical significance, and
    management recommendations. All endpoints require Bearer token authentication.
    """

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 1.0

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key: str = self.settings.drugbank_api_key
        self.base_url: str = self.settings.drugbank_base_url or "https://api.drugbank.com/v1"
        self._client = httpx.AsyncClient(
            timeout=30.0,
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "CDSS-Agentic-RAG/1.0",
            },
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with exponential-backoff retry.

        Handles rate limits (HTTP 429), server errors (5xx), and transient
        network failures with configurable retries and backoff.

        Args:
            method: HTTP method (``GET`` or ``POST``).
            url: Relative URL path (e.g., ``/ddi``).
            params: Query string parameters.
            json_body: JSON request body for POST requests.

        Returns:
            The successful ``httpx.Response``.

        Raises:
            DrugBankClientError: On non-retryable HTTP errors or auth failures.
            RateLimitError: When rate limits persist after all retries.
        """
        last_exception: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                if method.upper() == "GET":
                    response = await self._client.get(url, params=params)
                elif method.upper() == "POST":
                    response = await self._client.post(
                        url, params=params, json=json_body
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                elapsed = time.monotonic() - start_time
                logger.debug(
                    "DrugBank %s %s completed in %.3fs (status=%d)",
                    method.upper(),
                    url,
                    elapsed,
                    response.status_code,
                )

                # Handle authentication failures (no retry)
                if response.status_code in (401, 403):
                    logger.error(
                        "DrugBank authentication failed for %s %s (status=%d)",
                        method.upper(),
                        url,
                        response.status_code,
                    )
                    raise DrugBankClientError(
                        message=f"DrugBank authentication failed (HTTP {response.status_code}). "
                                "Verify your API key is valid.",
                        endpoint=url,
                        status_code=response.status_code,
                        details={"response_text": response.text[:500]},
                    )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get(
                            "Retry-After",
                            self.BASE_BACKOFF_SECONDS * (2 ** attempt),
                        )
                    )
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            "DrugBank rate limit hit (attempt %d/%d). Retrying in %.2fs.",
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        message=f"DrugBank rate limit exceeded after {self.MAX_RETRIES + 1} attempts",
                        retry_after=retry_after,
                        details={"endpoint": url},
                    )

                # Handle server errors with retry
                if response.status_code >= 500:
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                        logger.warning(
                            "DrugBank server error %d (attempt %d/%d). Retrying in %.2fs.",
                            response.status_code,
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue

                # Handle 404 gracefully (return response for caller to handle)
                if response.status_code == 404:
                    return response

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "DrugBank %s %s failed with HTTP %d after %.3fs: %s",
                    method.upper(),
                    url,
                    exc.response.status_code,
                    elapsed,
                    str(exc),
                )
                raise DrugBankClientError(
                    message=f"DrugBank API returned HTTP {exc.response.status_code}",
                    endpoint=url,
                    status_code=exc.response.status_code,
                    details={"response_text": exc.response.text[:500]},
                ) from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - start_time
                logger.warning(
                    "DrugBank %s %s request error (attempt %d/%d) after %.3fs: %s",
                    method.upper(),
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

        raise DrugBankClientError(
            message=f"DrugBank request failed after {self.MAX_RETRIES + 1} attempts: {last_exception}",
            endpoint=url,
            details={"last_error": str(last_exception)},
        )

    # ── Public API ───────────────────────────────────────────────────────────

    async def check_interactions(
        self, drug_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Check drug-drug interactions for a list of drug identifiers.

        Submits a set of drug identifiers to the DrugBank DDI endpoint and
        returns all pairwise interactions found, with severity classifications
        and clinical management guidance.

        Args:
            drug_ids: List of DrugBank drug identifiers (e.g., ``["DB00945", "DB00316"]``)
                or drug names. Must contain at least 2 entries.

        Returns:
            List of interaction dictionaries, each containing:
                - ``drug_a``: Name or ID of the first drug.
                - ``drug_b``: Name or ID of the second drug.
                - ``severity``: Severity level (``"minor"``, ``"moderate"``, ``"major"``).
                - ``description``: Detailed interaction description.
                - ``evidence_level``: Strength of supporting evidence.
                - ``clinical_significance``: Clinical significance summary.
                - ``management``: Recommended clinical management.
                - ``extended_description``: Extended pharmacological explanation.

        Raises:
            DrugBankClientError: If the API call fails or fewer than 2 drugs given.
        """
        if len(drug_ids) < 2:
            logger.warning("DrugBank interactions: fewer than 2 drug IDs provided")
            return []

        logger.info(
            "DrugBank check interactions: %d drugs (%s)",
            len(drug_ids),
            ", ".join(drug_ids[:5]) + ("..." if len(drug_ids) > 5 else ""),
        )

        # Build the request body for the DDI endpoint
        request_body = {"drugbank_ids": drug_ids}

        response = await self._request_with_retry(
            "POST", "/ddi", json_body=request_body
        )

        if response.status_code == 404:
            logger.info("DrugBank interactions: no interactions found for provided drugs")
            return []

        data = response.json()

        # Parse the response -- DrugBank may return a list or wrapped object
        raw_interactions: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_interactions = data
        elif isinstance(data, dict):
            raw_interactions = data.get("interactions", data.get("results", []))

        interactions: list[dict[str, Any]] = []
        for raw in raw_interactions:
            interaction = {
                "drug_a": raw.get("subject_drug", raw.get("drug_a", {
                    "drugbank_id": raw.get("subject_drugbank_id", ""),
                    "name": raw.get("subject_drug_name", ""),
                })),
                "drug_b": raw.get("affected_drug", raw.get("drug_b", {
                    "drugbank_id": raw.get("affected_drugbank_id", ""),
                    "name": raw.get("affected_drug_name", ""),
                })),
                "severity": raw.get("severity", raw.get("risk_rating", "unknown")),
                "description": raw.get("description", ""),
                "evidence_level": raw.get("evidence_level", raw.get("evidence", "")),
                "clinical_significance": raw.get(
                    "clinical_significance",
                    raw.get("summary", ""),
                ),
                "management": raw.get("management", raw.get("action", "")),
                "extended_description": raw.get("extended_description", ""),
            }

            # Normalize drug references to dicts if they are strings
            if isinstance(interaction["drug_a"], str):
                interaction["drug_a"] = {"name": interaction["drug_a"]}
            if isinstance(interaction["drug_b"], str):
                interaction["drug_b"] = {"name": interaction["drug_b"]}

            interactions.append(interaction)

        logger.info(
            "DrugBank check interactions: found %d interactions",
            len(interactions),
        )
        return interactions

    async def search_drug(self, query: str) -> list[dict[str, Any]]:
        """Search DrugBank for a drug by name or identifier.

        Performs a text search across drug names, synonyms, and identifiers.

        Args:
            query: Search query string (drug name, brand name, or identifier).

        Returns:
            List of matching drug dictionaries, each containing:
                - ``drugbank_id``: DrugBank accession number (e.g., ``"DB00945"``).
                - ``name``: Primary drug name.
                - ``cas_number``: CAS registry number.
                - ``drug_type``: Type (small molecule, biotech, etc.).
                - ``description``: Brief drug description.
                - ``synonyms``: List of alternate names.

        Raises:
            DrugBankClientError: If the API call fails.
        """
        params = {"q": query}

        logger.info("DrugBank search: query=%r", query)

        response = await self._request_with_retry("GET", "/drugs", params=params)

        if response.status_code == 404:
            logger.info("DrugBank search: no results for query=%r", query)
            return []

        data = response.json()

        # Response may be a list of drugs or wrapped in a container
        raw_drugs: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_drugs = data
        elif isinstance(data, dict):
            raw_drugs = data.get("drugs", data.get("results", []))

        drugs: list[dict[str, Any]] = []
        for raw in raw_drugs:
            drugs.append({
                "drugbank_id": raw.get("drugbank_id", raw.get("id", "")),
                "name": raw.get("name", ""),
                "cas_number": raw.get("cas_number", ""),
                "drug_type": raw.get("type", raw.get("drug_type", "")),
                "description": raw.get("description", "")[:500],
                "synonyms": raw.get("synonyms", []),
            })

        logger.info(
            "DrugBank search: found %d results for query=%r",
            len(drugs),
            query,
        )
        return drugs

    async def get_drug_details(self, drugbank_id: str) -> dict[str, Any]:
        """Get detailed pharmacological information for a specific drug.

        Retrieves comprehensive drug data including pharmacology,
        pharmacokinetics, classification, and identifiers.

        Args:
            drugbank_id: DrugBank accession number (e.g., ``"DB00945"``).

        Returns:
            Dictionary containing:
                - ``drugbank_id``: DrugBank accession number.
                - ``name``: Primary drug name.
                - ``description``: Detailed drug description.
                - ``drug_type``: Small molecule, biotech, etc.
                - ``cas_number``: CAS registry number.
                - ``state``: Physical state (solid, liquid, gas).
                - ``indication``: Approved indications.
                - ``pharmacodynamics``: Pharmacodynamic description.
                - ``mechanism_of_action``: Mechanism of action.
                - ``toxicity``: Toxicity information.
                - ``metabolism``: Metabolism pathways.
                - ``absorption``: Absorption characteristics.
                - ``half_life``: Elimination half-life.
                - ``protein_binding``: Plasma protein binding percentage.
                - ``route_of_elimination``: Elimination route.
                - ``volume_of_distribution``: Volume of distribution.
                - ``clearance``: Drug clearance rate.
                - ``classification``: Drug classification info.
                - ``categories``: List of drug categories.
                - ``atc_codes``: ATC classification codes.
                - ``external_ids``: External identifier cross-references.

        Raises:
            DrugBankClientError: If the drug is not found or the API call fails.
        """
        logger.info("DrugBank drug details: drugbank_id=%s", drugbank_id)

        response = await self._request_with_retry("GET", f"/drugs/{drugbank_id}")

        if response.status_code == 404:
            raise DrugBankClientError(
                message=f"Drug not found: {drugbank_id}",
                endpoint=f"/drugs/{drugbank_id}",
                status_code=404,
                details={"drugbank_id": drugbank_id},
            )

        raw = response.json()

        details: dict[str, Any] = {
            "drugbank_id": raw.get("drugbank_id", raw.get("id", drugbank_id)),
            "name": raw.get("name", ""),
            "description": raw.get("description", ""),
            "drug_type": raw.get("type", raw.get("drug_type", "")),
            "cas_number": raw.get("cas_number", ""),
            "state": raw.get("state", ""),
            "indication": raw.get("indication", ""),
            "pharmacodynamics": raw.get("pharmacodynamics", ""),
            "mechanism_of_action": raw.get("mechanism_of_action", ""),
            "toxicity": raw.get("toxicity", ""),
            "metabolism": raw.get("metabolism", ""),
            "absorption": raw.get("absorption", ""),
            "half_life": raw.get("half_life", ""),
            "protein_binding": raw.get("protein_binding", ""),
            "route_of_elimination": raw.get("route_of_elimination", ""),
            "volume_of_distribution": raw.get("volume_of_distribution", ""),
            "clearance": raw.get("clearance", ""),
            "classification": raw.get("classification", {}),
            "categories": raw.get("categories", []),
            "atc_codes": raw.get("atc_codes", []),
            "external_ids": raw.get("external_identifiers", raw.get("external_ids", [])),
        }

        logger.info(
            "DrugBank drug details: retrieved %s (%s)",
            details["name"] or drugbank_id,
            details["drug_type"] or "unknown type",
        )
        return details

    async def get_drug_interactions_for_drug(
        self, drugbank_id: str
    ) -> list[dict[str, Any]]:
        """Get all known drug-drug interactions for a specific drug.

        Retrieves the complete interaction profile for a single drug,
        useful for building a patient's interaction risk summary.

        Args:
            drugbank_id: DrugBank accession number (e.g., ``"DB00945"``).

        Returns:
            List of interaction dictionaries, each containing:
                - ``interacting_drug``: Dict with ``drugbank_id`` and ``name``.
                - ``severity``: Severity level (``"minor"``, ``"moderate"``, ``"major"``).
                - ``description``: Interaction description.
                - ``evidence_level``: Evidence strength.
                - ``clinical_significance``: Clinical significance summary.
                - ``management``: Recommended management actions.

        Raises:
            DrugBankClientError: If the drug is not found or the API call fails.
        """
        logger.info(
            "DrugBank drug interactions: drugbank_id=%s", drugbank_id
        )

        response = await self._request_with_retry(
            "GET", f"/drugs/{drugbank_id}/interactions"
        )

        if response.status_code == 404:
            logger.info(
                "DrugBank drug interactions: no interactions found for %s",
                drugbank_id,
            )
            return []

        data = response.json()

        # Parse response
        raw_interactions: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_interactions = data
        elif isinstance(data, dict):
            raw_interactions = data.get("interactions", data.get("results", []))

        interactions: list[dict[str, Any]] = []
        for raw in raw_interactions:
            # The interacting drug could be in various field names
            interacting_drug_data = raw.get("affected_drug", raw.get("drug", {}))
            if isinstance(interacting_drug_data, str):
                interacting_drug_data = {"name": interacting_drug_data}

            interacting_drug: dict[str, str] = {
                "drugbank_id": interacting_drug_data.get(
                    "drugbank_id", interacting_drug_data.get("id", "")
                ),
                "name": interacting_drug_data.get("name", ""),
            }

            interactions.append({
                "interacting_drug": interacting_drug,
                "severity": raw.get("severity", raw.get("risk_rating", "unknown")),
                "description": raw.get("description", ""),
                "evidence_level": raw.get("evidence_level", raw.get("evidence", "")),
                "clinical_significance": raw.get(
                    "clinical_significance", raw.get("summary", "")
                ),
                "management": raw.get("management", raw.get("action", "")),
            })

        logger.info(
            "DrugBank drug interactions: found %d interactions for %s",
            len(interactions),
            drugbank_id,
        )
        return interactions

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._client.aclose()
        logger.debug("DrugBankClient closed")

    async def __aenter__(self) -> DrugBankClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
