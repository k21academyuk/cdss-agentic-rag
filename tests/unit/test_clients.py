"""Tests for external API clients: PubMed, OpenFDA, RxNorm, DrugBank.

All HTTP calls are mocked via httpx or patch. Tests cover response
parsing, error handling, rate limiting, and edge cases.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from xml.etree import ElementTree

import pytest

from cdss.core.config import Settings
from cdss.core.exceptions import CDSSError, RateLimitError
from cdss.clients.pubmed_client import PubMedClient, PubMedClientError
from cdss.clients.openfda_client import OpenFDAClient, OpenFDAClientError


# ═══════════════════════════════════════════════════════════════════════════════
# PubMedClient Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPubMedClient:
    """Tests for the PubMedClient."""

    @pytest.fixture
    def pubmed_client(self, mock_settings) -> PubMedClient:
        """Create a PubMedClient with test settings."""
        return PubMedClient(settings=mock_settings)

    @pytest.fixture
    def mock_esearch_response(self) -> dict:
        """Return a mock ESearch JSON response."""
        return {
            "esearchresult": {
                "count": "3",
                "retmax": "3",
                "idlist": ["32970396", "33356052", "34272327"],
                "errorlist": {},
            }
        }

    @pytest.fixture
    def mock_efetch_xml(self) -> str:
        """Return a mock EFetch XML response."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>32970396</PMID>
      <Article>
        <ArticleTitle>Dapagliflozin in Patients with Chronic Kidney Disease</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">CKD is common and treatment options are limited.</AbstractText>
          <AbstractText Label="METHODS">We randomized 4304 participants.</AbstractText>
          <AbstractText Label="RESULTS">Dapagliflozin reduced the primary composite endpoint by 39%.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Heerspink</LastName>
            <ForeName>Hiddo J L</ForeName>
          </Author>
          <Author>
            <LastName>Stefansson</LastName>
            <ForeName>Bergur V</ForeName>
          </Author>
        </AuthorList>
        <Journal>
          <Title>The New England journal of medicine</Title>
          <JournalIssue>
            <PubDate>
              <Year>2020</Year>
              <Month>Oct</Month>
              <Day>08</Day>
            </PubDate>
          </JournalIssue>
        </Journal>
      </Article>
      <MeshHeadingList>
        <MeshHeading>
          <DescriptorName>Diabetes Mellitus, Type 2</DescriptorName>
        </MeshHeading>
        <MeshHeading>
          <DescriptorName>Renal Insufficiency, Chronic</DescriptorName>
        </MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1056/NEJMoa2024816</ArticleId>
        <ArticleId IdType="pmc">PMC7993404</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""

    async def test_search_returns_pmids(self, pubmed_client, mock_esearch_response):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_esearch_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "get", return_value=mock_response) as mock_get:
            pmids = await pubmed_client.search("SGLT2 inhibitors CKD")

        assert len(pmids) == 3
        assert "32970396" in pmids
        assert "33356052" in pmids

    async def test_fetch_articles_parses_xml(self, pubmed_client, mock_efetch_xml):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_efetch_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "post", return_value=mock_response):
            articles = await pubmed_client.fetch_articles(["32970396"])

        assert len(articles) == 1
        article = articles[0]
        assert article["pmid"] == "32970396"
        assert "Dapagliflozin" in article["title"]
        assert len(article["authors"]) == 2
        assert article["authors"][0] == "Heerspink Hiddo J L"
        assert "Diabetes Mellitus, Type 2" in article["mesh_terms"]
        assert article["doi"] == "10.1056/NEJMoa2024816"
        assert article["pmc_id"] == "PMC7993404"

    async def test_fetch_articles_parses_structured_abstract(self, pubmed_client, mock_efetch_xml):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_efetch_xml
        mock_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "post", return_value=mock_response):
            articles = await pubmed_client.fetch_articles(["32970396"])

        abstract = articles[0]["abstract"]
        assert "BACKGROUND:" in abstract
        assert "METHODS:" in abstract
        assert "RESULTS:" in abstract

    async def test_search_and_fetch_combined(self, pubmed_client, mock_esearch_response, mock_efetch_xml):
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = mock_esearch_response
        search_response.raise_for_status = MagicMock()

        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.text = mock_efetch_xml
        fetch_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "get", return_value=search_response), \
             patch.object(pubmed_client._client, "post", return_value=fetch_response):
            articles = await pubmed_client.search_and_fetch("SGLT2 inhibitors CKD")

        assert len(articles) >= 1

    async def test_search_empty_results(self, pubmed_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "esearchresult": {"count": "0", "retmax": "0", "idlist": []}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "get", return_value=mock_response):
            pmids = await pubmed_client.search("nonexistent rare disease xyz123")

        assert pmids == []

    async def test_search_and_fetch_no_results(self, pubmed_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "esearchresult": {"count": "0", "retmax": "0", "idlist": []}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(pubmed_client._client, "get", return_value=mock_response):
            articles = await pubmed_client.search_and_fetch("nonexistent rare disease xyz123")

        assert articles == []

    async def test_fetch_articles_empty_list(self, pubmed_client):
        result = await pubmed_client.fetch_articles([])
        assert result == []

    def test_build_mesh_query_conditions_only(self, pubmed_client):
        query = pubmed_client.build_mesh_query(conditions=["diabetes mellitus, type 2"])
        assert '"diabetes mellitus, type 2"[MeSH Terms]' in query

    def test_build_mesh_query_with_treatments(self, pubmed_client):
        query = pubmed_client.build_mesh_query(
            conditions=["diabetes mellitus, type 2"],
            treatments=["metformin", "insulin"],
        )
        assert '"diabetes mellitus, type 2"[MeSH Terms]' in query
        assert '"metformin"[MeSH Terms]' in query
        assert '"insulin"[MeSH Terms]' in query
        assert " AND " in query

    def test_build_mesh_query_with_date(self, pubmed_client):
        query = pubmed_client.build_mesh_query(
            conditions=["CKD"],
            date_from="2020/01/01",
        )
        assert "2020/01/01" in query
        assert "Date - Publication" in query

    async def test_rate_limit_handling(self, pubmed_client):
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "0.01"}
        rate_limit_response.raise_for_status = MagicMock()

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "esearchresult": {"count": "1", "retmax": "1", "idlist": ["12345"]}
        }
        success_response.raise_for_status = MagicMock()

        # First call rate-limited, second succeeds
        with patch.object(
            pubmed_client._client, "get",
            side_effect=[rate_limit_response, success_response]
        ):
            pmids = await pubmed_client.search("test query")

        assert pmids == ["12345"]


