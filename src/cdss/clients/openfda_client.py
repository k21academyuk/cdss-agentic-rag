"""OpenFDA Drug API client for adverse events, labeling, and recalls.

Provides async access to the OpenFDA public API for drug-related safety
data including adverse event reports (FAERS), structured product labeling
(SPL), and enforcement/recall reports.

See: https://open.fda.gov/apis/drug/
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


class OpenFDAClientError(CDSSError):
    """Raised when an OpenFDA API call fails."""

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


class OpenFDAClient:
    """Client for OpenFDA Drug API -- adverse events, labeling, recalls.

    Wraps the public OpenFDA REST API with typed methods, retry logic,
    and structured response parsing for integration into the CDSS pipeline.
    """

    BASE_URL = "https://api.fda.gov"

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 1.0

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            timeout=30.0,
            base_url=self.BASE_URL,
            headers={"User-Agent": "CDSS-Agentic-RAG/1.0"},
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _request_with_retry(
        self,
        url: str,
        params: dict[str, str],
    ) -> httpx.Response:
        """Execute a GET request with exponential-backoff retry on rate limits.

        OpenFDA enforces rate limits (240 requests/minute for keyless access).
        This method retries on HTTP 429 responses.

        Args:
            url: Relative URL path (e.g., ``/drug/event.json``).
            params: Query string parameters.

        Returns:
            The successful ``httpx.Response``.

        Raises:
            OpenFDAClientError: On non-retryable HTTP errors.
            RateLimitError: When rate limits persist after all retries.
        """
        last_exception: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                response = await self._client.get(url, params=params)
                elapsed = time.monotonic() - start_time

                logger.debug(
                    "OpenFDA GET %s completed in %.3fs (status=%d)",
                    url,
                    elapsed,
                    response.status_code,
                )

                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get(
                            "Retry-After",
                            self.BASE_BACKOFF_SECONDS * (2 ** attempt),
                        )
                    )
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            "OpenFDA rate limit hit (attempt %d/%d). Retrying in %.2fs.",
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        message=f"OpenFDA rate limit exceeded after {self.MAX_RETRIES + 1} attempts",
                        retry_after=retry_after,
                        details={"endpoint": url},
                    )

                # OpenFDA returns 404 when no results match (not a real error)
                if response.status_code == 404:
                    return response

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "OpenFDA GET %s failed with HTTP %d after %.3fs: %s",
                    url,
                    exc.response.status_code,
                    elapsed,
                    str(exc),
                )
                raise OpenFDAClientError(
                    message=f"OpenFDA API returned HTTP {exc.response.status_code}",
                    endpoint=url,
                    status_code=exc.response.status_code,
                    details={"response_text": exc.response.text[:500]},
                ) from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - start_time
                logger.warning(
                    "OpenFDA GET %s request error (attempt %d/%d) after %.3fs: %s",
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

        raise OpenFDAClientError(
            message=f"OpenFDA request failed after {self.MAX_RETRIES + 1} attempts: {last_exception}",
            endpoint=url,
            details={"last_error": str(last_exception)},
        )

    @staticmethod
    def _escape_search_term(term: str) -> str:
        """Escape special characters in an OpenFDA search term.

        OpenFDA uses Lucene query syntax; certain characters must be quoted.

        Args:
            term: Raw search term.

        Returns:
            Escaped/quoted term safe for use in ``search`` parameters.
        """
        # Wrap the term in double quotes for exact matching
        # and escape any internal double quotes
        escaped = term.replace('"', '\\"')
        return f'"{escaped}"'

    # ── Public API ───────────────────────────────────────────────────────────

    async def search_adverse_events(
        self,
        drug_name: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search drug adverse event reports from the FDA FAERS database.

        Queries the ``/drug/event.json`` endpoint filtering by drug generic
        name and returns structured adverse event data.

        Args:
            drug_name: Generic drug name to search for.
            limit: Maximum number of event reports to return (max 100).

        Returns:
            List of adverse event dictionaries, each containing:
                - ``safety_report_id``: Unique report identifier.
                - ``reactions``: List of reported reaction terms.
                - ``outcomes``: List of patient outcomes.
                - ``seriousness``: Dict of seriousness flags.
                - ``drug_characterization``: Role of the drug in the event.
                - ``receive_date``: Date the report was received.

        Raises:
            OpenFDAClientError: If the API call fails.
        """
        escaped_name = self._escape_search_term(drug_name)
        params = {
            "search": f"patient.drug.openfda.generic_name:{escaped_name}",
            "limit": str(min(limit, 100)),
        }

        logger.info("OpenFDA adverse events search: drug=%r, limit=%d", drug_name, limit)

        response = await self._request_with_retry("/drug/event.json", params)

        if response.status_code == 404:
            logger.info("OpenFDA adverse events: no results for drug=%r", drug_name)
            return []

        data = response.json()
        results = data.get("results", [])

        events: list[dict[str, Any]] = []
        for result in results:
            # Extract reactions
            reactions: list[str] = []
            for reaction in result.get("patient", {}).get("reaction", []):
                term = reaction.get("reactionmeddrapt", "")
                if term:
                    reactions.append(term)

            # Extract outcomes
            outcomes: list[str] = []
            for reaction in result.get("patient", {}).get("reaction", []):
                outcome = reaction.get("reactionoutcome", "")
                if outcome:
                    outcome_map = {
                        "1": "Recovered/Resolved",
                        "2": "Recovering/Resolving",
                        "3": "Not Recovered/Not Resolved",
                        "4": "Recovered/Resolved with Sequelae",
                        "5": "Fatal",
                        "6": "Unknown",
                    }
                    outcomes.append(outcome_map.get(str(outcome), str(outcome)))

            # Extract seriousness flags
            seriousness = {
                "is_serious": result.get("serious", "0") == "1",
                "death": result.get("seriousnessdeath", "0") == "1",
                "hospitalization": result.get("seriousnesshospitalization", "0") == "1",
                "life_threatening": result.get("seriousnesslifethreatening", "0") == "1",
                "disability": result.get("seriousnessdisabling", "0") == "1",
                "congenital_anomaly": result.get("seriousnesscongenitalanomali", "0") == "1",
                "other_medically_important": result.get("seriousnessother", "0") == "1",
            }

            # Extract drug characterization for the target drug
            drug_characterization = ""
            for drug in result.get("patient", {}).get("drug", []):
                openfda = drug.get("openfda", {})
                generic_names = [n.lower() for n in openfda.get("generic_name", [])]
                if drug_name.lower() in generic_names:
                    char_code = drug.get("drugcharacterization", "")
                    char_map = {
                        "1": "Suspect",
                        "2": "Concomitant",
                        "3": "Interacting",
                    }
                    drug_characterization = char_map.get(str(char_code), str(char_code))
                    break

            events.append({
                "safety_report_id": result.get("safetyreportid", ""),
                "reactions": reactions,
                "outcomes": list(set(outcomes)),  # deduplicate
                "seriousness": seriousness,
                "drug_characterization": drug_characterization,
                "receive_date": result.get("receivedate", ""),
            })

        logger.info(
            "OpenFDA adverse events: found %d reports for drug=%r",
            len(events),
            drug_name,
        )
        return events

    async def get_drug_label(self, drug_name: str) -> dict[str, Any] | None:
        """Retrieve structured product labeling (SPL) for a drug.

        Fetches the most recent drug label from the ``/drug/label.json``
        endpoint, extracting clinically relevant sections.

        Args:
            drug_name: Generic drug name.

        Returns:
            Dictionary containing labeling sections:
                - ``brand_name``: Brand name(s).
                - ``generic_name``: Confirmed generic name.
                - ``warnings``: Warnings and precautions text.
                - ``contraindications``: Contraindications text.
                - ``drug_interactions``: Drug interaction information.
                - ``adverse_reactions``: Adverse reactions section.
                - ``indications_and_usage``: Approved indications.
                - ``dosage_and_administration``: Dosing information.
                - ``boxed_warning``: Boxed warning if present.
                - ``pregnancy``: Pregnancy information if available.
            Returns ``None`` if no label is found.

        Raises:
            OpenFDAClientError: If the API call fails.
        """
        escaped_name = self._escape_search_term(drug_name)
        params = {
            "search": f"openfda.generic_name:{escaped_name}",
            "limit": "1",
        }

        logger.info("OpenFDA drug label: drug=%r", drug_name)

        response = await self._request_with_retry("/drug/label.json", params)

        if response.status_code == 404:
            logger.info("OpenFDA drug label: no label found for drug=%r", drug_name)
            return None

        data = response.json()
        results = data.get("results", [])

        if not results:
            return None

        label = results[0]
        openfda = label.get("openfda", {})

        def _join_text(sections: list[str] | str | None) -> str:
            """Safely join label sections that may be a list of strings."""
            if sections is None:
                return ""
            if isinstance(sections, list):
                return "\n\n".join(sections)
            return str(sections)

        parsed_label: dict[str, Any] = {
            "brand_name": ", ".join(openfda.get("brand_name", [])),
            "generic_name": ", ".join(openfda.get("generic_name", [])),
            "warnings": _join_text(label.get("warnings")),
            "contraindications": _join_text(label.get("contraindications")),
            "drug_interactions": _join_text(label.get("drug_interactions")),
            "adverse_reactions": _join_text(label.get("adverse_reactions")),
            "indications_and_usage": _join_text(label.get("indications_and_usage")),
            "dosage_and_administration": _join_text(label.get("dosage_and_administration")),
            "boxed_warning": _join_text(label.get("boxed_warning")),
            "pregnancy": _join_text(label.get("pregnancy")),
        }

        logger.info(
            "OpenFDA drug label: retrieved label for %s (%s)",
            parsed_label["generic_name"] or drug_name,
            parsed_label["brand_name"] or "no brand name",
        )
        return parsed_label

    async def search_drug_recalls(
        self,
        drug_name: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search drug recall and enforcement reports.

        Queries the ``/drug/enforcement.json`` endpoint for recall actions
        related to a specific drug.

        Args:
            drug_name: Generic drug name.
            limit: Maximum number of recall reports to return.

        Returns:
            List of recall dictionaries, each containing:
                - ``recall_number``: Unique recall event identifier.
                - ``reason_for_recall``: Reason the recall was initiated.
                - ``status``: Current status of the recall (Ongoing, Completed, etc.).
                - ``classification``: Severity class (Class I, II, or III).
                - ``product_description``: Description of the recalled product.
                - ``recall_initiation_date``: When the recall was initiated.
                - ``voluntary_mandated``: Whether voluntary or FDA-mandated.
                - ``distribution_pattern``: Geographic distribution.

        Raises:
            OpenFDAClientError: If the API call fails.
        """
        escaped_name = self._escape_search_term(drug_name)
        params = {
            "search": f"openfda.generic_name:{escaped_name}",
            "limit": str(min(limit, 100)),
        }

        logger.info("OpenFDA drug recalls: drug=%r, limit=%d", drug_name, limit)

        response = await self._request_with_retry("/drug/enforcement.json", params)

        if response.status_code == 404:
            logger.info("OpenFDA drug recalls: no recalls found for drug=%r", drug_name)
            return []

        data = response.json()
        results = data.get("results", [])

        recalls: list[dict[str, Any]] = []
        for result in results:
            recalls.append({
                "recall_number": result.get("recall_number", ""),
                "reason_for_recall": result.get("reason_for_recall", ""),
                "status": result.get("status", ""),
                "classification": result.get("classification", ""),
                "product_description": result.get("product_description", ""),
                "recall_initiation_date": result.get("recall_initiation_date", ""),
                "voluntary_mandated": result.get("voluntary_mandated", ""),
                "distribution_pattern": result.get("distribution_pattern", ""),
            })

        logger.info(
            "OpenFDA drug recalls: found %d recalls for drug=%r",
            len(recalls),
            drug_name,
        )
        return recalls

    async def get_adverse_event_counts(
        self,
        drug_name: str,
        reaction: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregated adverse event counts for a drug.

        Uses OpenFDA's ``count`` parameter for server-side aggregation of
        adverse event reaction terms.

        Args:
            drug_name: Generic drug name.
            reaction: Optional specific reaction to filter for. When omitted,
                returns the top reaction counts for the drug.

        Returns:
            Dictionary containing:
                - ``drug_name``: The queried drug.
                - ``total_reports``: Total number of matching reports.
                - ``reaction_counts``: List of ``{"term": str, "count": int}``
                    representing the most common reactions or the count for
                    a specific reaction.

        Raises:
            OpenFDAClientError: If the API call fails.
        """
        escaped_name = self._escape_search_term(drug_name)
        search_query = f"patient.drug.openfda.generic_name:{escaped_name}"

        if reaction:
            escaped_reaction = self._escape_search_term(reaction)
            search_query += f"+AND+patient.reaction.reactionmeddrapt:{escaped_reaction}"

        params = {
            "search": search_query,
            "count": "patient.reaction.reactionmeddrapt.exact",
        }

        logger.info(
            "OpenFDA adverse event counts: drug=%r, reaction=%r",
            drug_name,
            reaction,
        )

        response = await self._request_with_retry("/drug/event.json", params)

        if response.status_code == 404:
            logger.info(
                "OpenFDA adverse event counts: no data for drug=%r", drug_name
            )
            return {
                "drug_name": drug_name,
                "total_reports": 0,
                "reaction_counts": [],
            }

        data = response.json()
        results = data.get("results", [])

        reaction_counts: list[dict[str, Any]] = []
        total = 0
        for entry in results:
            term = entry.get("term", "")
            count = entry.get("count", 0)
            reaction_counts.append({"term": term, "count": count})
            total += count

        logger.info(
            "OpenFDA adverse event counts: %d unique reactions, %d total reports for drug=%r",
            len(reaction_counts),
            total,
            drug_name,
        )

        return {
            "drug_name": drug_name,
            "total_reports": total,
            "reaction_counts": reaction_counts,
        }

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._client.aclose()
        logger.debug("OpenFDAClient closed")

    async def __aenter__(self) -> OpenFDAClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
