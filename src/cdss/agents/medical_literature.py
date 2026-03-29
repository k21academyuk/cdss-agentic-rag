"""Medical Literature Agent for the Clinical Decision Support System.

Searches PubMed via NCBI E-Utilities and the Azure AI Search literature
cache for relevant medical evidence, performs LLM-assisted relevance
scoring, and synthesizes an evidence summary with citations.
"""

from __future__ import annotations

import json
import re
from typing import Any

from cdss.agents.base import BaseAgent
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.clients.pubmed_client import PubMedClient
from cdss.clients.search_client import AzureSearchClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AgentError
from cdss.core.models import (
    AgentTask,
    Citation,
    LiteratureEvidence,
    PubMedArticle,
)


class MedicalLiteratureAgent(BaseAgent):
    """Searches PubMed and cached literature for relevant medical evidence.

    Tools:
    - pubmed_search(query, max_results, mesh)
    - pubmed_fetch(pmid_list)
    - azure_ai_search(index="literature-cache")

    Model: GPT-4o
    Output: LiteratureEvidence
    """

    # Maximum articles to retrieve from PubMed in real-time
    MAX_PUBMED_RESULTS = 20
    # Maximum articles from the literature cache
    MAX_CACHE_RESULTS = 15
    # Maximum articles to send for evidence assessment
    MAX_ARTICLES_FOR_ASSESSMENT = 15

    def __init__(
        self,
        pubmed_client: PubMedClient | None = None,
        search_client: AzureSearchClient | None = None,
        openai_client: AzureOpenAIClient | None = None,
        retriever: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the MedicalLiteratureAgent.

        Args:
            pubmed_client: PubMed E-Utilities client for real-time literature search.
            search_client: Azure AI Search client for the literature cache index.
            openai_client: Azure OpenAI client for query optimization and evidence assessment.
            retriever: Optional RAG retriever for enhanced document retrieval.
            settings: Application settings. Defaults to environment-loaded settings.
        """
        super().__init__(name="medical_literature_agent", model="gpt-4o")
        self._settings = settings or get_settings()
        self._pubmed_client = pubmed_client or PubMedClient(settings=self._settings)
        self._search_client = search_client or AzureSearchClient(settings=self._settings)
        self._openai_client = openai_client or AzureOpenAIClient(settings=self._settings)
        self._retriever = retriever

    async def _execute(self, task: AgentTask) -> dict:
        """Search medical literature from PubMed and cache.

        1. Generate optimized PubMed query using LLM (convert natural language to MeSH terms)
        2. Search PubMed via E-Utilities (real-time)
        3. Search cached literature in AI Search
        4. Merge and deduplicate results
        5. LLM-assisted relevance scoring and summarization
        6. Return LiteratureEvidence with citations

        Args:
            task: Agent task with payload containing ``query`` and optionally
                  ``patient_context`` with conditions/medications.

        Returns:
            Dictionary containing ``summary``, ``sources_retrieved``, and
            ``literature_evidence`` (serialized LiteratureEvidence).
        """
        query = task.payload.get("query", "")
        patient_context = task.payload.get("patient_context", {})

        if not query:
            raise AgentError(
                message="query is required in task payload",
                agent_name=self.name,
            )

        # Extract conditions from patient context if available
        conditions = []
        if patient_context:
            for cond in patient_context.get("conditions", []):
                display = cond.get("display", "")
                if display:
                    conditions.append(display)

        self.logger.info(
            "Starting medical literature search",
            extra={
                "query": query[:100],
                "conditions_count": len(conditions),
            },
        )

        # Step 1: Generate optimized PubMed query
        optimized_query = await self._generate_pubmed_query(query, conditions or None)
        self.logger.debug(
            "Optimized PubMed query generated",
            extra={"optimized_query": optimized_query[:200]},
        )

        # Step 2: Search PubMed (real-time)
        pubmed_articles = await self._search_pubmed(optimized_query)
        if not pubmed_articles and optimized_query.strip() != query.strip():
            self.logger.info(
                "Optimized PubMed query returned zero results; retrying with natural-language query",
                extra={
                    "optimized_query": optimized_query[:160],
                    "fallback_query": query[:160],
                },
            )
            pubmed_articles = await self._search_pubmed(query)

        # Step 3: Search AI Search literature cache
        cached_articles = await self._search_literature_cache(query)

        # Step 4: Merge results, deduplicate by PMID
        merged_articles = self._merge_and_deduplicate(pubmed_articles, cached_articles)
        total_found = len(pubmed_articles) + len(cached_articles)

        self.logger.info(
            "Literature search results merged",
            extra={
                "pubmed_count": len(pubmed_articles),
                "cache_count": len(cached_articles),
                "merged_count": len(merged_articles),
            },
        )

        # Step 5: Score relevance, identify contradictions, assess consensus
        assessment = await self._assess_evidence(query, merged_articles)

        # Step 6: Build LiteratureEvidence model
        citations = self._build_citations(merged_articles, assessment)

        evidence = LiteratureEvidence(
            papers=[
                PubMedArticle(
                    pmid=a.get("pmid", ""),
                    title=a.get("title", ""),
                    authors=a.get("authors", []),
                    journal=a.get("journal", ""),
                    publication_date=a.get("pub_date", a.get("publication_date", "")),
                    abstract=a.get("abstract", ""),
                    mesh_terms=a.get("mesh_terms", []),
                    doi=a.get("doi"),
                    pmc_id=a.get("pmc_id"),
                )
                for a in merged_articles[:self.MAX_ARTICLES_FOR_ASSESSMENT]
                if a.get("pmid")
            ],
            evidence_level=assessment.get("evidence_level", "Level V - Expert Opinion"),
            summary=assessment.get("summary", "No evidence summary available."),
            contradictions=assessment.get("contradictions", []),
            consensus_strength=assessment.get("consensus_strength", 0.5),
        )

        return {
            "summary": evidence.summary,
            "sources_retrieved": len(merged_articles),
            "literature_evidence": evidence.model_dump(),
            "optimized_query": optimized_query,
            "total_articles_found": total_found,
            "articles_analyzed": min(len(merged_articles), self.MAX_ARTICLES_FOR_ASSESSMENT),
            "citations": [c.model_dump() for c in citations],
        }

    def _sanitize_pubmed_query(self, raw_query: str) -> str:
        """Normalize LLM output into a plain PubMed query string.

        The planner can occasionally return markdown wrappers such as:
        ```plaintext
        (query...)
        ```
        This helper strips formatting artifacts before the PubMed request.
        """
        cleaned = (raw_query or "").strip()
        if not cleaned:
            return ""

        fenced_match = re.match(r"^```[^\n]*\n(?P<body>.*)\n```$", cleaned, flags=re.DOTALL)
        if fenced_match:
            cleaned = fenced_match.group("body").strip()

        cleaned = re.sub(r"^\s*(pubmed\s+query|query)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip("`").strip()
        return cleaned

    async def _generate_pubmed_query(
        self, natural_query: str, conditions: list[str] | None = None
    ) -> str:
        """Use GPT-4o to convert natural language to optimized PubMed query with MeSH terms.

        Args:
            natural_query: The clinician's natural language question.
            conditions: Optional list of patient conditions for context.

        Returns:
            An optimized PubMed query string using MeSH terms and Boolean operators.
        """
        system_prompt = (
            "You are a medical literature search specialist. Convert the following "
            "clinical question into an optimized PubMed query using:\n"
            "- MeSH terms where appropriate (e.g., \"diabetes mellitus, type 2\"[MeSH Terms])\n"
            "- Boolean operators (AND, OR, NOT)\n"
            "- Field tags where helpful ([Title/Abstract], [MeSH Terms])\n"
            "- Date filters if the query implies recency\n\n"
            "Return ONLY the PubMed query string, nothing else. "
            "Make the query specific enough to find relevant results "
            "but broad enough to capture important evidence."
        )

        user_content = f"Clinical Question: {natural_query}"
        if conditions:
            user_content += f"\n\nPatient Conditions: {', '.join(conditions)}"

        try:
            response = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=512,
            )
            optimized = self._sanitize_pubmed_query(response.get("content", ""))
            # Fallback if the LLM returns empty or garbage
            if not optimized or len(optimized) < 5:
                self.logger.warning(
                    "LLM returned empty PubMed query, using natural language query",
                    extra={"raw_response": optimized},
                )
                return natural_query
            return optimized
        except Exception as exc:
            self.logger.warning(
                "PubMed query optimization failed, using natural language query",
                extra={"error": str(exc)},
            )
            return natural_query

    async def _search_pubmed(self, query: str) -> list[dict]:
        """Search PubMed and fetch article details.

        Args:
            query: The PubMed-optimized search query.

        Returns:
            List of article dictionaries from PubMed.
        """
        try:
            articles = await self._pubmed_client.search_and_fetch(
                query=query,
                max_results=self.MAX_PUBMED_RESULTS,
            )
            self.logger.info(
                "PubMed search completed",
                extra={"query": query[:100], "articles_found": len(articles)},
            )
            # Tag source for deduplication
            for article in articles:
                article["_source"] = "pubmed"
            return articles
        except Exception as exc:
            self.logger.warning(
                "PubMed search failed, continuing with cache only",
                extra={"error": str(exc)},
            )
            return []

    async def _search_literature_cache(self, query: str) -> list[dict]:
        """Search the Azure AI Search medical literature cache index.

        Args:
            query: The natural language clinical query.

        Returns:
            List of cached article dictionaries.
        """
        try:
            results = await self._search_client.search_medical_literature(
                query=query,
                top=self.MAX_CACHE_RESULTS,
            )
            # Transform search results into article-like dicts
            articles: list[dict] = []
            for r in results:
                metadata = r.get("metadata", {})
                articles.append({
                    "pmid": metadata.get("pmid", r.get("id", "")),
                    "title": metadata.get("title", ""),
                    "abstract": r.get("content", ""),
                    "authors": metadata.get("authors", []),
                    "journal": metadata.get("journal", ""),
                    "pub_date": metadata.get("pub_date", metadata.get("publication_date", "")),
                    "mesh_terms": metadata.get("mesh_terms", []),
                    "doi": metadata.get("doi", ""),
                    "pmc_id": metadata.get("pmc_id", ""),
                    "_source": "cache",
                    "_score": r.get("score", 0.0),
                    "_reranker_score": r.get("reranker_score", 0.0),
                })
            self.logger.info(
                "Literature cache search completed",
                extra={"articles_found": len(articles)},
            )
            return articles
        except Exception as exc:
            self.logger.warning(
                "Literature cache search failed, continuing with PubMed only",
                extra={"error": str(exc)},
            )
            return []

    def _merge_and_deduplicate(
        self, pubmed_articles: list[dict], cached_articles: list[dict]
    ) -> list[dict]:
        """Merge PubMed and cached articles, deduplicating by PMID.

        PubMed articles take precedence over cached versions since they
        contain the most up-to-date data from the source.

        Args:
            pubmed_articles: Articles retrieved from PubMed.
            cached_articles: Articles retrieved from the literature cache.

        Returns:
            Deduplicated list of article dictionaries.
        """
        seen_pmids: set[str] = set()
        merged: list[dict] = []

        # PubMed articles first (they have full metadata)
        for article in pubmed_articles:
            pmid = article.get("pmid", "")
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                merged.append(article)
            elif not pmid:
                merged.append(article)

        # Add cached articles not already seen
        for article in cached_articles:
            pmid = article.get("pmid", "")
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                merged.append(article)
            elif not pmid:
                merged.append(article)

        return merged

    async def _assess_evidence(self, query: str, articles: list[dict]) -> dict:
        """Use GPT-4o to assess evidence level, identify contradictions, summarize consensus.

        Args:
            query: The original clinical query.
            articles: List of article dictionaries to assess.

        Returns:
            Dictionary with keys: ``evidence_level``, ``summary``,
            ``contradictions``, ``consensus_strength``, ``relevance_scores``.
        """
        if not articles:
            return {
                "evidence_level": "Level V - Expert Opinion",
                "summary": "No relevant medical literature was found for this query.",
                "contradictions": [],
                "consensus_strength": 0.0,
                "relevance_scores": {},
            }

        # Prepare article summaries for the LLM (truncate to fit context)
        article_summaries: list[str] = []
        for i, article in enumerate(articles[:self.MAX_ARTICLES_FOR_ASSESSMENT]):
            title = article.get("title", "Untitled")
            abstract = article.get("abstract", "No abstract available.")[:800]
            journal = article.get("journal", "Unknown journal")
            pub_date = article.get("pub_date", article.get("publication_date", "Unknown date"))
            pmid = article.get("pmid", "Unknown")
            mesh = ", ".join(article.get("mesh_terms", [])[:5])

            summary_text = (
                f"[Article {i + 1}] PMID: {pmid}\n"
                f"Title: {title}\n"
                f"Journal: {journal} ({pub_date})\n"
                f"MeSH Terms: {mesh}\n"
                f"Abstract: {abstract}"
            )
            article_summaries.append(summary_text)

        articles_text = "\n\n---\n\n".join(article_summaries)

        system_prompt = (
            "You are an evidence-based medicine specialist evaluating medical literature "
            "for a Clinical Decision Support System. Analyze the provided articles and "
            "produce a structured evidence assessment.\n\n"
            "Respond with a JSON object containing:\n"
            "- \"evidence_level\": overall evidence level using Oxford CEBM levels:\n"
            "  - \"Level I - Systematic Review\" (of RCTs)\n"
            "  - \"Level II - Randomized Controlled Trial\"\n"
            "  - \"Level III - Cohort Study\"\n"
            "  - \"Level IV - Case Series\"\n"
            "  - \"Level V - Expert Opinion\"\n"
            "- \"summary\": a 2-4 sentence synthesis of the evidence, noting key findings, "
            "strength of evidence, and clinical implications\n"
            "- \"contradictions\": list of strings describing any contradictory findings "
            "between articles (empty list if none)\n"
            "- \"consensus_strength\": float from 0.0 (no consensus) to 1.0 (strong consensus)\n"
            "- \"relevance_scores\": object mapping PMID to relevance score (0.0-1.0) "
            "for each article"
        )

        user_prompt = (
            f"Clinical Query: {query}\n\n"
            f"Articles to Assess ({len(article_summaries)} total):\n\n{articles_text}"
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

            assessment = json.loads(response.get("content", "{}"))

            # Validate and set defaults
            valid_levels = {
                "Level I - Systematic Review",
                "Level II - Randomized Controlled Trial",
                "Level III - Cohort Study",
                "Level IV - Case Series",
                "Level V - Expert Opinion",
            }
            if assessment.get("evidence_level") not in valid_levels:
                assessment["evidence_level"] = "Level V - Expert Opinion"

            assessment.setdefault("summary", "Evidence assessment could not be completed.")
            assessment.setdefault("contradictions", [])
            consensus = assessment.get("consensus_strength", 0.5)
            assessment["consensus_strength"] = max(0.0, min(1.0, float(consensus)))
            assessment.setdefault("relevance_scores", {})

            self.logger.info(
                "Evidence assessment completed",
                extra={
                    "evidence_level": assessment["evidence_level"],
                    "consensus_strength": assessment["consensus_strength"],
                    "contradictions_count": len(assessment["contradictions"]),
                },
            )
            return assessment

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse evidence assessment JSON",
                extra={"error": str(exc)},
            )
            return {
                "evidence_level": "Level V - Expert Opinion",
                "summary": "Evidence assessment could not be completed due to a processing error.",
                "contradictions": [],
                "consensus_strength": 0.5,
                "relevance_scores": {},
            }
        except Exception as exc:
            self.logger.warning(
                "Evidence assessment failed",
                extra={"error": str(exc)},
            )
            return {
                "evidence_level": "Level V - Expert Opinion",
                "summary": f"Found {len(articles)} potentially relevant articles but evidence assessment could not be completed.",
                "contradictions": [],
                "consensus_strength": 0.5,
                "relevance_scores": {},
            }

    def _build_citations(
        self, articles: list[dict], assessment: dict
    ) -> list[Citation]:
        """Build Citation objects from articles with relevance scores from assessment.

        Args:
            articles: Merged article list.
            assessment: Evidence assessment containing relevance scores.

        Returns:
            List of Citation objects ordered by relevance score descending.
        """
        relevance_scores = assessment.get("relevance_scores", {})
        citations: list[Citation] = []

        for article in articles[:self.MAX_ARTICLES_FOR_ASSESSMENT]:
            pmid = article.get("pmid", "")
            score = relevance_scores.get(pmid, 0.5)
            try:
                score = max(0.0, min(1.0, float(score)))
            except (TypeError, ValueError):
                score = 0.5

            doi = article.get("doi", "")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
            if not url and doi:
                url = f"https://doi.org/{doi}"

            citations.append(
                Citation(
                    source_type="pubmed",
                    identifier=pmid or article.get("title", "unknown")[:50],
                    title=article.get("title", "Untitled"),
                    relevance_score=score,
                    url=url,
                )
            )

        # Sort by relevance score descending
        citations.sort(key=lambda c: c.relevance_score, reverse=True)
        return citations
