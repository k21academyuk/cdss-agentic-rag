"""Drug Safety Agent for the Clinical Decision Support System.

Checks drug-drug interactions via RxNorm normalization, queries DrugBank
for DDIs, fetches FDA adverse event data from OpenFDA, checks allergy
cross-reactivity, and synthesizes a comprehensive safety report using
GPT-4o.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from cdss.agents.base import BaseAgent
from cdss.clients.drugbank_client import DrugBankClient
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.clients.openfda_client import OpenFDAClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AgentError, DrugSafetyError
from cdss.core.models import (
    AgentTask,
    DrugAlert,
    DrugInteraction,
    DrugSafetyReport,
)


class DrugSafetyAgent(BaseAgent):
    """Checks drug-drug interactions, adverse events, and safety concerns.

    Tools:
    - drugbank_ddi_check(drug_list)
    - openfda_adverse_events(drug, condition)
    - rxnorm_normalize(drug_name)

    Model: GPT-4o
    Output: DrugSafetyReport
    """

    # Known cross-reactivity groups for allergy checking
    CROSS_REACTIVITY_GROUPS: dict[str, list[str]] = {
        "penicillin": [
            "amoxicillin", "ampicillin", "piperacillin", "nafcillin",
            "oxacillin", "dicloxacillin", "penicillin v", "penicillin g",
        ],
        "cephalosporin": [
            "cephalexin", "cefazolin", "ceftriaxone", "cefuroxime",
            "cefpodoxime", "cefdinir", "cefepime", "ceftazidime",
        ],
        "sulfonamide": [
            "sulfamethoxazole", "sulfasalazine", "sulfadiazine",
            "trimethoprim-sulfamethoxazole", "bactrim",
        ],
        "nsaid": [
            "ibuprofen", "naproxen", "aspirin", "celecoxib", "meloxicam",
            "diclofenac", "indomethacin", "ketorolac", "piroxicam",
        ],
        "ace_inhibitor": [
            "lisinopril", "enalapril", "ramipril", "captopril",
            "benazepril", "fosinopril", "quinapril", "perindopril",
        ],
        "statin": [
            "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
            "lovastatin", "fluvastatin", "pitavastatin",
        ],
    }

    def __init__(
        self,
        rxnorm_client: Any | None = None,
        openfda_client: OpenFDAClient | None = None,
        drugbank_client: Any | None = None,
        openai_client: AzureOpenAIClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the DrugSafetyAgent.

        Args:
            rxnorm_client: RxNorm REST API client for drug normalization.
                If None, a built-in httpx client is used.
            openfda_client: OpenFDA client for adverse event data.
            drugbank_client: DrugBank API client for DDI checks.
                If None, interaction checking falls back to RxNorm.
            openai_client: Azure OpenAI client for safety synthesis.
            settings: Application settings.
        """
        super().__init__(name="drug_safety_agent", model="gpt-4o")
        self._settings = settings or get_settings()
        self._rxnorm_client = rxnorm_client
        self._openfda_client = openfda_client or OpenFDAClient(settings=self._settings)
        self._drugbank_client = drugbank_client
        if self._drugbank_client is None and self._settings.drugbank_api_key.strip():
            try:
                self._drugbank_client = DrugBankClient(settings=self._settings)
                self.logger.info("DrugBank client enabled for interaction enrichment")
            except Exception as exc:
                self.logger.warning(
                    "Failed to initialize DrugBank client; continuing with RxNorm-only interactions",
                    extra={"error": str(exc)},
                )
        self._openai_client = openai_client or AzureOpenAIClient(settings=self._settings)
        self._rxnorm_base_url = self._settings.rxnorm_base_url
        self._http_client = httpx.AsyncClient(timeout=15.0)

    async def _execute(self, task: AgentTask) -> dict:
        """Check drug interactions and safety.

        Query Flow:
        1. Normalize drug names via RxNorm -> RxCUI
        2. Check DrugBank for DDIs (severity classification)
        3. Query OpenFDA for adverse event signals
        4. Merge results: DDI severity + real-world adverse event frequency
        5. Use GPT-4o to synthesize safety report with alternatives
        6. Return DrugSafetyReport

        Args:
            task: Agent task with payload containing ``medications`` (current list),
                  ``proposed_medications`` (new medications to check), ``conditions``,
                  and ``allergies``.

        Returns:
            Dictionary containing ``summary``, ``sources_retrieved``, and
            ``drug_safety_report`` (serialized DrugSafetyReport).
        """
        medications = task.payload.get("medications", [])
        proposed_medications = task.payload.get("proposed_medications", [])
        conditions = task.payload.get("conditions", [])
        allergies = task.payload.get("allergies", [])

        all_drug_names = self._extract_drug_names(medications, proposed_medications)

        if not all_drug_names:
            self.logger.info("No medications to check for drug safety")
            return {
                "summary": "No medications provided for safety checking.",
                "sources_retrieved": 0,
                "drug_safety_report": DrugSafetyReport(
                    interactions=[],
                    adverse_events=[],
                    alternatives=[],
                    dosage_adjustments=[],
                ).model_dump(),
            }

        self.logger.info(
            "Starting drug safety check",
            extra={
                "current_medications": len(medications),
                "proposed_medications": len(proposed_medications),
                "total_drugs": len(all_drug_names),
                "allergies_count": len(allergies),
            },
        )

        # Step 1: Normalize all drug names via RxNorm
        rxcui_map = await self._normalize_drugs(all_drug_names)
        sources_count = len(rxcui_map)

        # Step 2: Check DDIs via DrugBank or RxNorm interactions as fallback
        interactions = await self._check_drug_interactions(all_drug_names, rxcui_map)
        sources_count += len(interactions)

        # Step 3: Query OpenFDA for adverse events
        adverse_events = await self._check_adverse_events(all_drug_names)
        sources_count += len(adverse_events)

        # Step 4: Check allergy cross-reactivity
        allergy_alerts = await self._check_allergy_crossreactivity(allergies, all_drug_names)

        # Step 5: Use GPT-4o to synthesize comprehensive safety report
        synthesis = await self._synthesize_safety_report(
            drug_names=all_drug_names,
            interactions=interactions,
            adverse_events=adverse_events,
            allergy_alerts=allergy_alerts,
            conditions=conditions,
            proposed_medications=proposed_medications,
        )

        # Step 6: Build and return DrugSafetyReport
        # Convert interactions to model format
        interaction_models: list[DrugInteraction] = []
        for ddi in interactions:
            try:
                severity = ddi.get("severity", "moderate")
                if severity not in ("minor", "moderate", "major"):
                    severity = "moderate"
                interaction_models.append(
                    DrugInteraction(
                        drug_a=ddi.get("drug_a", ""),
                        drug_b=ddi.get("drug_b", ""),
                        severity=severity,
                        description=ddi.get("description", ""),
                        evidence_level=int(ddi.get("evidence_level", 3)),
                        source=ddi.get("source", "RxNorm"),
                        clinical_significance=ddi.get("clinical_significance"),
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    "Skipping malformed interaction record",
                    extra={"error": str(exc)},
                )

        # Convert allergy alerts to DrugAlert format
        drug_alert_models: list[DrugAlert] = []
        for alert in allergy_alerts:
            try:
                drug_alert_models.append(
                    DrugAlert(
                        severity=alert.get("severity", "major"),
                        description=alert.get("description", ""),
                        source=alert.get("source", "Allergy cross-reactivity check"),
                        evidence_level=int(alert.get("evidence_level", 2)),
                        alternatives=alert.get("alternatives", []),
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    "Skipping malformed allergy alert",
                    extra={"error": str(exc)},
                )

        report = DrugSafetyReport(
            interactions=interaction_models,
            adverse_events=adverse_events,
            alternatives=synthesis.get("alternatives", []),
            dosage_adjustments=synthesis.get("dosage_adjustments", []),
        )

        summary = synthesis.get("summary", self._build_fallback_summary(interactions, allergy_alerts))

        self.logger.info(
            "Drug safety check completed",
            extra={
                "interactions_found": len(interaction_models),
                "adverse_events_checked": len(adverse_events),
                "allergy_alerts": len(drug_alert_models),
                "alternatives_suggested": len(report.alternatives),
            },
        )

        return {
            "summary": summary,
            "sources_retrieved": sources_count,
            "drug_safety_report": report.model_dump(),
            "drug_alerts": [a.model_dump() for a in drug_alert_models],
            "rxcui_map": rxcui_map,
        }

    def _extract_drug_names(
        self,
        medications: list[dict | str],
        proposed_medications: list[dict | str],
    ) -> list[str]:
        """Extract drug name strings from medication data.

        Handles both dict format (with ``name`` key) and plain string format.

        Args:
            medications: Current medications.
            proposed_medications: Newly proposed medications.

        Returns:
            Deduplicated list of drug name strings.
        """
        names: list[str] = []
        seen: set[str] = set()

        for med in medications + proposed_medications:
            if isinstance(med, dict):
                name = med.get("name", med.get("drug_name", ""))
            else:
                name = str(med)

            # Extract just the drug name (strip dosage info)
            name = name.strip()
            if name:
                name_lower = name.lower()
                if name_lower not in seen:
                    seen.add(name_lower)
                    names.append(name)

        return names

    async def _normalize_drugs(self, drug_names: list[str]) -> dict[str, str]:
        """Normalize drug names to RxCUI via RxNorm REST API.

        Args:
            drug_names: List of drug name strings.

        Returns:
            Dictionary mapping drug name to RxCUI string.
            Drugs that could not be normalized will have an empty RxCUI.
        """
        rxcui_map: dict[str, str] = {}

        normalization_tasks = [
            self._normalize_single_drug(name)
            for name in drug_names
        ]

        results = await asyncio.gather(*normalization_tasks, return_exceptions=True)

        for name, result in zip(drug_names, results):
            if isinstance(result, Exception):
                self.logger.warning(
                    "RxNorm normalization failed for drug",
                    extra={"drug_name": name, "error": str(result)},
                )
                rxcui_map[name] = ""
            else:
                rxcui_map[name] = result

        normalized_count = sum(1 for v in rxcui_map.values() if v)
        self.logger.info(
            "Drug normalization completed",
            extra={
                "total_drugs": len(drug_names),
                "normalized_count": normalized_count,
            },
        )
        return rxcui_map

    async def _normalize_single_drug(self, drug_name: str) -> str:
        """Normalize a single drug name to its RxCUI via the RxNorm REST API.

        Args:
            drug_name: The drug name to normalize.

        Returns:
            The RxCUI string, or empty string if not found.
        """
        try:
            url = f"{self._rxnorm_base_url}/rxcui.json"
            params = {"name": drug_name, "search": "1"}
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            id_group = data.get("idGroup", {})
            rxnorm_id_list = id_group.get("rxnormId", [])

            if rxnorm_id_list:
                rxcui = rxnorm_id_list[0]
                self.logger.debug(
                    "Drug normalized",
                    extra={"drug_name": drug_name, "rxcui": rxcui},
                )
                return str(rxcui)

            # Try approximate match
            url_approx = f"{self._rxnorm_base_url}/approximateTerm.json"
            params_approx = {"term": drug_name, "maxEntries": "1"}
            response_approx = await self._http_client.get(url_approx, params=params_approx)
            response_approx.raise_for_status()

            data_approx = response_approx.json()
            candidates = data_approx.get("approximateGroup", {}).get("candidate", [])
            if candidates:
                rxcui = candidates[0].get("rxcui", "")
                if rxcui:
                    self.logger.debug(
                        "Drug normalized via approximate match",
                        extra={"drug_name": drug_name, "rxcui": rxcui},
                    )
                    return str(rxcui)

            self.logger.debug(
                "Drug could not be normalized",
                extra={"drug_name": drug_name},
            )
            return ""

        except Exception as exc:
            self.logger.warning(
                "RxNorm API call failed",
                extra={"drug_name": drug_name, "error": str(exc)},
            )
            return ""

    async def _check_drug_interactions(
        self, drug_names: list[str], rxcui_map: dict[str, str]
    ) -> list[dict]:
        """Check drug-drug interactions via RxNorm interaction API.

        Uses the RxNorm interaction endpoint as the primary source.
        If a DrugBank client is available, it is also queried.

        Args:
            drug_names: List of drug names.
            rxcui_map: Mapping of drug names to RxCUI identifiers.

        Returns:
            List of interaction dictionaries with keys: ``drug_a``, ``drug_b``,
            ``severity``, ``description``, ``evidence_level``, ``source``.
        """
        interactions: list[dict] = []

        # Get all valid RxCUIs
        valid_rxcuis = {
            name: rxcui for name, rxcui in rxcui_map.items() if rxcui
        }

        if len(valid_rxcuis) < 2:
            self.logger.info(
                "Fewer than 2 normalized drugs, skipping DDI check",
                extra={"valid_rxcuis_count": len(valid_rxcuis)},
            )
            return interactions

        rxcui_list = list(valid_rxcuis.values())
        rxcui_to_name = {v: k for k, v in valid_rxcuis.items()}

        try:
            interactions.extend(
                await self._check_rxnorm_interactions(
                    rxcui_list=rxcui_list,
                    rxcui_to_name=rxcui_to_name,
                )
            )

            self.logger.info(
                "RxNorm DDI check completed",
                extra={
                    "rxcuis_checked": len(rxcui_list),
                    "interactions_found": len(interactions),
                },
            )

        except Exception as exc:
            self.logger.warning(
                "RxNorm interaction check failed",
                extra={"error": str(exc)},
            )

        # Fallback: derive explicit pair interactions from OpenFDA drug labels.
        # This preserves structured interaction output even when RxNorm
        # interaction endpoints are unavailable.
        if not interactions:
            try:
                label_interactions = await self._check_openfda_label_interactions(drug_names)
                if label_interactions:
                    self.logger.info(
                        "OpenFDA label interaction fallback produced interactions",
                        extra={"interactions_found": len(label_interactions)},
                    )
                    interactions.extend(label_interactions)
            except Exception as exc:
                self.logger.warning(
                    "OpenFDA label interaction fallback failed",
                    extra={"error": str(exc)},
                )

        # Also check DrugBank if client is available
        if self._drugbank_client is not None:
            try:
                drugbank_interactions = await self._check_drugbank_interactions(
                    drug_names, rxcui_map
                )
                interactions.extend(drugbank_interactions)
            except Exception as exc:
                self.logger.warning(
                    "DrugBank interaction check failed",
                    extra={"error": str(exc)},
                )

        return self._deduplicate_interactions(interactions)

    async def _check_rxnorm_interactions(
        self,
        rxcui_list: list[str],
        rxcui_to_name: dict[str, str],
    ) -> list[dict]:
        """Fetch RxNorm interactions with fallback for endpoint incompatibilities."""
        selected_rxcuis = set(rxcui_list)
        interactions: list[dict] = []

        list_url = f"{self._rxnorm_base_url}/interaction/list.json"
        list_params = {"rxcuis": "+".join(rxcui_list)}
        response = await self._http_client.get(list_url, params=list_params)

        if response.status_code < 400:
            interactions.extend(
                self._parse_rxnorm_interaction_payload(
                    payload=response.json(),
                    selected_rxcuis=selected_rxcuis,
                    rxcui_to_name=rxcui_to_name,
                )
            )
            return interactions

        # Some RxNorm deployments return 404 for list endpoint. Fallback
        # to per-RxCUI endpoint and keep only pairings inside the selected set.
        self.logger.warning(
            "RxNorm interaction list endpoint unavailable, using per-RxCUI fallback",
            extra={"status_code": response.status_code, "url": list_url},
        )

        fallback_url = f"{self._rxnorm_base_url}/interaction/interaction.json"
        for index, rxcui in enumerate(rxcui_list):
            fallback_response = await self._http_client.get(fallback_url, params={"rxcui": rxcui})
            if fallback_response.status_code >= 400:
                if fallback_response.status_code == 404 and index == 0:
                    self.logger.warning(
                        "RxNorm per-RxCUI endpoint unavailable; skipping remaining fallback calls",
                        extra={"status_code": fallback_response.status_code, "url": fallback_url},
                    )
                    break
                self.logger.warning(
                    "RxNorm per-RxCUI interaction lookup failed",
                    extra={"rxcui": rxcui, "status_code": fallback_response.status_code},
                )
                continue

            interactions.extend(
                self._parse_rxnorm_interaction_payload(
                    payload=fallback_response.json(),
                    selected_rxcuis=selected_rxcuis,
                    rxcui_to_name=rxcui_to_name,
                )
            )

        return interactions

    def _parse_rxnorm_interaction_payload(
        self,
        payload: dict,
        selected_rxcuis: set[str],
        rxcui_to_name: dict[str, str],
    ) -> list[dict]:
        """Parse interaction payloads from both list and per-RxCUI RxNorm endpoints."""
        interactions: list[dict] = []
        groups = payload.get("fullInteractionTypeGroup", [])
        for group in groups:
            source_name = group.get("sourceName", "RxNorm")
            for interaction_type in group.get("fullInteractionType", []):
                for pair in interaction_type.get("interactionPair", []):
                    record = self._build_rxnorm_interaction_record(
                        pair=pair,
                        source_name=source_name,
                        selected_rxcuis=selected_rxcuis,
                        rxcui_to_name=rxcui_to_name,
                    )
                    if record is not None:
                        interactions.append(record)

        # Fallback format seen in per-rxcui endpoint.
        if interactions:
            return interactions

        alt_groups = payload.get("interactionTypeGroup", [])
        for group in alt_groups:
            source_name = group.get("sourceName", "RxNorm")
            for interaction_type in group.get("interactionType", []):
                for pair in interaction_type.get("interactionPair", []):
                    record = self._build_rxnorm_interaction_record(
                        pair=pair,
                        source_name=source_name,
                        selected_rxcuis=selected_rxcuis,
                        rxcui_to_name=rxcui_to_name,
                    )
                    if record is not None:
                        interactions.append(record)

        return interactions

    def _build_rxnorm_interaction_record(
        self,
        pair: dict,
        source_name: str,
        selected_rxcuis: set[str],
        rxcui_to_name: dict[str, str],
    ) -> dict | None:
        """Normalize an RxNorm interaction pair to a CDSS interaction record."""
        interaction_concepts = pair.get("interactionConcept", [])
        if len(interaction_concepts) < 2:
            return None

        drug_a_min = interaction_concepts[0].get("minConceptItem", {})
        drug_b_min = interaction_concepts[1].get("minConceptItem", {})
        drug_a_rxcui = str(drug_a_min.get("rxcui", "")).strip()
        drug_b_rxcui = str(drug_b_min.get("rxcui", "")).strip()
        if not drug_a_rxcui or not drug_b_rxcui:
            return None
        if drug_a_rxcui not in selected_rxcuis or drug_b_rxcui not in selected_rxcuis:
            return None

        drug_a_name = rxcui_to_name.get(drug_a_rxcui, str(drug_a_min.get("name", "Unknown")))
        drug_b_name = rxcui_to_name.get(drug_b_rxcui, str(drug_b_min.get("name", "Unknown")))
        description = str(pair.get("description", "")).strip()
        severity_text = str(pair.get("severity", "")).strip().lower()

        return {
            "drug_a": drug_a_name,
            "drug_b": drug_b_name,
            "severity": self._map_severity_label(severity_text),
            "description": description,
            "evidence_level": 2,
            "source": source_name or "RxNorm",
            "clinical_significance": severity_text,
        }

    def _map_severity_label(self, severity_text: str) -> str:
        """Map free-text severity descriptions to the CDSS severity taxonomy."""
        if "contraindicated" in severity_text or "high" in severity_text or "major" in severity_text:
            return "major"
        if "moderate" in severity_text:
            return "moderate"
        if "low" in severity_text or "minor" in severity_text:
            return "minor"
        return "moderate"

    def _deduplicate_interactions(self, interactions: list[dict]) -> list[dict]:
        """Drop duplicate interaction entries returned by multiple RxNorm paths."""
        unique: list[dict] = []
        seen: set[tuple[str, str, str, str]] = set()
        for interaction in interactions:
            drug_a = str(interaction.get("drug_a", "")).strip().lower()
            drug_b = str(interaction.get("drug_b", "")).strip().lower()
            if not drug_a or not drug_b:
                continue
            pair_key = tuple(sorted((drug_a, drug_b)))
            source = str(interaction.get("source", "")).strip().lower()
            description = str(interaction.get("description", "")).strip().lower()
            dedupe_key = (pair_key[0], pair_key[1], source, description)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            unique.append(interaction)
        return unique

    async def _check_drugbank_interactions(
        self, drug_names: list[str], _rxcui_map: dict[str, str]
    ) -> list[dict]:
        """Check drug interactions via DrugBank API.

        Args:
            drug_names: List of drug names.
            rxcui_map: Mapping of drug names to RxCUI identifiers.

        Returns:
            List of interaction dictionaries from DrugBank.
        """
        if self._drugbank_client is None:
            return []

        interactions: list[dict] = []
        try:
            if hasattr(self._drugbank_client, "check_interactions"):
                raw_results = await self._drugbank_client.check_interactions(drug_names)
                for entry in raw_results:
                    drug_a_raw = entry.get("drug_a", {})
                    drug_b_raw = entry.get("drug_b", {})
                    drug_a = drug_a_raw.get("name", "") if isinstance(drug_a_raw, dict) else str(drug_a_raw)
                    drug_b = drug_b_raw.get("name", "") if isinstance(drug_b_raw, dict) else str(drug_b_raw)
                    if not drug_a or not drug_b:
                        continue
                    interactions.append(
                        {
                            "drug_a": drug_a,
                            "drug_b": drug_b,
                            "severity": self._map_severity_label(str(entry.get("severity", "")).lower()),
                            "description": entry.get("description", ""),
                            "evidence_level": int(entry.get("evidence_level", 2) or 2),
                            "source": "DrugBank",
                            "clinical_significance": entry.get("clinical_significance", ""),
                        }
                    )
                return interactions

            # Legacy compatibility for clients exposing pairwise check_interaction.
            if hasattr(self._drugbank_client, "check_interaction"):
                for i, drug_a in enumerate(drug_names):
                    for drug_b in drug_names[i + 1:]:
                        result = await self._drugbank_client.check_interaction(drug_a, drug_b)
                        if result and result.get("has_interaction"):
                            interactions.append(
                                {
                                    "drug_a": drug_a,
                                    "drug_b": drug_b,
                                    "severity": self._map_severity_label(str(result.get("severity", "")).lower()),
                                    "description": result.get("description", ""),
                                    "evidence_level": int(result.get("evidence_level", 2) or 2),
                                    "source": "DrugBank",
                                    "clinical_significance": result.get("clinical_significance", ""),
                                }
                            )
                return interactions

            self.logger.warning("DrugBank client missing interaction methods; skipping")
        except Exception as exc:
            self.logger.warning(
                "DrugBank interaction check failed",
                extra={"error": str(exc)},
            )

        return self._deduplicate_interactions(interactions)

    async def _check_openfda_label_interactions(self, drug_names: list[str]) -> list[dict]:
        """Infer pairwise interactions from OpenFDA label text sections."""
        labels_by_drug: dict[str, dict[str, Any] | None] = {}
        tasks = [
            self._openfda_client.get_drug_label(drug_name=name)
            for name in drug_names
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for drug_name, result in zip(drug_names, results):
            if isinstance(result, Exception):
                self.logger.warning(
                    "OpenFDA drug label lookup failed",
                    extra={"drug_name": drug_name, "error": str(result)},
                )
                labels_by_drug[drug_name] = None
                continue
            labels_by_drug[drug_name] = result

        interactions: list[dict] = []
        for drug_a in drug_names:
            label = labels_by_drug.get(drug_a)
            if not label:
                continue

            interaction_text = " ".join(
                [
                    str(label.get("drug_interactions", "") or ""),
                    str(label.get("contraindications", "") or ""),
                    str(label.get("warnings", "") or ""),
                ]
            ).strip()
            if not interaction_text:
                continue

            interaction_text_lower = interaction_text.lower()
            for drug_b in drug_names:
                if drug_a.lower() == drug_b.lower():
                    continue
                if not self._contains_medication_name(interaction_text_lower, drug_b):
                    continue

                interactions.append(
                    {
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "severity": self._infer_label_severity(interaction_text_lower),
                        "description": self._extract_label_snippet(interaction_text, drug_b),
                        "evidence_level": 3,
                        "source": "OpenFDA Label",
                        "clinical_significance": "Label indicates potential interaction or contraindication.",
                    }
                )

        return self._deduplicate_interactions(interactions)

    def _contains_medication_name(self, haystack_lower: str, medication_name: str) -> bool:
        """Check medication mention with word boundaries to reduce false positives."""
        pattern = rf"\b{re.escape(medication_name.lower())}\b"
        return re.search(pattern, haystack_lower) is not None

    def _infer_label_severity(self, text_lower: str) -> str:
        """Infer severity from regulatory-label interaction language."""
        major_terms = (
            "contraindicated",
            "avoid concomitant",
            "avoid use",
            "not recommended",
            "serious",
            "life-threatening",
            "major",
            "fatal",
        )
        moderate_terms = (
            "monitor",
            "caution",
            "increase",
            "decrease",
            "dose adjustment",
            "adjust dose",
            "bleeding risk",
            "toxicity",
            "interaction",
        )
        if any(term in text_lower for term in major_terms):
            return "major"
        if any(term in text_lower for term in moderate_terms):
            return "moderate"
        return "minor"

    def _extract_label_snippet(self, text: str, medication_name: str, window: int = 180) -> str:
        """Extract a short label snippet around the matched medication mention."""
        text_lower = text.lower()
        target = medication_name.lower()
        idx = text_lower.find(target)
        if idx == -1:
            snippet = text[:window]
        else:
            start = max(0, idx - window // 2)
            end = min(len(text), idx + len(target) + window // 2)
            snippet = text[start:end]
        compact = re.sub(r"\s+", " ", snippet).strip()
        if len(compact) > 320:
            compact = f"{compact[:317]}..."
        return compact

    async def _check_adverse_events(self, drug_names: list[str]) -> list[dict]:
        """Query OpenFDA for adverse event signals for each drug.

        Args:
            drug_names: List of drug names to check.

        Returns:
            List of adverse event summary dictionaries.
        """
        adverse_events: list[dict] = []

        tasks = [
            self._openfda_client.get_adverse_event_counts(drug_name=name)
            for name in drug_names
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(drug_names, results):
            if isinstance(result, Exception):
                self.logger.warning(
                    "OpenFDA adverse event query failed for drug",
                    extra={"drug_name": name, "error": str(result)},
                )
                continue

            if result and result.get("total_reports", 0) > 0:
                # Get top 5 most common reactions
                top_reactions = result.get("reaction_counts", [])[:5]
                adverse_events.append({
                    "drug_name": name,
                    "total_reports": result.get("total_reports", 0),
                    "top_reactions": [
                        {"term": r.get("term", ""), "count": r.get("count", 0)}
                        for r in top_reactions
                    ],
                })

        self.logger.info(
            "OpenFDA adverse event check completed",
            extra={
                "drugs_checked": len(drug_names),
                "drugs_with_events": len(adverse_events),
            },
        )
        return adverse_events

    async def _check_allergy_crossreactivity(
        self, allergies: list[dict | str], medications: list[str]
    ) -> list[dict]:
        """Check if any medications cross-react with known allergies.

        Uses built-in cross-reactivity group tables (e.g., penicillin
        cross-reactivity with cephalosporins).

        Args:
            allergies: List of allergy records (dict with ``substance`` key) or strings.
            medications: List of medication name strings to check.

        Returns:
            List of allergy alert dictionaries.
        """
        alerts: list[dict] = []

        if not allergies or not medications:
            return alerts

        # Normalize allergy substances
        allergy_substances: list[str] = []
        for allergy in allergies:
            if isinstance(allergy, dict):
                substance = allergy.get("substance", "").lower().strip()
            else:
                substance = str(allergy).lower().strip()
            if substance:
                allergy_substances.append(substance)

        if not allergy_substances:
            return alerts

        # Check each medication against allergy cross-reactivity groups
        for med_name in medications:
            med_lower = med_name.lower().strip()

            for allergy_substance in allergy_substances:
                # Direct match
                if allergy_substance in med_lower or med_lower in allergy_substance:
                    alerts.append({
                        "severity": "major",
                        "description": (
                            f"DIRECT ALLERGY MATCH: Patient is allergic to "
                            f"'{allergy_substance}' and '{med_name}' contains or "
                            f"is the same substance. This medication should NOT "
                            f"be administered."
                        ),
                        "source": "Allergy cross-reactivity check",
                        "evidence_level": 1,
                        "drug_name": med_name,
                        "allergy": allergy_substance,
                        "match_type": "direct",
                        "alternatives": [],
                    })
                    continue

                # Cross-reactivity group check
                for group_name, group_drugs in self.CROSS_REACTIVITY_GROUPS.items():
                    allergy_in_group = any(
                        allergy_substance in drug or drug in allergy_substance
                        for drug in group_drugs
                    ) or allergy_substance == group_name

                    med_in_group = any(
                        med_lower in drug or drug in med_lower
                        for drug in group_drugs
                    )

                    if allergy_in_group and med_in_group:
                        alerts.append({
                            "severity": "major",
                            "description": (
                                f"CROSS-REACTIVITY RISK: Patient is allergic to "
                                f"'{allergy_substance}' (in {group_name} group). "
                                f"'{med_name}' belongs to the same drug class and "
                                f"may cause a cross-reactive allergic response."
                            ),
                            "source": "Allergy cross-reactivity check",
                            "evidence_level": 2,
                            "drug_name": med_name,
                            "allergy": allergy_substance,
                            "match_type": f"cross_reactivity_{group_name}",
                            "alternatives": [],
                        })

        if alerts:
            self.logger.warning(
                "Allergy cross-reactivity alerts detected",
                extra={"alert_count": len(alerts)},
            )

        return alerts

    async def _synthesize_safety_report(
        self,
        drug_names: list[str],
        interactions: list[dict],
        adverse_events: list[dict],
        allergy_alerts: list[dict],
        conditions: list[str | dict],
        proposed_medications: list[str | dict],
    ) -> dict:
        """Use GPT-4o to synthesize a comprehensive drug safety report.

        Combines DDI data, adverse event signals, and allergy alerts
        into a clinician-friendly safety summary with alternative suggestions.

        Args:
            drug_names: All drug names checked.
            interactions: Detected drug-drug interactions.
            adverse_events: OpenFDA adverse event summaries.
            allergy_alerts: Cross-reactivity alerts.
            conditions: Patient conditions (for context).
            proposed_medications: Newly proposed medications.

        Returns:
            Dictionary with ``summary``, ``alternatives``, ``dosage_adjustments``,
            and ``safe_to_proceed``.
        """
        # Build context for the LLM
        context_parts: list[str] = []

        context_parts.append(f"Medications being checked: {', '.join(drug_names)}")

        proposed_names = [
            m.get("name", str(m)) if isinstance(m, dict) else str(m)
            for m in proposed_medications
        ]
        if proposed_names:
            context_parts.append(f"Newly proposed medications: {', '.join(proposed_names)}")

        condition_names = [
            c.get("display", str(c)) if isinstance(c, dict) else str(c)
            for c in conditions
        ]
        if condition_names:
            context_parts.append(f"Patient conditions: {', '.join(condition_names)}")

        if interactions:
            interaction_strs: list[str] = []
            for ddi in interactions:
                interaction_strs.append(
                    f"- {ddi['drug_a']} <-> {ddi['drug_b']}: "
                    f"Severity={ddi['severity']}, "
                    f"Description: {ddi['description'][:200]}"
                )
            context_parts.append(
                "Drug-Drug Interactions Found:\n" + "\n".join(interaction_strs)
            )
        else:
            context_parts.append("Drug-Drug Interactions: None detected")

        if adverse_events:
            ae_strs: list[str] = []
            for ae in adverse_events:
                top = ", ".join(
                    f"{r['term']} ({r['count']})"
                    for r in ae.get("top_reactions", [])[:3]
                )
                ae_strs.append(
                    f"- {ae['drug_name']}: {ae['total_reports']} reports. "
                    f"Top reactions: {top}"
                )
            context_parts.append(
                "Adverse Event Signals (OpenFDA):\n" + "\n".join(ae_strs)
            )

        if allergy_alerts:
            alert_strs = [f"- {a['description']}" for a in allergy_alerts]
            context_parts.append(
                "ALLERGY ALERTS:\n" + "\n".join(alert_strs)
            )

        context_text = "\n\n".join(context_parts)

        system_prompt = (
            "You are a clinical pharmacologist and drug safety specialist for a "
            "Clinical Decision Support System. Analyze the drug safety data provided "
            "and synthesize a comprehensive safety assessment.\n\n"
            "Respond with a JSON object containing:\n"
            "- \"summary\": a concise 2-5 sentence clinical safety summary highlighting "
            "the most critical findings and recommendations\n"
            "- \"safe_to_proceed\": boolean indicating whether the medication plan is "
            "considered safe (false if any major DDIs or allergy matches exist)\n"
            "- \"alternatives\": list of alternative medication suggestions if safety "
            "issues were found (empty list if none needed)\n"
            "- \"dosage_adjustments\": list of recommended dosage adjustments based on "
            "patient conditions and interactions (empty list if none needed)\n\n"
            "Be specific about which drug pairs interact and the clinical significance. "
            "Always err on the side of caution for patient safety."
        )

        try:
            response = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context_text},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=1536,
                response_format={"type": "json_object"},
            )

            synthesis = json.loads(response.get("content", "{}"))
            synthesis.setdefault("summary", "Drug safety assessment could not be completed.")
            synthesis.setdefault("safe_to_proceed", len(allergy_alerts) == 0 and not any(
                i.get("severity") == "major" for i in interactions
            ))
            synthesis.setdefault("alternatives", [])
            synthesis.setdefault("dosage_adjustments", [])

            self.logger.info(
                "Drug safety synthesis completed",
                extra={
                    "safe_to_proceed": synthesis["safe_to_proceed"],
                    "alternatives_count": len(synthesis["alternatives"]),
                },
            )
            return synthesis

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse safety synthesis JSON",
                extra={"error": str(exc)},
            )
            return self._build_fallback_synthesis(interactions, allergy_alerts)
        except Exception as exc:
            self.logger.warning(
                "Drug safety synthesis failed",
                extra={"error": str(exc)},
            )
            return self._build_fallback_synthesis(interactions, allergy_alerts)

    def _build_fallback_synthesis(
        self, interactions: list[dict], allergy_alerts: list[dict]
    ) -> dict:
        """Build a fallback synthesis when LLM synthesis fails.

        Args:
            interactions: Detected interactions.
            allergy_alerts: Detected allergy alerts.

        Returns:
            Basic synthesis dictionary.
        """
        has_major = any(i.get("severity") == "major" for i in interactions)
        has_allergies = len(allergy_alerts) > 0

        safe = not has_major and not has_allergies

        summary_parts: list[str] = []
        if has_allergies:
            summary_parts.append(
                f"CRITICAL: {len(allergy_alerts)} allergy alert(s) detected. "
                "Review allergy cross-reactivity before proceeding."
            )
        if has_major:
            major_count = sum(1 for i in interactions if i.get("severity") == "major")
            summary_parts.append(
                f"WARNING: {major_count} major drug-drug interaction(s) detected."
            )
        if not summary_parts:
            summary_parts.append("No critical drug safety issues detected.")

        return {
            "summary": " ".join(summary_parts),
            "safe_to_proceed": safe,
            "alternatives": [],
            "dosage_adjustments": [],
        }

    def _build_fallback_summary(
        self, interactions: list[dict], allergy_alerts: list[dict]
    ) -> str:
        """Build a fallback text summary.

        Args:
            interactions: Detected interactions.
            allergy_alerts: Detected allergy alerts.

        Returns:
            Summary string.
        """
        return self._build_fallback_synthesis(interactions, allergy_alerts)["summary"]
