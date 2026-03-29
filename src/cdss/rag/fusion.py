"""Cross-source context fusion for the Clinical Decision Support System.

Fuses retrieval results from multiple knowledge sources (patient records,
drug interactions, treatment protocols, medical literature) into a single
ordered context using weighted interleaving. Drug safety alerts are injected
as system-level constraints. The fused context is trimmed to fit within
the LLM context window and formatted into a structured synthesis prompt.
"""

from __future__ import annotations

import hashlib
from typing import Any

from cdss.core.exceptions import CDSSError
from cdss.core.logging import get_logger
from cdss.rag.chunker import MedicalDocumentChunker

logger = get_logger(__name__)

# Approximate characters per token for context window budget
_CHARS_PER_TOKEN = 4


class CrossSourceFusion:
    """Weighted cross-source fusion for multi-source RAG results.

    Fuses results from multiple retrieval sources using priority-based
    weighted interleaving. Patient-specific data always appears first.
    Drug safety alerts are injected as system-level constraints that
    the synthesis LLM must respect.

    Source weights (higher = more important):
        - patient_records: 1.0 (highest -- patient-specific data)
        - drug_interactions: 0.95 (critical -- safety-first)
        - treatment_protocols: 0.85 (high -- institutional guidelines)
        - medical_literature: 0.75 (important -- evidence base)
        - cached_pubmed: 0.70 (useful -- supplementary)
    """

    SOURCE_WEIGHTS: dict[str, float] = {
        "patient_records": 1.0,
        "drug_interactions": 0.95,
        "treatment_protocols": 0.85,
        "medical_literature": 0.75,
        "cached_pubmed": 0.70,
    }

    def __init__(self, max_context_tokens: int = 100_000) -> None:
        """Initialize the fusion engine.

        Args:
            max_context_tokens: Maximum number of tokens allowed in the
                fused context window. Results are trimmed to fit.
        """
        self.max_context_tokens = max_context_tokens
        self._max_context_chars = max_context_tokens * _CHARS_PER_TOKEN

        logger.info(
            "CrossSourceFusion initialized",
            extra={"max_context_tokens": max_context_tokens},
        )

    def fuse(self, source_results: dict[str, list[dict]]) -> list[dict]:
        """Fuse results from multiple sources with weighted interleaving.

        Patient data always appears first. Drug safety alerts are injected
        as system-level constraints. Results are deduplicated and trimmed
        to the context window budget.

        Args:
            source_results: Dict mapping source_type to a list of result dicts.
                Each result dict should contain at minimum: "id", "content",
                and optionally "score", "reranker_score", "relevance_score",
                "metadata".

        Returns:
            Ordered list of fused result dicts, each augmented with
            "source_type" and "fusion_rank" fields. Ordered by weighted
            importance with patient data first and drug safety alerts
            prominently placed.
        """
        if not source_results:
            logger.warning("No source results provided for fusion")
            return []

        total_results = sum(len(v) for v in source_results.values())
        logger.info(
            "Starting cross-source fusion",
            extra={
                "source_count": len(source_results),
                "total_results": total_results,
                "sources": list(source_results.keys()),
            },
        )

        # Tag each result with its source type
        for source_type, results in source_results.items():
            for result in results:
                result["source_type"] = source_type

        # Separate patient records and drug safety alerts (they get priority)
        patient_results = source_results.get("patient_records", [])
        drug_alerts = source_results.get("drug_interactions", [])

        # Remaining sources for weighted interleaving
        remaining_sources = {
            k: v
            for k, v in source_results.items()
            if k not in ("patient_records", "drug_interactions")
        }

        # Build fused list: patient data first, then drug alerts, then interleaved rest
        fused: list[dict] = []

        # Patient records always first
        for result in patient_results:
            result["fusion_priority"] = "patient_data"
            fused.append(result)

        # Drug safety alerts next (critical safety information)
        for result in drug_alerts:
            result["fusion_priority"] = "drug_safety"
            fused.append(result)

        # Weighted interleave remaining sources
        interleaved = self._weighted_interleave(remaining_sources)
        for result in interleaved:
            result["fusion_priority"] = "evidence"
            fused.append(result)

        # Deduplicate
        fused = self._deduplicate(fused)

        # Assign fusion rank
        for rank, result in enumerate(fused):
            result["fusion_rank"] = rank

        # Trim to context window
        fused = self._trim_to_context_window(fused)

        logger.info(
            "Cross-source fusion complete",
            extra={
                "input_total": total_results,
                "output_count": len(fused),
                "patient_records": len(patient_results),
                "drug_alerts": len(drug_alerts),
                "evidence_results": len(interleaved),
            },
        )

        return fused

    def _weighted_interleave(
        self, source_results: dict[str, list[dict]]
    ) -> list[dict]:
        """Interleave results from multiple sources based on weights.

        Uses a round-robin approach weighted by source importance. Higher
        weighted sources contribute more results per round.

        Args:
            source_results: Dict mapping source_type to result lists.

        Returns:
            Interleaved list of result dicts.
        """
        if not source_results:
            return []

        # Calculate normalized selection probabilities
        total_weight = sum(
            self.SOURCE_WEIGHTS.get(source, 0.5) for source in source_results
        )

        # Build per-source iterators with weights
        source_queues: list[tuple[str, float, list[dict]]] = []
        for source_type, results in source_results.items():
            if results:
                weight = self.SOURCE_WEIGHTS.get(source_type, 0.5)
                normalized_weight = weight / total_weight if total_weight > 0 else 1.0
                source_queues.append((source_type, normalized_weight, list(results)))

        if not source_queues:
            return []

        # Sort by weight descending so higher-priority sources go first
        source_queues.sort(key=lambda x: x[1], reverse=True)

        interleaved: list[dict] = []
        total_to_distribute = sum(len(q[2]) for q in source_queues)

        # Track fractional credits per source for fair interleaving
        credits: dict[str, float] = {q[0]: 0.0 for q in source_queues}

        rounds = 0
        max_rounds = total_to_distribute * 2  # Safety limit

        while total_to_distribute > 0 and rounds < max_rounds:
            rounds += 1
            progress_made = False

            for source_type, weight, queue in source_queues:
                if not queue:
                    continue

                # Accumulate credit
                credits[source_type] += weight

                # Take items while credit is available
                while credits[source_type] >= (1.0 / len(source_queues)) and queue:
                    item = queue.pop(0)
                    interleaved.append(item)
                    total_to_distribute -= 1
                    credits[source_type] -= 1.0 / len(source_queues)
                    progress_made = True

            if not progress_made:
                # Force progress by taking one from each non-empty source
                for source_type, weight, queue in source_queues:
                    if queue:
                        interleaved.append(queue.pop(0))
                        total_to_distribute -= 1
                        progress_made = True
                        break

            if not progress_made:
                break

        # Drain any remaining items
        for _, _, queue in source_queues:
            interleaved.extend(queue)

        return interleaved

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        """Remove duplicate results based on content similarity.

        Uses content hashing for exact duplicates and a simple character-level
        overlap check for near-duplicates. Preserves the first occurrence
        (higher priority due to ordering).

        Args:
            results: Ordered list of result dicts.

        Returns:
            Deduplicated list preserving original ordering.
        """
        seen_hashes: set[str] = set()
        seen_ids: set[str] = set()
        deduplicated: list[dict] = []

        for result in results:
            # Check by document ID first
            result_id = result.get("id", "")
            if result_id and result_id in seen_ids:
                continue

            # Check by content hash
            content = result.get("content", "")
            if not content:
                deduplicated.append(result)
                if result_id:
                    seen_ids.add(result_id)
                continue

            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            if content_hash in seen_hashes:
                continue

            # Check for near-duplicate (>90% character overlap with shorter text)
            is_near_duplicate = False
            normalized_content = content.strip().lower()
            for existing in deduplicated:
                existing_content = existing.get("content", "").strip().lower()
                if not existing_content:
                    continue

                # Quick length check: if lengths differ by more than 20%, skip
                len_ratio = min(len(normalized_content), len(existing_content)) / max(
                    len(normalized_content), len(existing_content), 1
                )
                if len_ratio < 0.8:
                    continue

                # Check if one is a substring of the other
                shorter = min(normalized_content, existing_content, key=len)
                longer = max(normalized_content, existing_content, key=len)
                if shorter in longer:
                    is_near_duplicate = True
                    break

            if is_near_duplicate:
                continue

            deduplicated.append(result)
            seen_hashes.add(content_hash)
            if result_id:
                seen_ids.add(result_id)

        removed = len(results) - len(deduplicated)
        if removed > 0:
            logger.debug(
                "Deduplication removed results",
                extra={"removed": removed, "remaining": len(deduplicated)},
            )

        return deduplicated

    def _trim_to_context_window(self, results: list[dict]) -> list[dict]:
        """Trim results to fit within the LLM context window budget.

        Preserves ordering (highest priority first) and removes results
        from the tail until the total content fits.

        Args:
            results: Ordered list of result dicts.

        Returns:
            Trimmed list that fits within max_context_tokens.
        """
        if not results:
            return []

        trimmed: list[dict] = []
        total_chars = 0

        for result in results:
            content = result.get("content", "")
            content_chars = len(content)

            # Account for prompt formatting overhead (~200 chars per result)
            overhead = 200
            result_chars = content_chars + overhead

            if total_chars + result_chars > self._max_context_chars:
                # Check if we can include a truncated version
                remaining_budget = self._max_context_chars - total_chars - overhead
                if remaining_budget > 200:
                    # Include truncated content
                    truncated_result = dict(result)
                    truncated_result["content"] = content[:remaining_budget] + "..."
                    truncated_result["truncated"] = True
                    trimmed.append(truncated_result)
                break

            trimmed.append(result)
            total_chars += result_chars

        if len(trimmed) < len(results):
            logger.info(
                "Context window trimming applied",
                extra={
                    "original_count": len(results),
                    "trimmed_count": len(trimmed),
                    "total_chars": total_chars,
                    "max_chars": self._max_context_chars,
                },
            )

        return trimmed

    def build_context_prompt(
        self,
        fused_results: list[dict],
        query: str,
        drug_alerts: list[dict] | None = None,
    ) -> str:
        """Build the structured prompt for the synthesis LLM.

        Constructs a well-organized prompt with clear sections:
        1. System constraints (drug safety alerts)
        2. Patient context (demographics, conditions, meds, allergies, labs)
        3. Retrieved evidence (protocols, literature, records)
        4. Clinical question

        Args:
            fused_results: Ordered list of fused results from the fuse() method.
            query: Original clinical question.
            drug_alerts: Optional list of drug interaction alert dicts, each
                containing "severity", "description", "drugs" fields.

        Returns:
            Formatted context prompt string ready for the synthesis LLM.
        """
        sections: list[str] = []

        # ── Section 1: Drug Safety Constraints ───────────────────────────────
        safety_constraints = self._build_safety_section(fused_results, drug_alerts)
        if safety_constraints:
            sections.append(safety_constraints)

        # ── Section 2: Patient Context ───────────────────────────────────────
        patient_context = self._build_patient_section(fused_results)
        if patient_context:
            sections.append(patient_context)

        # ── Section 3: Retrieved Evidence ────────────────────────────────────
        evidence_section = self._build_evidence_section(fused_results)
        if evidence_section:
            sections.append(evidence_section)

        # ── Section 4: Clinical Question ─────────────────────────────────────
        sections.append(
            f"## CLINICAL QUESTION\n\n{query}"
        )

        prompt = "\n\n---\n\n".join(sections)

        logger.debug(
            "Context prompt built",
            extra={
                "prompt_length": len(prompt),
                "estimated_tokens": MedicalDocumentChunker.estimate_tokens(prompt),
                "section_count": len(sections),
            },
        )

        return prompt

    def _build_safety_section(
        self,
        fused_results: list[dict],
        drug_alerts: list[dict] | None = None,
    ) -> str:
        """Build the drug safety constraints section of the prompt.

        Args:
            fused_results: Fused results that may contain drug interaction data.
            drug_alerts: Additional drug alert dicts.

        Returns:
            Formatted safety constraints section, or empty string if none.
        """
        alerts: list[str] = []

        # Extract drug alerts from fused results
        for result in fused_results:
            if result.get("source_type") == "drug_interactions":
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                severity = metadata.get("severity", "unknown")
                drugs = metadata.get("drugs", [])

                if content:
                    drug_names = ", ".join(drugs) if drugs else "unknown drugs"
                    alerts.append(
                        f"- **[{severity.upper()}]** ({drug_names}): {content}"
                    )

        # Add explicit drug alerts
        if drug_alerts:
            for alert in drug_alerts:
                severity = alert.get("severity", "unknown")
                description = alert.get("description", "")
                drugs = alert.get("drugs", [])

                if description:
                    drug_names = ", ".join(drugs) if drugs else "unknown drugs"
                    alerts.append(
                        f"- **[{severity.upper()}]** ({drug_names}): {description}"
                    )

        if not alerts:
            return ""

        header = (
            "## DRUG SAFETY CONSTRAINTS\n\n"
            "**CRITICAL: The following drug safety alerts MUST be considered "
            "in any clinical recommendation. Do NOT suggest treatments that "
            "violate these constraints.**\n\n"
        )

        return header + "\n".join(alerts)

    def _build_patient_section(self, fused_results: list[dict]) -> str:
        """Build the patient context section of the prompt.

        Extracts and organizes patient-specific information from results
        tagged as patient_records.

        Args:
            fused_results: Fused results containing patient record data.

        Returns:
            Formatted patient context section, or empty string if no data.
        """
        patient_entries: list[str] = []
        patient_metadata_collected: dict[str, Any] = {}

        for result in fused_results:
            if result.get("source_type") != "patient_records":
                continue

            content = result.get("content", "")
            metadata = result.get("metadata", {})

            # Collect patient demographics from metadata
            for key in ("patient_id", "name", "age", "sex", "dob"):
                if key in metadata and key not in patient_metadata_collected:
                    patient_metadata_collected[key] = metadata[key]

            # Categorize patient content by section type
            section_type = metadata.get("section_type", result.get("section_type", ""))

            if content:
                label = section_type.replace("_", " ").title() if section_type else "Clinical Note"
                patient_entries.append(f"### {label}\n{content}")

        if not patient_entries:
            return ""

        # Build demographics header
        demographics_parts: list[str] = []
        if "patient_id" in patient_metadata_collected:
            demographics_parts.append(
                f"Patient ID: {patient_metadata_collected['patient_id']}"
            )
        if "age" in patient_metadata_collected:
            demographics_parts.append(f"Age: {patient_metadata_collected['age']}")
        if "sex" in patient_metadata_collected:
            demographics_parts.append(f"Sex: {patient_metadata_collected['sex']}")

        header = "## PATIENT CONTEXT\n\n"
        if demographics_parts:
            header += " | ".join(demographics_parts) + "\n\n"

        return header + "\n\n".join(patient_entries)

    def _build_evidence_section(self, fused_results: list[dict]) -> str:
        """Build the retrieved evidence section of the prompt.

        Organizes non-patient, non-drug-alert results by source type with
        clear source attribution and citation metadata.

        Args:
            fused_results: Fused results.

        Returns:
            Formatted evidence section, or empty string if no evidence.
        """
        evidence_by_source: dict[str, list[str]] = {}

        for result in fused_results:
            source_type = result.get("source_type", "unknown")

            # Skip patient records and drug interactions (handled in other sections)
            if source_type in ("patient_records", "drug_interactions"):
                continue

            content = result.get("content", "")
            if not content:
                continue

            metadata = result.get("metadata", {})

            # Build citation info
            citation_parts: list[str] = []
            if "title" in metadata:
                citation_parts.append(f"**{metadata['title']}**")
            if "authors" in metadata and metadata["authors"]:
                authors = metadata["authors"]
                if isinstance(authors, list):
                    authors = ", ".join(authors[:3])
                    if len(metadata["authors"]) > 3:
                        authors += " et al."
                citation_parts.append(authors)
            if "journal" in metadata:
                citation_parts.append(f"*{metadata['journal']}*")
            if "pmid" in metadata:
                citation_parts.append(f"PMID: {metadata['pmid']}")
            if "evidence_grade" in metadata:
                citation_parts.append(f"Evidence Grade: {metadata['evidence_grade']}")

            relevance_score = result.get("relevance_score")
            score_label = ""
            if relevance_score is not None:
                score_label = f" (relevance: {relevance_score:.2f})"

            citation_line = " | ".join(citation_parts) if citation_parts else ""

            entry = ""
            if citation_line:
                entry += f"*Source: {citation_line}*{score_label}\n\n"
            entry += content

            source_label = source_type.replace("_", " ").title()
            if source_label not in evidence_by_source:
                evidence_by_source[source_label] = []
            evidence_by_source[source_label].append(entry)

        if not evidence_by_source:
            return ""

        parts: list[str] = ["## RETRIEVED EVIDENCE\n"]

        for source_label, entries in evidence_by_source.items():
            parts.append(f"### {source_label}\n")
            for i, entry in enumerate(entries, 1):
                parts.append(f"**[{source_label} #{i}]**\n{entry}\n")

        return "\n".join(parts)

    def extract_citations(self, fused_results: list[dict]) -> list[dict]:
        """Extract citation metadata from all fused results.

        Builds a structured list of citations that can be included in the
        final clinical response for traceability and evidence grading.

        Args:
            fused_results: Fused results from the fuse() method.

        Returns:
            List of citation dicts, each containing:
                source_type, document_id, title, authors, journal, pmid,
                evidence_grade, relevance_score, fusion_rank.
        """
        citations: list[dict] = []

        for result in fused_results:
            metadata = result.get("metadata", {})

            citation: dict[str, Any] = {
                "source_type": result.get("source_type", "unknown"),
                "document_id": result.get("id", ""),
                "fusion_rank": result.get("fusion_rank"),
                "relevance_score": result.get("relevance_score"),
            }

            # Extract citation-relevant metadata
            for field in (
                "title",
                "authors",
                "journal",
                "pmid",
                "evidence_grade",
                "publication_date",
                "section_type",
                "patient_id",
                "severity",
            ):
                if field in metadata:
                    citation[field] = metadata[field]

            # Extract content snippet for context
            content = result.get("content", "")
            if content:
                citation["snippet"] = content[:300] + ("..." if len(content) > 300 else "")

            citations.append(citation)

        logger.debug(
            "Citations extracted",
            extra={"citation_count": len(citations)},
        )

        return citations
