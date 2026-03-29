"""Azure Document Intelligence client wrapper for medical PDF extraction."""

from __future__ import annotations

import re
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient as AzureDocIntelClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import DocumentProcessingError
from cdss.core.logging import get_logger

logger = get_logger(__name__)


class DocumentIntelligenceClient:
    """Extract structured data from medical PDFs using Azure Document Intelligence.

    Provides document analysis for medical documents including lab reports,
    prescriptions, discharge summaries, and clinical notes. Extracts
    structured content including tables, sections, key-value pairs, and
    medical-specific data.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Azure Document Intelligence client.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self._settings = settings or get_settings()

        if not self._settings.azure_document_intelligence_endpoint:
            raise DocumentProcessingError("CDSS_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT is not configured")
        if not self._settings.azure_document_intelligence_key:
            raise DocumentProcessingError("CDSS_AZURE_DOCUMENT_INTELLIGENCE_KEY is not configured")

        self._client = AzureDocIntelClient(
            endpoint=self._settings.azure_document_intelligence_endpoint,
            credential=AzureKeyCredential(
                self._settings.azure_document_intelligence_key
            ),
        )

        logger.info(
            "DocumentIntelligenceClient initialized",
            endpoint=self._settings.azure_document_intelligence_endpoint,
        )

    async def analyze_document(
        self, document_bytes: bytes, model_id: str = "prebuilt-layout"
    ) -> dict:
        """Analyze a document and return structured content.

        Uses the specified model to analyze the document, extracting
        pages, tables, paragraphs, and key-value pairs.

        Args:
            document_bytes: Raw bytes of the document to analyze.
            model_id: Document Intelligence model ID. Options include:
                - "prebuilt-layout": General layout extraction (default).
                - "prebuilt-read": OCR and text extraction.
                - "prebuilt-document": General document with key-value pairs.

        Returns:
            Dict with keys:
                - content (str): Full extracted text content.
                - pages (list[dict]): Per-page information (page_number, width, height, lines).
                - tables (list[dict]): Extracted tables as structured data.
                - paragraphs (list[dict]): Extracted paragraphs with roles.
                - key_value_pairs (list[dict]): Extracted key-value pairs.
                - sections (list[dict]): Document sections (headers + content).

        Raises:
            DocumentProcessingError: If document analysis fails.
        """
        if not document_bytes:
            raise DocumentProcessingError("Empty document bytes provided")

        try:
            logger.debug(
                "Analyzing document",
                model_id=model_id,
                document_size_bytes=len(document_bytes),
            )

            # SDK compatibility:
            # Newer azure-ai-documentintelligence expects `body=...`.
            # Older versions accepted `analyze_request=...`.
            try:
                poller = self._client.begin_analyze_document(
                    model_id=model_id,
                    body=document_bytes,
                    content_type="application/pdf",
                )
            except TypeError:
                try:
                    poller = self._client.begin_analyze_document(
                        model_id=model_id,
                        analyze_request=document_bytes,
                        content_type="application/pdf",
                    )
                except TypeError:
                    poller = self._client.begin_analyze_document(
                        model_id=model_id,
                        analyze_request=AnalyzeDocumentRequest(bytes_source=document_bytes),
                    )
            result = poller.result()

            # Extract pages
            pages: list[dict] = []
            if result.pages:
                for page in result.pages:
                    page_data: dict[str, Any] = {
                        "page_number": page.page_number,
                        "width": page.width,
                        "height": page.height,
                        "unit": page.unit if page.unit else "inch",
                        "lines": [],
                    }
                    if page.lines:
                        for line in page.lines:
                            page_data["lines"].append({
                                "content": line.content,
                                "polygon": line.polygon if line.polygon else [],
                            })
                    pages.append(page_data)

            # Extract tables
            tables = self.extract_tables({"_raw_result": result})

            # Extract paragraphs
            paragraphs: list[dict] = []
            if result.paragraphs:
                for paragraph in result.paragraphs:
                    para_data: dict[str, Any] = {
                        "content": paragraph.content,
                        "role": paragraph.role if paragraph.role else "body",
                    }
                    if paragraph.bounding_regions:
                        para_data["page_number"] = (
                            paragraph.bounding_regions[0].page_number
                        )
                    paragraphs.append(para_data)

            # Extract key-value pairs
            key_value_pairs: list[dict] = []
            if result.key_value_pairs:
                for kvp in result.key_value_pairs:
                    key_text = kvp.key.content if kvp.key else ""
                    value_text = kvp.value.content if kvp.value else ""
                    confidence = kvp.confidence if kvp.confidence else 0.0
                    key_value_pairs.append({
                        "key": key_text,
                        "value": value_text,
                        "confidence": confidence,
                    })

            # Extract sections
            sections = self.extract_sections({
                "_raw_result": result,
                "paragraphs": paragraphs,
            })

            analysis_result = {
                "content": result.content or "",
                "pages": pages,
                "tables": tables,
                "paragraphs": paragraphs,
                "key_value_pairs": key_value_pairs,
                "sections": sections,
            }

            logger.info(
                "Document analysis completed",
                model_id=model_id,
                page_count=len(pages),
                table_count=len(tables),
                paragraph_count=len(paragraphs),
                kvp_count=len(key_value_pairs),
                section_count=len(sections),
            )

            return analysis_result

        except DocumentProcessingError:
            raise
        except Exception as exc:
            logger.error(
                "Document analysis failed",
                model_id=model_id,
                document_size_bytes=len(document_bytes),
                error=str(exc),
            )
            raise DocumentProcessingError(
                f"Document analysis failed with model '{model_id}': {exc}"
            ) from exc

    async def analyze_medical_pdf(self, pdf_bytes: bytes) -> dict:
        """Specialized analysis for medical PDFs (lab reports, prescriptions).

        Uses the layout model to extract content, then post-processes to
        identify and structure medical-specific data such as patient info,
        dates, test results, and medications.

        Args:
            pdf_bytes: Raw bytes of the medical PDF.

        Returns:
            Dict with keys:
                - raw_content (str): Full extracted text.
                - patient_info (dict): Extracted patient information.
                - dates (list[str]): Extracted dates found in the document.
                - test_results (list[dict]): Extracted lab test results.
                - medications (list[dict]): Extracted medication information.
                - tables (list[dict]): Structured table data.
                - sections (list[dict]): Document sections.
                - key_value_pairs (list[dict]): Key-value pairs from the document.

        Raises:
            DocumentProcessingError: If analysis or post-processing fails.
        """
        logger.debug(
            "Analyzing medical PDF",
            pdf_size_bytes=len(pdf_bytes),
        )

        try:
            # First, get the raw analysis
            analysis = await self.analyze_document(
                document_bytes=pdf_bytes,
                model_id="prebuilt-layout",
            )

            content = analysis["content"]

            # Post-process: Extract patient information from key-value pairs
            patient_info = self._extract_patient_info(
                analysis["key_value_pairs"], content
            )

            # Post-process: Extract dates
            dates = self._extract_dates(content)

            # Post-process: Extract test results from tables and content
            test_results = self._extract_test_results(analysis["tables"], content)

            # Post-process: Extract medication information
            medications = self._extract_medications(
                analysis["key_value_pairs"], content
            )

            medical_data = {
                "raw_content": content,
                "patient_info": patient_info,
                "dates": dates,
                "test_results": test_results,
                "medications": medications,
                "tables": analysis["tables"],
                "sections": analysis["sections"],
                "key_value_pairs": analysis["key_value_pairs"],
            }

            logger.info(
                "Medical PDF analysis completed",
                dates_found=len(dates),
                test_results_found=len(test_results),
                medications_found=len(medications),
                has_patient_info=bool(patient_info),
            )

            return medical_data

        except DocumentProcessingError:
            raise
        except Exception as exc:
            logger.error(
                "Medical PDF analysis failed",
                error=str(exc),
            )
            raise DocumentProcessingError(
                f"Medical PDF analysis failed: {exc}"
            ) from exc

    def extract_tables(self, result: dict) -> list[dict]:
        """Extract tables from analysis result as structured data.

        Args:
            result: Analysis result dict. If it contains '_raw_result',
                    that raw API result object is used. Otherwise, the
                    dict is treated as pre-processed.

        Returns:
            List of table dicts, each with keys:
                - table_index (int): Zero-based table index.
                - row_count (int): Number of rows.
                - column_count (int): Number of columns.
                - cells (list[dict]): Cell data with row_index, column_index, content, kind.
                - headers (list[str]): Column header values.
                - rows (list[list[str]]): Row data as lists of cell values.
        """
        raw_result = result.get("_raw_result")

        tables: list[dict] = []

        if raw_result is not None and hasattr(raw_result, "tables") and raw_result.tables:
            for idx, table in enumerate(raw_result.tables):
                table_data: dict[str, Any] = {
                    "table_index": idx,
                    "row_count": table.row_count,
                    "column_count": table.column_count,
                    "cells": [],
                    "headers": [],
                    "rows": [],
                }

                # Build a grid for easier access
                grid: dict[tuple[int, int], str] = {}

                if table.cells:
                    for cell in table.cells:
                        cell_data = {
                            "row_index": cell.row_index,
                            "column_index": cell.column_index,
                            "content": cell.content or "",
                            "kind": cell.kind if cell.kind else "content",
                        }
                        table_data["cells"].append(cell_data)
                        grid[(cell.row_index, cell.column_index)] = cell.content or ""

                # Extract headers (row 0 or cells marked as columnHeader)
                header_cells = [
                    c for c in table_data["cells"] if c["kind"] == "columnHeader"
                ]
                if header_cells:
                    max_col = max(c["column_index"] for c in header_cells) + 1
                    headers = [""] * max_col
                    for c in header_cells:
                        headers[c["column_index"]] = c["content"]
                    table_data["headers"] = headers
                else:
                    # Fallback: use row 0 as headers
                    table_data["headers"] = [
                        grid.get((0, col), "")
                        for col in range(table.column_count)
                    ]

                # Extract data rows (skip header row)
                start_row = 1 if table_data["headers"] else 0
                for row_idx in range(start_row, table.row_count):
                    row = [
                        grid.get((row_idx, col), "")
                        for col in range(table.column_count)
                    ]
                    table_data["rows"].append(row)

                tables.append(table_data)

        logger.debug("Tables extracted", table_count=len(tables))
        return tables

    def extract_sections(self, result: dict) -> list[dict]:
        """Extract document sections grouped by headers and their content.

        Args:
            result: Analysis result dict containing 'paragraphs' (list of
                    paragraph dicts with 'content' and 'role' keys).

        Returns:
            List of section dicts, each with keys:
                - heading (str): Section heading text.
                - level (int): Heading level (1 for title, 2 for sectionHeading, 3 for others).
                - content (str): Combined content text under the heading.
                - paragraphs (list[str]): Individual paragraph texts in the section.
        """
        paragraphs = result.get("paragraphs", [])

        if not paragraphs:
            return []

        heading_roles = {"title", "sectionHeading", "pageHeader"}
        sections: list[dict] = []
        current_section: dict[str, Any] | None = None

        for para in paragraphs:
            role = para.get("role", "body")
            content = para.get("content", "").strip()

            if not content:
                continue

            if role in heading_roles:
                # Save previous section
                if current_section is not None:
                    current_section["content"] = "\n\n".join(
                        current_section["paragraphs"]
                    )
                    sections.append(current_section)

                level = 1 if role == "title" else (2 if role == "sectionHeading" else 3)
                current_section = {
                    "heading": content,
                    "level": level,
                    "content": "",
                    "paragraphs": [],
                }
            else:
                if current_section is None:
                    # Content before any heading; create an implicit section
                    current_section = {
                        "heading": "",
                        "level": 0,
                        "content": "",
                        "paragraphs": [],
                    }
                current_section["paragraphs"].append(content)

        # Don't forget the last section
        if current_section is not None:
            current_section["content"] = "\n\n".join(current_section["paragraphs"])
            sections.append(current_section)

        logger.debug("Sections extracted", section_count=len(sections))
        return sections

    # -------------------------------------------------------------------------
    # Private post-processing helpers for medical PDF analysis
    # -------------------------------------------------------------------------

    def _extract_patient_info(
        self, key_value_pairs: list[dict], content: str
    ) -> dict:
        """Extract patient information from key-value pairs and content.

        Args:
            key_value_pairs: Key-value pairs extracted from the document.
            content: Full text content of the document.

        Returns:
            Dict with patient information fields (name, dob, gender, mrn, etc.).
        """
        patient_info: dict[str, str] = {}

        # Known patient info key patterns (case-insensitive)
        patient_key_patterns = {
            "name": ["patient name", "name", "patient"],
            "dob": ["date of birth", "dob", "birth date", "d.o.b"],
            "gender": ["gender", "sex"],
            "mrn": ["mrn", "medical record number", "record number", "patient id"],
            "age": ["age"],
            "address": ["address"],
            "phone": ["phone", "telephone", "contact"],
            "insurance": ["insurance", "insurance id", "policy number"],
        }

        for kvp in key_value_pairs:
            key_lower = kvp["key"].lower().strip().rstrip(":")
            value = kvp["value"].strip()

            if not value:
                continue

            for field_name, patterns in patient_key_patterns.items():
                for pattern in patterns:
                    if pattern in key_lower:
                        patient_info[field_name] = value
                        break

        # Fallback: try regex patterns on full content if key fields are missing
        if "mrn" not in patient_info:
            mrn_match = re.search(r"MRN[:\s#]*([A-Z0-9-]+)", content, re.IGNORECASE)
            if mrn_match:
                patient_info["mrn"] = mrn_match.group(1)

        if "dob" not in patient_info:
            dob_match = re.search(
                r"(?:DOB|Date of Birth)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
                content,
                re.IGNORECASE,
            )
            if dob_match:
                patient_info["dob"] = dob_match.group(1)

        return patient_info

    def _extract_dates(self, content: str) -> list[str]:
        """Extract all dates found in the document content.

        Args:
            content: Full text content of the document.

        Returns:
            List of date strings found in the document, deduplicated.
        """
        date_patterns = [
            # MM/DD/YYYY or MM-DD-YYYY
            r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b",
            # YYYY-MM-DD
            r"\b(\d{4}-\d{2}-\d{2})\b",
            # Month DD, YYYY
            r"\b((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
            # DD Mon YYYY
            r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"[a-z]*\s+\d{4})\b",
        ]

        dates: list[str] = []
        seen: set[str] = set()

        for pattern in date_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                normalized = match.strip()
                if normalized not in seen:
                    seen.add(normalized)
                    dates.append(normalized)

        return dates

    def _extract_test_results(
        self, tables: list[dict], content: str
    ) -> list[dict]:
        """Extract lab test results from tables and content.

        Args:
            tables: Extracted table data from the document.
            content: Full text content of the document.

        Returns:
            List of test result dicts with keys: test_name, value,
            unit, reference_range, flag.
        """
        test_results: list[dict] = []

        # Extract from tables that look like lab results
        lab_result_headers = {"test", "result", "value", "reference", "range", "unit", "flag"}

        for table in tables:
            headers_lower = [h.lower() for h in table.get("headers", [])]
            header_overlap = set(headers_lower) & lab_result_headers

            if len(header_overlap) >= 2:
                # This table likely contains lab results
                header_map: dict[str, int] = {}
                for col_idx, header in enumerate(headers_lower):
                    if "test" in header or "name" in header or "analyte" in header:
                        header_map["test_name"] = col_idx
                    elif "result" in header or "value" in header:
                        header_map["value"] = col_idx
                    elif "unit" in header:
                        header_map["unit"] = col_idx
                    elif "reference" in header or "range" in header or "normal" in header:
                        header_map["reference_range"] = col_idx
                    elif "flag" in header or "status" in header or "abnormal" in header:
                        header_map["flag"] = col_idx

                for row in table.get("rows", []):
                    if not any(cell.strip() for cell in row):
                        continue

                    result_entry: dict[str, str] = {
                        "test_name": "",
                        "value": "",
                        "unit": "",
                        "reference_range": "",
                        "flag": "",
                    }

                    for field, col_idx in header_map.items():
                        if col_idx < len(row):
                            result_entry[field] = row[col_idx].strip()

                    if result_entry["test_name"] or result_entry["value"]:
                        test_results.append(result_entry)

        # Fallback: try regex patterns on content for inline results
        if not test_results:
            inline_pattern = re.compile(
                r"([A-Za-z\s]+?)\s*:\s*"
                r"([\d.,]+)\s*"
                r"([a-zA-Z/%]+)?\s*"
                r"(?:\(?([\d.,\-\s]+(?:[a-zA-Z/%]+)?)\)?)?"
            )

            for match in inline_pattern.finditer(content):
                test_name = match.group(1).strip()
                value = match.group(2).strip()
                unit = (match.group(3) or "").strip()
                ref_range = (match.group(4) or "").strip()

                # Filter out non-test matches (too short or common words)
                if len(test_name) < 2 or test_name.lower() in {
                    "page", "date", "time", "age", "phone", "fax",
                }:
                    continue

                test_results.append({
                    "test_name": test_name,
                    "value": value,
                    "unit": unit,
                    "reference_range": ref_range,
                    "flag": "",
                })

        return test_results

    def _extract_medications(
        self, key_value_pairs: list[dict], content: str
    ) -> list[dict]:
        """Extract medication information from the document.

        Args:
            key_value_pairs: Key-value pairs from document analysis.
            content: Full text content of the document.

        Returns:
            List of medication dicts with keys: name, dosage, frequency, route.
        """
        medications: list[dict] = []

        # Check key-value pairs for medication-related entries
        medication_keys = {"medication", "drug", "prescription", "rx", "medicine"}
        for kvp in key_value_pairs:
            key_lower = kvp["key"].lower().strip().rstrip(":")
            if any(med_key in key_lower for med_key in medication_keys):
                value = kvp["value"].strip()
                if value:
                    medications.append({
                        "name": value,
                        "dosage": "",
                        "frequency": "",
                        "route": "",
                    })

        # Regex-based extraction for common medication patterns
        # Pattern: Drug Name DosageMg Route Frequency
        med_pattern = re.compile(
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+"
            r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?|IU))\s*"
            r"(?:(PO|IV|IM|SC|SQ|SL|PR|topical|inhaled|oral|intravenous)\s*)?"
            r"(?:(once daily|twice daily|BID|TID|QID|QD|PRN|daily|"
            r"every\s+\d+\s+hours?|q\d+h|qhs|qam))?",
            re.IGNORECASE,
        )

        for match in med_pattern.finditer(content):
            name = match.group(1).strip()
            dosage = match.group(2).strip()
            route = (match.group(3) or "").strip()
            frequency = (match.group(4) or "").strip()

            # Avoid duplicates
            if not any(
                m["name"].lower() == name.lower() and m["dosage"] == dosage
                for m in medications
            ):
                medications.append({
                    "name": name,
                    "dosage": dosage,
                    "frequency": frequency,
                    "route": route,
                })

        return medications
