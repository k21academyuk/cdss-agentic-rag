"""Patient History Agent for the Clinical Decision Support System.

Retrieves and synthesizes patient demographics, conditions, medications,
allergies, laboratory results, and clinical timeline from Cosmos DB
and Azure AI Search into a unified PatientContext.
"""

from __future__ import annotations

import json
from typing import Any

from cdss.agents.base import BaseAgent
from cdss.clients.cosmos_client import CosmosDBClient
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.clients.search_client import AzureSearchClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AgentError
from cdss.core.models import (
    AgentTask,
    Allergy,
    Demographics,
    LabResult,
    MedicalCondition,
    Medication,
    PatientContext,
    PatientProfile,
)


class PatientHistoryAgent(BaseAgent):
    """Retrieves patient demographics, conditions, medications, allergies, labs, and timeline.

    Tools:
    - azure_ai_search(index="patient-records")
    - cosmos_db_read(container="patient_profiles")
    - FHIR query (simulated)

    Model: GPT-4o-mini
    Output: PatientContext
    """

    def __init__(
        self,
        search_client: AzureSearchClient | None = None,
        cosmos_client: CosmosDBClient | None = None,
        openai_client: AzureOpenAIClient | None = None,
        retriever: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the PatientHistoryAgent.

        Args:
            search_client: Azure AI Search client for patient record retrieval.
            cosmos_client: Cosmos DB client for patient profile lookup.
            openai_client: Azure OpenAI client for timeline synthesis.
            retriever: Optional RAG retriever for enhanced document retrieval.
            settings: Application settings. Defaults to environment-loaded settings.
        """
        super().__init__(name="patient_history_agent", model="gpt-4o-mini")
        self._settings = settings or get_settings()
        self._search_client = search_client or AzureSearchClient(settings=self._settings)
        self._cosmos_client = cosmos_client or CosmosDBClient(settings=self._settings)
        self._openai_client = openai_client or AzureOpenAIClient(settings=self._settings)
        self._retriever = retriever

    async def _execute(self, task: AgentTask) -> dict:
        """Retrieve patient context from multiple sources.

        1. Get patient profile from Cosmos DB
        2. Search patient records in AI Search
        3. Synthesize timeline with GPT-4o-mini
        4. Return PatientContext

        Args:
            task: Agent task with payload containing ``patient_id`` and optional ``query``.

        Returns:
            Dictionary containing ``summary``, ``sources_retrieved``, and
            ``patient_context`` (serialized PatientContext).

        Raises:
            AgentError: If patient_id is missing from the payload.
        """
        patient_id = task.payload.get("patient_id")
        query = task.payload.get("query", "")

        if not patient_id:
            raise AgentError(
                message="patient_id is required in task payload",
                agent_name=self.name,
            )

        self.logger.info(
            "Retrieving patient context",
            extra={"patient_id": patient_id, "query": query[:100]},
        )

        # Step 1: Get stored profile from Cosmos DB
        profile_data = await self._fetch_patient_profile(patient_id)

        # Step 2: Search AI Search patient-records index for relevant documents
        search_results = await self._search_patient_records(patient_id, query)

        # Step 3: Use GPT-4o-mini to synthesize a patient timeline summary
        timeline_summary = await self._synthesize_timeline(
            patient_id=patient_id,
            profile_data=profile_data,
            search_results=search_results,
            query=query,
        )

        # Step 4: Combine into PatientContext
        patient_context = self._build_patient_context(
            patient_id=patient_id,
            profile_data=profile_data,
            search_results=search_results,
            timeline_summary=timeline_summary,
        )

        total_sources = (1 if profile_data else 0) + len(search_results)

        self.logger.info(
            "Patient context assembled",
            extra={
                "patient_id": patient_id,
                "conditions_count": len(patient_context.conditions),
                "medications_count": len(patient_context.medications),
                "allergies_count": len(patient_context.allergies),
                "labs_count": len(patient_context.recent_labs),
                "total_sources": total_sources,
            },
        )

        return {
            "summary": timeline_summary,
            "sources_retrieved": total_sources,
            "patient_context": patient_context.model_dump(),
        }

    async def _fetch_patient_profile(self, patient_id: str) -> dict | None:
        """Fetch the patient profile from Cosmos DB.

        Args:
            patient_id: The unique patient identifier.

        Returns:
            Patient profile dictionary, or None if not found.
        """
        try:
            profile = await self._cosmos_client.get_patient_profile(patient_id)
            if profile:
                self.logger.debug(
                    "Patient profile retrieved from Cosmos DB",
                    extra={"patient_id": patient_id},
                )
            else:
                self.logger.warning(
                    "Patient profile not found in Cosmos DB",
                    extra={"patient_id": patient_id},
                )
            return profile
        except Exception as exc:
            self.logger.warning(
                "Failed to fetch patient profile from Cosmos DB, continuing with search only",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            return None

    async def _search_patient_records(
        self, patient_id: str, query: str
    ) -> list[dict]:
        """Search for relevant patient records in Azure AI Search.

        Args:
            patient_id: Patient identifier for filtering.
            query: Clinical query to contextualize search.

        Returns:
            List of search result dictionaries.
        """
        search_query = f"patient:{patient_id} {query}" if query else f"patient:{patient_id} medical history"

        try:
            results = await self._search_client.search_patient_records(
                query=search_query,
                patient_id=patient_id,
                top=20,
            )
            self.logger.debug(
                "Patient records search completed",
                extra={
                    "patient_id": patient_id,
                    "results_count": len(results),
                },
            )
            return results
        except Exception as exc:
            self.logger.warning(
                "Patient records search failed, continuing with Cosmos DB data only",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            return []

    async def _synthesize_timeline(
        self,
        patient_id: str,
        profile_data: dict | None,
        search_results: list[dict],
        query: str,
    ) -> str:
        """Use GPT-4o-mini to synthesize a narrative patient timeline.

        Combines data from the Cosmos DB profile and AI Search results
        into a coherent clinical timeline summary relevant to the query.

        Args:
            patient_id: Patient identifier.
            profile_data: Patient profile from Cosmos DB, or None.
            search_results: Search results from AI Search.
            query: The original clinical query for contextual focus.

        Returns:
            A narrative summary of the patient's clinical timeline.
        """
        # Build context from available data
        context_parts: list[str] = []

        if profile_data:
            demographics = profile_data.get("demographics", {})
            context_parts.append(
                f"Demographics: Age {demographics.get('age', 'unknown')}, "
                f"Sex {demographics.get('sex', 'unknown')}, "
                f"Weight {demographics.get('weight_kg', 'unknown')} kg, "
                f"Height {demographics.get('height_cm', 'unknown')} cm"
            )

            conditions = profile_data.get("active_conditions", [])
            if conditions:
                condition_strs = [
                    f"- {c.get('display', c.get('code', 'Unknown'))} "
                    f"(Status: {c.get('status', 'active')}, "
                    f"Onset: {c.get('onset_date', 'unknown')})"
                    for c in conditions
                ]
                context_parts.append("Active Conditions:\n" + "\n".join(condition_strs))

            medications = profile_data.get("active_medications", [])
            if medications:
                med_strs = [
                    f"- {m.get('name', 'Unknown')} {m.get('dose', '')} {m.get('frequency', '')}"
                    for m in medications
                ]
                context_parts.append("Current Medications:\n" + "\n".join(med_strs))

            allergies = profile_data.get("allergies", [])
            if allergies:
                allergy_strs = [
                    f"- {a.get('substance', 'Unknown')} "
                    f"(Reaction: {a.get('reaction', 'unknown')}, "
                    f"Severity: {a.get('severity', 'unknown')})"
                    for a in allergies
                ]
                context_parts.append("Allergies:\n" + "\n".join(allergy_strs))

            labs = profile_data.get("recent_labs", [])
            if labs:
                lab_strs = [
                    f"- {l.get('display', l.get('code', 'Unknown'))}: "
                    f"{l.get('value', '')} {l.get('unit', '')} "
                    f"(Ref: {l.get('reference_range', 'N/A')}, "
                    f"Date: {l.get('date', 'unknown')})"
                    for l in labs
                ]
                context_parts.append("Recent Lab Results:\n" + "\n".join(lab_strs))

        # Add relevant content from search results
        if search_results:
            relevant_docs = [
                r.get("content", "")[:500]
                for r in search_results[:10]
                if r.get("content")
            ]
            if relevant_docs:
                context_parts.append(
                    "Additional Clinical Records:\n" + "\n---\n".join(relevant_docs)
                )

        if not context_parts:
            return f"No clinical data found for patient {patient_id}."

        patient_context_text = "\n\n".join(context_parts)

        system_prompt = (
            "You are a clinical data synthesizer in a Clinical Decision Support System. "
            "Given patient data from electronic health records, synthesize a concise "
            "clinical timeline summary. Focus on:\n"
            "1. Key demographics and relevant history\n"
            "2. Active conditions with onset dates\n"
            "3. Current medication regimen\n"
            "4. Known allergies and their severity\n"
            "5. Significant recent lab results and trends\n"
            "6. Any information relevant to the clinical query\n\n"
            "Be factual and concise. Only include information present in the data. "
            "Do not speculate or infer conditions not documented."
        )

        user_prompt = (
            f"Patient ID: {patient_id}\n\n"
            f"Clinical Query: {query}\n\n"
            f"Patient Data:\n{patient_context_text}\n\n"
            "Please synthesize a clinical timeline summary for this patient, "
            "highlighting information relevant to the clinical query."
        )

        try:
            response = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=1024,
            )
            timeline = response.get("content", "").strip()
            self.logger.debug(
                "Timeline synthesis completed",
                extra={"patient_id": patient_id, "timeline_length": len(timeline)},
            )
            return timeline
        except Exception as exc:
            self.logger.warning(
                "Timeline synthesis failed, returning raw data summary",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            # Fallback: return a basic summary from raw data
            return self._build_fallback_summary(patient_id, profile_data)

    def _build_fallback_summary(
        self, patient_id: str, profile_data: dict | None
    ) -> str:
        """Build a basic fallback summary when LLM synthesis fails.

        Args:
            patient_id: Patient identifier.
            profile_data: Patient profile data from Cosmos DB.

        Returns:
            A basic text summary of available patient data.
        """
        if not profile_data:
            return f"Patient {patient_id}: No profile data available."

        parts: list[str] = [f"Patient {patient_id}:"]

        demographics = profile_data.get("demographics", {})
        if demographics:
            parts.append(
                f"  {demographics.get('age', '?')}yo "
                f"{demographics.get('sex', 'unknown')}"
            )

        conditions = profile_data.get("active_conditions", [])
        if conditions:
            cond_names = [c.get("display", c.get("code", "?")) for c in conditions]
            parts.append(f"  Conditions: {', '.join(cond_names)}")

        medications = profile_data.get("active_medications", [])
        if medications:
            med_names = [m.get("name", "?") for m in medications]
            parts.append(f"  Medications: {', '.join(med_names)}")

        allergies = profile_data.get("allergies", [])
        if allergies:
            allergy_names = [a.get("substance", "?") for a in allergies]
            parts.append(f"  Allergies: {', '.join(allergy_names)}")

        return "\n".join(parts)

    def _build_patient_context(
        self,
        patient_id: str,
        profile_data: dict | None,
        search_results: list[dict],
        timeline_summary: str,
    ) -> PatientContext:
        """Assemble a PatientContext from all available data sources.

        Args:
            patient_id: Patient identifier.
            profile_data: Patient profile from Cosmos DB.
            search_results: Search results from AI Search.
            timeline_summary: LLM-synthesized timeline narrative.

        Returns:
            A fully populated PatientContext instance.
        """
        demographics = Demographics(
            age=0, sex="unknown", weight_kg=0.1, height_cm=0.1
        )
        conditions: list[MedicalCondition] = []
        medications: list[Medication] = []
        allergies: list[Allergy] = []
        recent_labs: list[LabResult] = []

        if profile_data:
            # Parse demographics
            demo_data = profile_data.get("demographics", {})
            if demo_data:
                demographics = Demographics(
                    age=demo_data.get("age", 0),
                    sex=demo_data.get("sex", "unknown"),
                    weight_kg=demo_data.get("weight_kg", 0.1),
                    height_cm=demo_data.get("height_cm", 0.1),
                    blood_type=demo_data.get("blood_type"),
                )

            # Parse conditions
            for cond_data in profile_data.get("active_conditions", []):
                try:
                    conditions.append(
                        MedicalCondition(
                            code=cond_data.get("code", "unknown"),
                            system=cond_data.get("system", "ICD-10"),
                            display=cond_data.get("display", "Unknown condition"),
                            onset_date=cond_data.get("onset_date"),
                            status=cond_data.get("status", "active"),
                        )
                    )
                except Exception as exc:
                    self.logger.debug(
                        "Skipping malformed condition record",
                        extra={"error": str(exc), "data": str(cond_data)[:200]},
                    )

            # Parse medications
            for med_data in profile_data.get("active_medications", []):
                try:
                    medications.append(
                        Medication(
                            rxcui=med_data.get("rxcui", "unknown"),
                            name=med_data.get("name", "Unknown medication"),
                            dose=med_data.get("dose", "unknown"),
                            frequency=med_data.get("frequency", "unknown"),
                            start_date=med_data.get("start_date"),
                            prescriber=med_data.get("prescriber"),
                        )
                    )
                except Exception as exc:
                    self.logger.debug(
                        "Skipping malformed medication record",
                        extra={"error": str(exc), "data": str(med_data)[:200]},
                    )

            # Parse allergies
            for allergy_data in profile_data.get("allergies", []):
                try:
                    allergies.append(
                        Allergy(
                            substance=allergy_data.get("substance", "Unknown"),
                            reaction=allergy_data.get("reaction", "Unknown"),
                            severity=allergy_data.get("severity", "moderate"),
                            code=allergy_data.get("code"),
                            system=allergy_data.get("system"),
                        )
                    )
                except Exception as exc:
                    self.logger.debug(
                        "Skipping malformed allergy record",
                        extra={"error": str(exc), "data": str(allergy_data)[:200]},
                    )

            # Parse lab results
            for lab_data in profile_data.get("recent_labs", []):
                try:
                    recent_labs.append(
                        LabResult(
                            code=lab_data.get("code", "unknown"),
                            system=lab_data.get("system", "LOINC"),
                            display=lab_data.get("display", "Unknown test"),
                            value=float(lab_data.get("value", 0)),
                            unit=lab_data.get("unit", ""),
                            date=lab_data.get("date"),
                            reference_range=lab_data.get("reference_range"),
                        )
                    )
                except Exception as exc:
                    self.logger.debug(
                        "Skipping malformed lab result record",
                        extra={"error": str(exc), "data": str(lab_data)[:200]},
                    )

        total_sources = (1 if profile_data else 0) + len(search_results)

        return PatientContext(
            demographics=demographics,
            conditions=conditions,
            medications=medications,
            allergies=allergies,
            recent_labs=recent_labs,
            timeline_summary=timeline_summary,
        )
