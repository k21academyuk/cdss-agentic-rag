"""PubMed E-Utilities API client for biomedical literature search.

Provides async access to NCBI's Entrez E-Utilities including ESearch,
EFetch, and ELink endpoints. Supports MeSH term queries, Boolean
operators, date filtering, and related-article discovery.

Rate limits: 3 requests/second without API key, 10 requests/second with key.
See: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from xml.etree import ElementTree

import httpx

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import CDSSError, RateLimitError

logger = logging.getLogger(__name__)


class PubMedClientError(CDSSError):
    """Raised when a PubMed API call fails."""

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


class PubMedClient:
    """Client for NCBI PubMed E-Utilities API.

    Provides methods to search PubMed, fetch article details, find related
    articles, and build optimized MeSH queries. All network calls are async
    with automatic retry and exponential backoff for rate-limit handling.
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 0.5

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key: str = self.settings.pubmed_api_key
        self.email: str = self.settings.pubmed_email
        self._client = httpx.AsyncClient(
            timeout=30.0,
            base_url=self.BASE_URL,
            headers={"User-Agent": "CDSS-Agentic-RAG/1.0"},
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _common_params(self) -> dict[str, str]:
        """Return parameters shared across all E-Utility requests."""
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with exponential-backoff retry on rate limits.

        Args:
            method: HTTP method (GET or POST).
            url: Relative URL path (e.g., ``esearch.fcgi``).
            params: Query string parameters.
            data: Form data for POST requests.

        Returns:
            The successful ``httpx.Response``.

        Raises:
            PubMedClientError: After all retries are exhausted or on non-retryable errors.
            RateLimitError: If rate limits persist after all retry attempts.
        """
        last_exception: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                if method.upper() == "GET":
                    response = await self._client.get(url, params=params)
                else:
                    response = await self._client.post(url, params=params, data=data)

                elapsed = time.monotonic() - start_time
                logger.debug(
                    "PubMed %s %s completed in %.3fs (status=%d)",
                    method.upper(),
                    url,
                    elapsed,
                    response.status_code,
                )

                # Handle rate-limit responses (HTTP 429 or 503)
                if response.status_code in (429, 503):
                    retry_after = float(
                        response.headers.get("Retry-After", self.BASE_BACKOFF_SECONDS * (2 ** attempt))
                    )
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            "PubMed rate limit hit (attempt %d/%d). Retrying in %.2fs.",
                            attempt + 1,
                            self.MAX_RETRIES + 1,
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        message=f"PubMed rate limit exceeded after {self.MAX_RETRIES + 1} attempts",
                        retry_after=retry_after,
                        details={"endpoint": url, "status_code": response.status_code},
                    )

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "PubMed %s %s failed with HTTP %d after %.3fs: %s",
                    method.upper(),
                    url,
                    exc.response.status_code,
                    elapsed,
                    str(exc),
                )
                raise PubMedClientError(
                    message=f"PubMed API returned HTTP {exc.response.status_code}",
                    endpoint=url,
                    status_code=exc.response.status_code,
                    details={"response_text": exc.response.text[:500]},
                ) from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - start_time
                logger.warning(
                    "PubMed %s %s request error (attempt %d/%d) after %.3fs: %s",
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

        raise PubMedClientError(
            message=f"PubMed request failed after {self.MAX_RETRIES + 1} attempts: {last_exception}",
            endpoint=url,
            details={"last_error": str(last_exception)},
        )

    # ── Public API ───────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_results: int = 50,
        date_range: tuple[str, str] | None = None,
        sort: str = "relevance",
    ) -> list[str]:
        """Search PubMed and return a list of PMIDs.

        Uses the ESearch E-Utility endpoint. Supports MeSH terms, Boolean
        operators (AND, OR, NOT), field tags, and date filtering.

        Args:
            query: PubMed search query string.
            max_results: Maximum number of PMIDs to return (max 10000).
            date_range: Optional ``(mindate, maxdate)`` tuple in ``YYYY/MM/DD``
                format. When provided, filters results by publication date.
            sort: Sort order -- ``"relevance"`` (default) or ``"pub_date"``.

        Returns:
            List of PMID strings.

        Raises:
            PubMedClientError: If the API call fails.
        """
        params = {
            **self._common_params(),
            "db": "pubmed",
            "term": query,
            "retmax": str(min(max_results, 10000)),
            "retmode": "json",
            "sort": sort,
        }

        if date_range is not None:
            mindate, maxdate = date_range
            params["mindate"] = mindate
            params["maxdate"] = maxdate
            params["datetype"] = "pdat"

        logger.info(
            "PubMed search: query=%r, max_results=%d, sort=%s, date_range=%s",
            query,
            max_results,
            sort,
            date_range,
        )

        response = await self._request_with_retry("GET", "esearch.fcgi", params=params)
        data = response.json()

        esearch_result = data.get("esearchresult", {})

        # Check for query translation errors
        error_list = esearch_result.get("errorlist", {})
        if error_list:
            phrase_not_found = error_list.get("phrasesnotfound", [])
            if phrase_not_found:
                logger.warning(
                    "PubMed search: phrases not found: %s", phrase_not_found
                )

        pmids: list[str] = esearch_result.get("idlist", [])
        total_count = int(esearch_result.get("count", 0))

        logger.info(
            "PubMed search returned %d PMIDs (total matching: %d)",
            len(pmids),
            total_count,
        )

        return pmids

    async def fetch_articles(self, pmids: list[str]) -> list[dict[str, Any]]:
        """Fetch full article details for a list of PMIDs.

        Uses the EFetch E-Utility endpoint with XML output for comprehensive
        article metadata including MeSH terms.

        Args:
            pmids: List of PubMed ID strings to fetch.

        Returns:
            List of article dictionaries containing: ``pmid``, ``title``,
            ``abstract``, ``authors``, ``journal``, ``pub_date``,
            ``mesh_terms``, ``doi``, ``pmc_id``.

        Raises:
            PubMedClientError: If the API call or XML parsing fails.
        """
        if not pmids:
            return []

        # EFetch has a practical limit; batch in groups of 200
        all_articles: list[dict[str, Any]] = []
        batch_size = 200

        for batch_start in range(0, len(pmids), batch_size):
            batch = pmids[batch_start : batch_start + batch_size]

            params = self._common_params()
            form_data = {
                "db": "pubmed",
                "id": ",".join(batch),
                "rettype": "xml",
                "retmode": "xml",
            }

            logger.info(
                "PubMed fetch: retrieving %d articles (batch %d-%d of %d)",
                len(batch),
                batch_start + 1,
                batch_start + len(batch),
                len(pmids),
            )

            response = await self._request_with_retry(
                "POST", "efetch.fcgi", params=params, data=form_data
            )

            try:
                articles = self._parse_efetch_xml(response.text)
                all_articles.extend(articles)
            except ElementTree.ParseError as exc:
                logger.error("Failed to parse PubMed EFetch XML: %s", exc)
                raise PubMedClientError(
                    message="Failed to parse PubMed XML response",
                    endpoint="efetch.fcgi",
                    details={"parse_error": str(exc)},
                ) from exc

        logger.info("PubMed fetch: parsed %d articles total", len(all_articles))
        return all_articles

    async def search_and_fetch(
        self,
        query: str,
        max_results: int = 20,
        date_range: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Combined search + fetch in a single call.

        Convenience method that runs ESearch followed by EFetch.

        Args:
            query: PubMed search query.
            max_results: Maximum number of articles to return.
            date_range: Optional ``(mindate, maxdate)`` tuple in ``YYYY/MM/DD`` format.

        Returns:
            List of fully populated article dictionaries.
        """
        pmids = await self.search(query, max_results, date_range)
        if not pmids:
            logger.info("PubMed search_and_fetch: no results for query=%r", query)
            return []
        return await self.fetch_articles(pmids)

    async def get_related_articles(
        self, pmid: str, max_results: int = 10
    ) -> list[str]:
        """Discover related articles for a given PMID using ELink.

        Uses the neighbor_score command to find articles that PubMed considers
        related based on shared MeSH terms and citation patterns.

        Args:
            pmid: Source PubMed ID.
            max_results: Maximum number of related PMIDs to return.

        Returns:
            List of related PMID strings, ordered by relevance score.
        """
        params = {
            **self._common_params(),
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "cmd": "neighbor_score",
            "retmode": "json",
        }

        logger.info("PubMed related articles: pmid=%s, max_results=%d", pmid, max_results)

        response = await self._request_with_retry("GET", "elink.fcgi", params=params)
        data = response.json()

        related_pmids: list[str] = []
        linksets = data.get("linksets", [])
        for linkset in linksets:
            linksetdbs = linkset.get("linksetdbs", [])
            for linksetdb in linksetdbs:
                if linksetdb.get("linkname") == "pubmed_pubmed":
                    links = linksetdb.get("links", [])
                    for link in links:
                        link_id = str(link.get("id", ""))
                        if link_id and link_id != pmid:
                            related_pmids.append(link_id)
                        if len(related_pmids) >= max_results:
                            break
                if len(related_pmids) >= max_results:
                    break
            if len(related_pmids) >= max_results:
                break

        logger.info(
            "PubMed related articles for PMID %s: found %d",
            pmid,
            len(related_pmids),
        )
        return related_pmids[:max_results]

    def build_mesh_query(
        self,
        conditions: list[str],
        treatments: list[str] | None = None,
        date_from: str | None = None,
    ) -> str:
        """Build an optimized PubMed query using MeSH terms and Boolean operators.

        Constructs a structured query string combining condition MeSH terms
        (joined with OR) and optionally treatment MeSH terms (joined with OR),
        combining the two groups with AND. An optional date filter restricts
        results to publications from a given date onward.

        Args:
            conditions: List of medical condition terms (e.g.,
                ``["diabetes mellitus, type 2", "insulin resistance"]``).
            treatments: Optional list of treatment terms (e.g.,
                ``["metformin", "insulin"]``).
            date_from: Optional start date in ``YYYY/MM/DD`` format for
                filtering by publication date.

        Returns:
            Formatted PubMed query string.

        Examples:
            >>> client = PubMedClient()
            >>> client.build_mesh_query(
            ...     conditions=["diabetes mellitus, type 2"],
            ...     treatments=["metformin", "insulin"],
            ...     date_from="2020/01/01",
            ... )
            '(("diabetes mellitus, type 2"[MeSH Terms])) AND (("metformin"[MeSH Terms]) OR ("insulin"[MeSH Terms])) AND ("2020/01/01"[Date - Publication] : "3000"[Date - Publication])'
        """
        # Build condition group
        condition_parts = [f'"{c}"[MeSH Terms]' for c in conditions]
        condition_group = "(" + " OR ".join(f"({p})" for p in condition_parts) + ")"

        query_parts: list[str] = [condition_group]

        # Build treatment group if provided
        if treatments:
            treatment_parts = [f'"{t}"[MeSH Terms]' for t in treatments]
            treatment_group = "(" + " OR ".join(f"({p})" for p in treatment_parts) + ")"
            query_parts.append(treatment_group)

        # Add date filter
        if date_from:
            date_filter = f'("{date_from}"[Date - Publication] : "3000"[Date - Publication])'
            query_parts.append(date_filter)

        query = " AND ".join(query_parts)
        logger.debug("Built MeSH query: %s", query)
        return query

    # ── XML Parsing ──────────────────────────────────────────────────────────

    def _parse_efetch_xml(self, xml_text: str) -> list[dict[str, Any]]:
        """Parse EFetch XML response into structured article dictionaries.

        Args:
            xml_text: Raw XML response from EFetch.

        Returns:
            List of article dictionaries.
        """
        root = ElementTree.fromstring(xml_text)
        articles: list[dict[str, Any]] = []

        for article_elem in root.findall(".//PubmedArticle"):
            article = self._parse_single_article(article_elem)
            if article:
                articles.append(article)

        return articles

    def _parse_single_article(
        self, article_elem: ElementTree.Element
    ) -> dict[str, Any]:
        """Parse a single PubmedArticle XML element.

        Args:
            article_elem: ``<PubmedArticle>`` XML element.

        Returns:
            Dictionary with article metadata.
        """
        citation = article_elem.find(".//MedlineCitation")
        if citation is None:
            return {}

        # PMID
        pmid_elem = citation.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else ""

        # Article section
        article_section = citation.find(".//Article")
        if article_section is None:
            return {"pmid": pmid}

        # Title
        title_elem = article_section.find(".//ArticleTitle")
        title = self._extract_text_with_children(title_elem)

        # Abstract -- may have multiple AbstractText elements (structured abstract)
        abstract_parts: list[str] = []
        abstract_elem = article_section.find(".//Abstract")
        if abstract_elem is not None:
            for text_elem in abstract_elem.findall(".//AbstractText"):
                label = text_elem.get("Label", "")
                text_content = self._extract_text_with_children(text_elem)
                if label:
                    abstract_parts.append(f"{label}: {text_content}")
                else:
                    abstract_parts.append(text_content)
        abstract = "\n".join(abstract_parts)

        # Authors
        authors: list[str] = []
        author_list = article_section.find(".//AuthorList")
        if author_list is not None:
            for author_elem in author_list.findall(".//Author"):
                last_name_elem = author_elem.find("LastName")
                fore_name_elem = author_elem.find("ForeName")
                if last_name_elem is not None and last_name_elem.text:
                    name = last_name_elem.text
                    if fore_name_elem is not None and fore_name_elem.text:
                        name = f"{last_name_elem.text} {fore_name_elem.text}"
                    authors.append(name)
                else:
                    # Collective author
                    collective = author_elem.find("CollectiveName")
                    if collective is not None and collective.text:
                        authors.append(collective.text)

        # Journal
        journal_elem = article_section.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None and journal_elem.text else ""

        # Publication date
        pub_date = self._parse_pub_date(article_section)

        # MeSH terms
        mesh_terms: list[str] = []
        mesh_list = citation.find(".//MeshHeadingList")
        if mesh_list is not None:
            for heading in mesh_list.findall(".//MeshHeading"):
                descriptor = heading.find("DescriptorName")
                if descriptor is not None and descriptor.text:
                    mesh_terms.append(descriptor.text)
                # Include qualifiers for richer context
                for qualifier in heading.findall("QualifierName"):
                    if qualifier.text:
                        mesh_terms.append(f"{descriptor.text}/{qualifier.text}" if descriptor is not None and descriptor.text else qualifier.text)

        # Article IDs (DOI, PMC)
        doi = ""
        pmc_id = ""
        pubmed_data = article_elem.find(".//PubmedData")
        if pubmed_data is not None:
            article_id_list = pubmed_data.find(".//ArticleIdList")
            if article_id_list is not None:
                for aid in article_id_list.findall("ArticleId"):
                    id_type = aid.get("IdType", "")
                    if id_type == "doi" and aid.text:
                        doi = aid.text
                    elif id_type == "pmc" and aid.text:
                        pmc_id = aid.text

        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "pub_date": pub_date,
            "mesh_terms": mesh_terms,
            "doi": doi,
            "pmc_id": pmc_id,
        }

    @staticmethod
    def _extract_text_with_children(elem: ElementTree.Element | None) -> str:
        """Extract all text content from an element including mixed content children.

        PubMed XML often has inline tags (``<i>``, ``<b>``, ``<sub>``, ``<sup>``)
        within text elements. This method extracts all text, stripping inline tags.

        Args:
            elem: XML element, or ``None``.

        Returns:
            Concatenated text content.
        """
        if elem is None:
            return ""
        # itertext() yields all text content including from child elements
        return "".join(elem.itertext()).strip()

    @staticmethod
    def _parse_pub_date(article_section: ElementTree.Element) -> str:
        """Extract and format the publication date from an Article element.

        Handles both structured dates (Year/Month/Day) and MedlineDate fallbacks.

        Args:
            article_section: ``<Article>`` XML element.

        Returns:
            Date string in ``YYYY-MM-DD``, ``YYYY-MM``, ``YYYY``, or raw format.
        """
        pub_date_elem = article_section.find(".//Journal/JournalIssue/PubDate")
        if pub_date_elem is None:
            return ""

        year_elem = pub_date_elem.find("Year")
        month_elem = pub_date_elem.find("Month")
        day_elem = pub_date_elem.find("Day")

        if year_elem is not None and year_elem.text:
            parts = [year_elem.text]
            if month_elem is not None and month_elem.text:
                # Month can be numeric or abbreviated name
                month_text = month_elem.text
                month_map = {
                    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                }
                month_num = month_map.get(month_text, month_text)
                parts.append(month_num)
                if day_elem is not None and day_elem.text:
                    parts.append(day_elem.text.zfill(2))
            return "-".join(parts)

        # Fallback: MedlineDate
        medline_date = pub_date_elem.find("MedlineDate")
        if medline_date is not None and medline_date.text:
            return medline_date.text.strip()

        return ""

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        await self._client.aclose()
        logger.debug("PubMedClient closed")

    async def __aenter__(self) -> PubMedClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