# ═══════════════════════════════════════════════════════════════════════════════
# OpenFDAClient Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestOpenFDAClient:
    """Tests for the OpenFDAClient."""

    @pytest.fixture
    def openfda_client(self, mock_settings) -> OpenFDAClient:
        """Create an OpenFDAClient with test settings."""
        return OpenFDAClient(settings=mock_settings)

    async def test_search_adverse_events_parses_response(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "safetyreportid": "10234567",
                    "serious": "1",
                    "seriousnessdeath": "0",
                    "seriousnesshospitalization": "1",
                    "seriousnesslifethreatening": "0",
                    "seriousnessdisabling": "0",
                    "seriousnesscongenitalanomali": "0",
                    "seriousnessother": "0",
                    "receivedate": "20240315",
                    "patient": {
                        "reaction": [
                            {"reactionmeddrapt": "Nausea", "reactionoutcome": "1"},
                            {"reactionmeddrapt": "Vomiting", "reactionoutcome": "1"},
                        ],
                        "drug": [
                            {
                                "drugcharacterization": "1",
                                "openfda": {"generic_name": ["METFORMIN"]},
                            }
                        ],
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            events = await openfda_client.search_adverse_events("metformin")

        assert len(events) == 1
        event = events[0]
        assert event["safety_report_id"] == "10234567"
        assert "Nausea" in event["reactions"]
        assert "Vomiting" in event["reactions"]
        assert event["seriousness"]["is_serious"] is True
        assert event["seriousness"]["hospitalization"] is True

    async def test_search_adverse_events_handles_404(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            events = await openfda_client.search_adverse_events("nonexistent_drug_xyz")

        assert events == []

    async def test_get_drug_label_extracts_sections(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "openfda": {
                        "brand_name": ["Farxiga"],
                        "generic_name": ["dapagliflozin"],
                    },
                    "warnings": ["Risk of DKA."],
                    "contraindications": ["Severe renal impairment."],
                    "drug_interactions": ["May increase diuretic effect."],
                    "adverse_reactions": ["UTI, genital mycotic infections."],
                    "indications_and_usage": ["Type 2 diabetes, CKD, HF."],
                    "dosage_and_administration": ["10 mg once daily."],
                    "boxed_warning": None,
                    "pregnancy": ["Category C."],
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            label = await openfda_client.get_drug_label("dapagliflozin")

        assert label is not None
        assert label["brand_name"] == "Farxiga"
        assert label["generic_name"] == "dapagliflozin"
        assert "DKA" in label["warnings"]
        assert "10 mg" in label["dosage_and_administration"]

    async def test_get_drug_label_not_found(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            label = await openfda_client.get_drug_label("nonexistent_drug_xyz")

        assert label is None

    async def test_search_drug_recalls(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "recall_number": "D-001-2024",
                    "reason_for_recall": "Contamination",
                    "status": "Ongoing",
                    "classification": "Class II",
                    "product_description": "Metformin 500mg tablets",
                    "recall_initiation_date": "20240101",
                    "voluntary_mandated": "Voluntary",
                    "distribution_pattern": "Nationwide",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            recalls = await openfda_client.search_drug_recalls("metformin")

        assert len(recalls) == 1
        assert recalls[0]["recall_number"] == "D-001-2024"
        assert recalls[0]["classification"] == "Class II"

    async def test_get_adverse_event_counts(self, openfda_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"term": "Nausea", "count": 1500},
                {"term": "Diarrhea", "count": 1200},
                {"term": "Headache", "count": 800},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(openfda_client._client, "get", return_value=mock_response):
            counts = await openfda_client.get_adverse_event_counts("metformin")

        assert counts["drug_name"] == "metformin"
        assert counts["total_reports"] == 3500
        assert len(counts["reaction_counts"]) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# RxNormClient Tests (Mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRxNormClient:
    """Tests for the RxNorm API client (using fixture mock)."""

    async def test_normalize_drug_name(self, mock_rxnorm_client):
        result = await mock_rxnorm_client.normalize_drug_name("dapagliflozin")

        assert result["rxcui"] == "1488574"
        assert "dapagliflozin" in result["name"].lower()

    async def test_find_interactions(self, mock_rxnorm_client):
        result = await mock_rxnorm_client.find_interactions(["metformin", "dapagliflozin"])

        assert len(result) >= 1
        assert result[0]["drug_a"] == "metformin"
        assert result[0]["drug_b"] == "dapagliflozin"

    async def test_approximate_match(self, mock_rxnorm_client):
        result = await mock_rxnorm_client.approximate_match("dapagliflozn")  # typo

        assert len(result) >= 1
        assert result[0]["score"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# DrugBankClient Tests (Mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDrugBankClient:
    """Tests for the DrugBank API client (using fixture mock)."""

    async def test_check_interactions(self, mock_drugbank_client):
        result = await mock_drugbank_client.check_interactions(["metformin", "lisinopril"])

        assert len(result) >= 1
        assert result[0]["drug_a"] == "metformin"
        assert result[0]["drug_b"] == "lisinopril"
        assert result[0]["source"] == "DrugBank"

    async def test_search_drug(self, mock_drugbank_client):
        result = await mock_drugbank_client.search_drug("sitagliptin")

        assert len(result) >= 1
        assert result[0]["name"] == "Sitagliptin"
        assert "DPP-4 Inhibitors" in result[0]["categories"]
