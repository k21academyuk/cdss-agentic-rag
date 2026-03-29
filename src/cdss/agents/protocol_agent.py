"""Protocol Agent for the Clinical Decision Support System.

Retrieves matching clinical guidelines and treatment protocols from
Azure AI Search and Azure Blob Storage, then extracts and ranks
relevant recommendations for the clinical query.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from cdss.agents.base import BaseAgent
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.clients.search_client import AzureSearchClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AgentError
from cdss.core.models import AgentTask, ProtocolMatch


class ProtocolAgent(BaseAgent):
    """Retrieves matching clinical guidelines and treatment protocols.

    Tools:
    - azure_ai_search(index="protocols")
    - blob_storage_read(container="guidelines")

    Model: GPT-4o-mini
    Output: list[ProtocolMatch]
    """

    # Maximum protocols to retrieve from search
    MAX_SEARCH_RESULTS = 20
    # Maximum protocols to return after scoring
    MAX_PROTOCOL_MATCHES = 10

    def __init__(
        self,
        search_client: AzureSearchClient | None = None,
        blob_client: Any | None = None,
        openai_client: AzureOpenAIClient | None = None,
        retriever: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the ProtocolAgent.

        Args:
            search_client: Azure AI Search client for protocol search.
            blob_client: Azure Blob Storage client for full guideline documents.
            openai_client: Azure OpenAI client for recommendation extraction.
            retriever: Optional RAG retriever for enhanced document retrieval.
            settings: Application settings. Defaults to environment-loaded settings.
        """
        super().__init__(name="protocol_agent", model="gpt-4o-mini")
        self._settings = settings or get_settings()
        self._search_client = search_client or AzureSearchClient(settings=self._settings)
        self._blob_client = blob_client
        self._openai_client = openai_client or AzureOpenAIClient(settings=self._settings)
        self._retriever = retriever

    async def _execute(self, task: AgentTask) -> dict:
        """Find matching treatment protocols.

        1. Search treatment-protocols index in AI Search
        2. Extract matching guidelines with evidence grades
        3. Summarize relevant recommendations
        4. Return list of ProtocolMatch

        Args:
            task: Agent task with payload containing ``query``, optional
                  ``conditions`` (list of condition display names), and
                  optional ``specialty``.

        Returns:
            Dictionary containing ``summary``, ``sources_retrieved``, and
            ``protocol_matches`` (list of serialized ProtocolMatch).
        """
        query = task.payload.get("query", "")
        conditions = task.payload.get("conditions", [])
        specialty = task.payload.get("specialty")

        if not query:
            raise AgentError(
                message="query is required in task payload",
                agent_name=self.name,
            )

        self.logger.info(
            "Searching for treatment protocols",
            extra={
                "query": query[:100],
                "conditions_count": len(conditions),
                "specialty": specialty,
            },
        )

        # Step 1: Search protocols index with optional specialty filter
        search_results = await self._search_protocols(query, specialty)

        if not search_results:
            self.logger.info(
                "No protocol matches found",
                extra={"query": query[:100], "specialty": specialty},
            )
            return {
                "summary": "No matching clinical guidelines or treatment protocols were found.",
                "sources_retrieved": 0,
                "protocol_matches": [],
            }

        # Step 2: Parse results into preliminary ProtocolMatch objects
        preliminary_matches = self._parse_search_results(search_results)

        # Step 3: Use GPT-4o-mini to extract specific recommendations relevant to query
        enriched_matches = await self._extract_recommendations(
            query=query,
            conditions=conditions,
            matches=preliminary_matches,
            search_results=search_results,
        )

        # Step 4: Sort by applicability score and return top matches
        enriched_matches.sort(
            key=lambda m: m.get("applicability_score", 0.0),
            reverse=True,
        )
        top_matches = enriched_matches[:self.MAX_PROTOCOL_MATCHES]

        # Build ProtocolMatch objects
        protocol_matches: list[ProtocolMatch] = []
        for match_data in top_matches:
            try:
                evidence_grade = match_data.get("evidence_grade", "expert_opinion")
                # Validate evidence grade
                valid_grades = {"A", "B", "C", "D", "expert_opinion"}
                if evidence_grade not in valid_grades:
                    evidence_grade = "expert_opinion"

                protocol_match = ProtocolMatch(
                    guideline_name=match_data.get("guideline_name", "Unknown Guideline"),
                    version=match_data.get("version", "Unknown"),
                    recommendation=match_data.get("recommendation", ""),
                    evidence_grade=evidence_grade,
                    specialty=match_data.get("specialty", specialty or "general"),
                    contraindications=match_data.get("contraindications", []),
                    last_updated=match_data.get("last_updated", date.today()),
                )
                protocol_matches.append(protocol_match)
            except Exception as exc:
                self.logger.debug(
                    "Skipping malformed protocol match",
                    extra={"error": str(exc), "data": str(match_data)[:200]},
                )

        # Build summary
        summary = self._build_summary(query, protocol_matches)

        self.logger.info(
            "Protocol search completed",
            extra={
                "total_search_results": len(search_results),
                "protocol_matches": len(protocol_matches),
            },
        )

        return {
            "summary": summary,
            "sources_retrieved": len(search_results),
            "protocol_matches": [pm.model_dump() for pm in protocol_matches],
        }

    async def _search_protocols(
        self, query: str, specialty: str | None
    ) -> list[dict]:
        """Search the treatment-protocols index in Azure AI Search.

        Args:
            query: Clinical query about treatments or protocols.
            specialty: Optional medical specialty filter (e.g., "cardiology").

        Returns:
            List of search result dictionaries.
        """
        try:
            results = await self._search_client.search_treatment_protocols(
                query=query,
                specialty=specialty,
                top=self.MAX_SEARCH_RESULTS,
            )
            self.logger.debug(
                "Protocol search completed",
                extra={
                    "results_count": len(results),
                    "specialty_filter": specialty,
                },
            )
            return results
        except Exception as exc:
            self.logger.error(
                "Protocol search failed",
                extra={"error": str(exc), "specialty": specialty},
            )
            return []

    def _parse_search_results(self, search_results: list[dict]) -> list[dict]:
        """Parse raw search results into preliminary protocol match dictionaries.

        Args:
            search_results: Raw search results from Azure AI Search.

        Returns:
            List of partially populated protocol match dictionaries.
        """
        matches: list[dict] = []

        for result in search_results:
            metadata = result.get("metadata", {})
            content = result.get("content", "")

            match_data = {
                "protocol_id": result.get("id", ""),
                "guideline_name": metadata.get(
                    "guideline_name",
                    metadata.get("title", "Unknown Guideline"),
                ),
                "version": metadata.get("version", metadata.get("year", "Unknown")),
                "specialty": metadata.get("specialty", "general"),
                "evidence_grade": metadata.get("evidence_grade", "expert_opinion"),
                "content": content,
                "score": result.get("score", 0.0),
                "reranker_score": result.get("reranker_score", 0.0),
                "source": metadata.get("source", metadata.get("organization", "")),
                "last_updated": metadata.get("last_updated", str(date.today())),
                "url": metadata.get("url", ""),
                "contraindications": metadata.get("contraindications", []),
            }
            matches.append(match_data)

        return matches

    async def _extract_recommendations(
        self,
        query: str,
        conditions: list[str],
        matches: list[dict],
        search_results: list[dict],
    ) -> list[dict]:
        """Use GPT-4o-mini to extract specific recommendations from protocol content.

        Sends the protocol content to the LLM along with the clinical query
        and conditions to extract the most relevant recommendation text,
        assess applicability, and identify contraindications.

        Args:
            query: The original clinical query.
            conditions: Patient conditions for context.
            matches: Preliminary match dictionaries with content.
            search_results: Raw search results for additional context.

        Returns:
            List of enriched match dictionaries with ``recommendation``,
            ``applicability_score``, and ``contraindications``.
        """
        if not matches:
            return []

        # Build protocol summaries for LLM
        protocol_texts: list[str] = []
        for i, match in enumerate(matches[:self.MAX_PROTOCOL_MATCHES]):
            content = match.get("content", "")[:1500]
            text = (
                f"[Protocol {i + 1}] {match.get('guideline_name', 'Unknown')}\n"
                f"Version: {match.get('version', 'Unknown')}\n"
                f"Evidence Grade: {match.get('evidence_grade', 'Unknown')}\n"
                f"Specialty: {match.get('specialty', 'Unknown')}\n"
                f"Content:\n{content}"
            )
            protocol_texts.append(text)

        protocols_text = "\n\n---\n\n".join(protocol_texts)

        conditions_text = ", ".join(conditions) if conditions else "Not specified"

        system_prompt = (
            "You are a clinical guideline specialist for a Clinical Decision Support System. "
            "Given a clinical query, patient conditions, and protocol documents, extract "
            "the most relevant recommendations from each protocol.\n\n"
            "For each protocol, respond with a JSON object containing a \"protocols\" array "
            "where each element has:\n"
            "- \"index\": the protocol number (1-based)\n"
            "- \"recommendation\": the specific recommendation text relevant to the query "
            "(2-4 sentences, directly quoting or paraphrasing the guideline)\n"
            "- \"evidence_grade\": one of \"A\", \"B\", \"C\", \"D\", or \"expert_opinion\"\n"
            "- \"applicability_score\": float 0.0-1.0 indicating how applicable this "
            "protocol is to the specific clinical query and patient conditions\n"
            "- \"contraindications\": list of contraindications mentioned in the protocol "
            "that may be relevant\n\n"
            "Only include protocols with applicability_score > 0.3. "
            "Be precise and cite guideline language where possible."
        )

        user_prompt = (
            f"Clinical Query: {query}\n"
            f"Patient Conditions: {conditions_text}\n\n"
            f"Protocol Documents:\n\n{protocols_text}"
        )

        try:
            response = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.get("content", "{}"))
            extracted_protocols = result.get("protocols", [])

            # Merge extracted recommendations back into match data
            enriched: list[dict] = []
            for extracted in extracted_protocols:
                idx = extracted.get("index", 0) - 1  # Convert to 0-based
                if 0 <= idx < len(matches):
                    match = matches[idx].copy()
                    match["recommendation"] = extracted.get("recommendation", match.get("content", "")[:500])
                    match["evidence_grade"] = extracted.get("evidence_grade", match.get("evidence_grade", "expert_opinion"))
                    match["applicability_score"] = max(0.0, min(1.0, float(extracted.get("applicability_score", 0.5))))
                    extracted_contras = extracted.get("contraindications", [])
                    if extracted_contras:
                        match["contraindications"] = extracted_contras
                    enriched.append(match)

            # Add any matches that weren't extracted (with lower scores)
            extracted_indices = {(e.get("index", 0) - 1) for e in extracted_protocols}
            for i, match in enumerate(matches):
                if i not in extracted_indices:
                    match = match.copy()
                    match.setdefault("recommendation", match.get("content", "")[:500])
                    match.setdefault("applicability_score", 0.3)
                    enriched.append(match)

            self.logger.debug(
                "Recommendations extracted",
                extra={
                    "total_matches": len(matches),
                    "extracted_count": len(extracted_protocols),
                    "enriched_count": len(enriched),
                },
            )
            return enriched

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse recommendation extraction JSON",
                extra={"error": str(exc)},
            )
            # Fallback: return matches with content as recommendation
            for match in matches:
                match.setdefault("recommendation", match.get("content", "")[:500])
                match.setdefault("applicability_score", 0.5)
            return matches

        except Exception as exc:
            self.logger.warning(
                "Recommendation extraction failed",
                extra={"error": str(exc)},
            )
            for match in matches:
                match.setdefault("recommendation", match.get("content", "")[:500])
                match.setdefault("applicability_score", 0.5)
            return matches

    def _build_summary(
        self, query: str, protocol_matches: list[ProtocolMatch]
    ) -> str:
        """Build a human-readable summary of protocol matches.

        Args:
            query: The original clinical query.
            protocol_matches: List of matched ProtocolMatch objects.

        Returns:
            A narrative summary of the protocol findings.
        """
        if not protocol_matches:
            return "No matching clinical guidelines or treatment protocols were found."

        parts: list[str] = [
            f"Found {len(protocol_matches)} relevant clinical guideline(s):"
        ]

        for i, match in enumerate(protocol_matches, 1):
            grade_display = (
                f"Grade {match.evidence_grade}"
                if match.evidence_grade != "expert_opinion"
                else "Expert Opinion"
            )
            parts.append(
                f"\n{i}. {match.guideline_name} ({match.version})\n"
                f"   Evidence: {grade_display} | Specialty: {match.specialty}\n"
                f"   Recommendation: {match.recommendation[:200]}{'...' if len(match.recommendation) > 200 else ''}"
            )

            if match.contraindications:
                contras = ", ".join(match.contraindications[:3])
                parts.append(f"   Contraindications: {contras}")

        return "\n".join(parts)
