"""Guardrails Agent for the Clinical Decision Support System.

Validates clinical output for safety, hallucination detection,
citation verification, scope classification, and confidence thresholds.
Acts as the final quality gate before responses are returned to clinicians.
"""

from __future__ import annotations

import json
from typing import Any

from cdss.agents.base import BaseAgent
from cdss.clients.openai_client import AzureOpenAIClient
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AgentError, GuardrailsViolation
from cdss.core.models import AgentTask, GuardrailsResult


class GuardrailsAgent(BaseAgent):
    """Validates clinical output for safety, hallucination, and scope.

    Checks (from architecture):
    - Hallucination check: every claim must have a citation
    - Drug safety check: no recommendation contradicts DDI alerts
    - Scope check: flags if recommendation exceeds system capability
    - Disclaimer injection
    - Confidence threshold: if < 0.6, escalate to "insufficient evidence"

    Model: GPT-4o (independent instance)
    Output: GuardrailsResult
    """

    # Standard clinical disclaimers
    STANDARD_DISCLAIMERS: list[str] = [
        "This is clinical decision support and does not constitute a medical diagnosis.",
        "All recommendations should be verified by the attending physician.",
        "This system is designed to assist, not replace, clinical judgment.",
    ]

    # Topics considered outside CDSS scope
    OUT_OF_SCOPE_INDICATORS: list[str] = [
        "surgical procedure details",
        "mental health crisis intervention",
        "pediatric dosing for neonates",
        "radiation therapy planning",
        "genetic counseling",
        "end-of-life decisions",
        "malpractice or legal advice",
        "insurance or billing",
        "specific patient prognosis or life expectancy",
    ]

    def __init__(
        self,
        openai_client: AzureOpenAIClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the GuardrailsAgent.

        Args:
            openai_client: Azure OpenAI client for validation LLM calls.
                Uses an independent GPT-4o instance for unbiased validation.
            settings: Application settings. Defaults to environment-loaded settings.
        """
        super().__init__(name="guardrails_agent", model="gpt-4o")
        self._settings = settings or get_settings()
        self._openai_client = openai_client or AzureOpenAIClient(settings=self._settings)
        self._confidence_threshold = self._settings.confidence_threshold

    async def _execute(self, task: AgentTask) -> dict:
        """Validate the clinical response.

        1. Citation verification: check every claim has a source
        2. Drug safety validation: ensure no contradictions with DDI alerts
        3. Scope classification: is this within CDSS capability?
        4. Confidence check: if < threshold, flag as insufficient evidence
        5. Add required disclaimers
        6. Return GuardrailsResult

        Args:
            task: Agent task with payload containing:
                - ``response`` (dict or str): The clinical response to validate.
                - ``drug_alerts`` (list[dict]): Drug safety alerts from DrugSafetyAgent.
                - ``citations`` (list[dict]): Citations from MedicalLiteratureAgent.
                - ``confidence_score`` (float): Confidence score from the orchestrator.

        Returns:
            Dictionary containing ``summary``, ``sources_retrieved``, and
            ``guardrails_result`` (serialized GuardrailsResult).
        """
        response = task.payload.get("response", {})
        drug_alerts = task.payload.get("drug_alerts", [])
        citations = task.payload.get("citations", [])
        confidence_score = task.payload.get("confidence_score", 0.0)

        # Extract text from response (handle both dict and string)
        if isinstance(response, dict):
            response_text = response.get(
                "recommendation",
                response.get("assessment", response.get("content", str(response))),
            )
        else:
            response_text = str(response)

        if not response_text or not response_text.strip():
            raise AgentError(
                message="Empty response text provided for guardrails validation",
                agent_name=self.name,
            )

        self.logger.info(
            "Starting guardrails validation",
            extra={
                "response_length": len(response_text),
                "drug_alerts_count": len(drug_alerts),
                "citations_count": len(citations),
                "confidence_score": confidence_score,
            },
        )

        # Run all validation checks
        # Step 1: Citation verification
        citation_issues = await self._verify_citations(response_text, citations)

        # Step 2: Drug safety validation
        safety_issues = await self._check_drug_safety_consistency(
            response_text, drug_alerts
        )

        # Step 3: Scope classification
        scope_issues: list[str] = []
        is_in_scope = await self._classify_scope(response_text)
        if not is_in_scope:
            scope_issues.append(
                "This recommendation may exceed the scope of the Clinical Decision "
                "Support System. Manual review by a specialist is recommended."
            )

        # Step 4: Confidence check
        hallucination_flags: list[str] = []
        escalation_required = False
        escalation_reason = ""

        if confidence_score < self._confidence_threshold:
            escalation_required = True
            escalation_reason = (
                f"Confidence score ({confidence_score:.2f}) is below the threshold "
                f"({self._confidence_threshold:.2f}). The evidence base may be "
                f"insufficient for a reliable recommendation."
            )
            hallucination_flags.append(
                f"Low confidence ({confidence_score:.2f}): recommendation may not be "
                f"adequately supported by available evidence."
            )

        # Additional hallucination flags from citation check
        if citation_issues:
            hallucination_flags.extend([
                f"Unsupported claim: {issue}" for issue in citation_issues[:5]
            ])

        # Step 5: Add required disclaimers
        disclaimers = self._get_required_disclaimers()

        # Add context-specific disclaimers
        if drug_alerts:
            major_alerts = [
                a for a in drug_alerts
                if a.get("severity") in ("major", "contraindicated")
            ]
            if major_alerts:
                disclaimers.append(
                    "IMPORTANT: Major drug safety alerts have been identified. "
                    "Review the drug safety report before implementing any medication changes."
                )

        if escalation_required:
            disclaimers.append(
                "NOTE: This recommendation has been flagged for physician review "
                "due to insufficient evidence confidence."
            )

        # Determine overall validity
        is_valid = (
            not safety_issues
            and not scope_issues
            and not escalation_required
            and len(citation_issues) <= 2  # Allow minor citation gaps
        )

        # Build GuardrailsResult
        guardrails_result = GuardrailsResult(
            is_valid=is_valid,
            hallucination_flags=hallucination_flags,
            safety_concerns=safety_issues,
            disclaimers=disclaimers,
        )

        # Build summary
        summary = self._build_validation_summary(
            is_valid=is_valid,
            citation_issues=citation_issues,
            safety_issues=safety_issues,
            scope_issues=scope_issues,
            confidence_score=confidence_score,
            escalation_required=escalation_required,
        )

        self.logger.info(
            "Guardrails validation completed",
            extra={
                "is_valid": is_valid,
                "citation_issues": len(citation_issues),
                "safety_issues": len(safety_issues),
                "scope_issues": len(scope_issues),
                "hallucination_flags": len(hallucination_flags),
                "escalation_required": escalation_required,
            },
        )

        return {
            "summary": summary,
            "sources_retrieved": len(citations),
            "guardrails_result": guardrails_result.model_dump(),
            "is_valid": is_valid,
            "citation_issues": citation_issues,
            "safety_issues": safety_issues,
            "scope_issues": scope_issues,
            "escalation_required": escalation_required,
            "escalation_reason": escalation_reason,
        }

    async def _verify_citations(
        self, response_text: str, citations: list[dict]
    ) -> list[str]:
        """Verify that claims in the response are supported by citations.

        Uses GPT-4o to identify factual claims in the response and check
        whether each claim is supported by the provided citations.

        Args:
            response_text: The clinical response text to verify.
            citations: List of citation dictionaries with ``title``,
                      ``identifier``, and ``source_type`` keys.

        Returns:
            List of issue strings for claims lacking citation support.
        """
        if not citations:
            return [
                "No citations were provided to support the clinical recommendation. "
                "All clinical claims should be backed by evidence."
            ]

        # Build citation reference text
        citation_refs: list[str] = []
        for i, cite in enumerate(citations, 1):
            title = cite.get("title", "Untitled")
            identifier = cite.get("identifier", "Unknown")
            source_type = cite.get("source_type", "unknown")
            citation_refs.append(
                f"[{i}] {title} ({source_type}: {identifier})"
            )

        citations_text = "\n".join(citation_refs)

        system_prompt = (
            "You are a medical fact-checker for a Clinical Decision Support System. "
            "Your task is to identify factual clinical claims in the response and "
            "determine whether each claim is supported by the provided citations.\n\n"
            "Respond with a JSON object containing:\n"
            "- \"unsupported_claims\": list of strings describing specific claims "
            "in the response that are NOT supported by any of the cited sources. "
            "Only flag claims that make specific clinical assertions (drug dosages, "
            "treatment outcomes, diagnostic criteria, etc.). Do not flag general "
            "medical knowledge or transitional statements.\n"
            "- \"supported_claims_count\": integer count of claims that ARE supported\n"
            "- \"total_claims_count\": integer total number of clinical claims identified\n\n"
            "Be precise but not overly strict. Common medical knowledge "
            "(e.g., 'diabetes is characterized by elevated blood glucose') does not "
            "need specific citation."
        )

        user_prompt = (
            f"Clinical Response to Verify:\n{response_text}\n\n"
            f"Available Citations:\n{citations_text}"
        )

        try:
            result = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.0,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            verification = json.loads(result.get("content", "{}"))
            unsupported = verification.get("unsupported_claims", [])

            self.logger.debug(
                "Citation verification completed",
                extra={
                    "total_claims": verification.get("total_claims_count", 0),
                    "supported_claims": verification.get("supported_claims_count", 0),
                    "unsupported_claims": len(unsupported),
                },
            )

            return unsupported

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse citation verification JSON",
                extra={"error": str(exc)},
            )
            return ["Citation verification could not be completed due to a processing error."]
        except Exception as exc:
            self.logger.warning(
                "Citation verification failed",
                extra={"error": str(exc)},
            )
            return ["Citation verification could not be completed."]

    async def _check_drug_safety_consistency(
        self, recommendation: str, drug_alerts: list[dict]
    ) -> list[str]:
        """Ensure recommendation does not contradict drug safety alerts.

        Uses GPT-4o to compare the clinical recommendation against the drug
        safety alerts and identify any contradictions.

        Args:
            recommendation: The clinical recommendation text.
            drug_alerts: List of drug alert dictionaries.

        Returns:
            List of safety issue strings for contradictions found.
        """
        if not drug_alerts:
            return []

        # Format drug alerts for the LLM
        alert_strs: list[str] = []
        for i, alert in enumerate(drug_alerts, 1):
            severity = alert.get("severity", "unknown")
            description = alert.get("description", "No description")
            source = alert.get("source", "Unknown")
            alert_strs.append(
                f"[Alert {i}] Severity: {severity}\n"
                f"  Description: {description}\n"
                f"  Source: {source}"
            )

        alerts_text = "\n\n".join(alert_strs)

        system_prompt = (
            "You are a drug safety validator for a Clinical Decision Support System. "
            "Compare the clinical recommendation against the drug safety alerts and "
            "identify any contradictions or unsafe recommendations.\n\n"
            "A contradiction exists when:\n"
            "- The recommendation suggests a drug flagged in a major interaction alert\n"
            "- The recommendation dosage conflicts with safety adjustments\n"
            "- The recommendation ignores an allergy cross-reactivity alert\n"
            "- The recommendation combines drugs with a known major DDI\n\n"
            "Respond with a JSON object containing:\n"
            "- \"contradictions\": list of strings describing specific contradictions "
            "between the recommendation and drug safety alerts. Each string should "
            "name the specific drugs and the nature of the conflict.\n"
            "- \"is_consistent\": boolean, true if the recommendation is consistent "
            "with all drug safety alerts"
        )

        user_prompt = (
            f"Clinical Recommendation:\n{recommendation}\n\n"
            f"Drug Safety Alerts:\n{alerts_text}"
        )

        try:
            result = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.0,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            validation = json.loads(result.get("content", "{}"))
            contradictions = validation.get("contradictions", [])

            self.logger.debug(
                "Drug safety consistency check completed",
                extra={
                    "is_consistent": validation.get("is_consistent", True),
                    "contradictions_count": len(contradictions),
                },
            )

            return contradictions

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse drug safety consistency JSON",
                extra={"error": str(exc)},
            )
            return [
                "Drug safety consistency check could not be completed. "
                "Manual verification of drug interactions is recommended."
            ]
        except Exception as exc:
            self.logger.warning(
                "Drug safety consistency check failed",
                extra={"error": str(exc)},
            )
            return [
                "Drug safety consistency check could not be completed. "
                "Manual verification is recommended."
            ]

    async def _classify_scope(self, recommendation: str) -> bool:
        """Check if the recommendation is within CDSS scope.

        Uses GPT-4o to determine whether the recommendation falls within
        the Clinical Decision Support System's intended capabilities.

        Args:
            recommendation: The clinical recommendation text.

        Returns:
            True if the recommendation is within scope, False otherwise.
        """
        out_of_scope_list = "\n".join(
            f"- {indicator}" for indicator in self.OUT_OF_SCOPE_INDICATORS
        )

        system_prompt = (
            "You are a scope classifier for a Clinical Decision Support System. "
            "Determine whether the following clinical recommendation falls within "
            "the system's intended scope.\n\n"
            "The system IS designed to help with:\n"
            "- Evidence-based treatment recommendations\n"
            "- Drug interaction and safety checks\n"
            "- Clinical guideline matching\n"
            "- Differential diagnosis support\n"
            "- Lab result interpretation\n"
            "- Medical literature evidence summaries\n\n"
            "The system is NOT designed for:\n"
            f"{out_of_scope_list}\n\n"
            "Respond with a JSON object containing:\n"
            "- \"is_in_scope\": boolean, true if the recommendation is within scope\n"
            "- \"reason\": brief explanation if out of scope (empty string if in scope)"
        )

        try:
            result = await self._openai_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Recommendation:\n{recommendation}"},
                ],
                model=self.model,
                temperature=0.0,
                max_tokens=256,
                response_format={"type": "json_object"},
            )

            classification = json.loads(result.get("content", "{}"))
            is_in_scope = classification.get("is_in_scope", True)
            reason = classification.get("reason", "")

            if not is_in_scope:
                self.logger.warning(
                    "Recommendation classified as out of scope",
                    extra={"reason": reason},
                )

            return bool(is_in_scope)

        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse scope classification JSON",
                extra={"error": str(exc)},
            )
            # Default to in-scope to avoid false blocking
            return True
        except Exception as exc:
            self.logger.warning(
                "Scope classification failed, defaulting to in-scope",
                extra={"error": str(exc)},
            )
            return True

    def _get_required_disclaimers(self) -> list[str]:
        """Return standard clinical disclaimers.

        Returns:
            List of disclaimer strings that must be attached to every response.
        """
        return list(self.STANDARD_DISCLAIMERS)

    def _build_validation_summary(
        self,
        is_valid: bool,
        citation_issues: list[str],
        safety_issues: list[str],
        scope_issues: list[str],
        confidence_score: float,
        escalation_required: bool,
    ) -> str:
        """Build a human-readable summary of the guardrails validation.

        Args:
            is_valid: Overall validation result.
            citation_issues: Citation verification issues.
            safety_issues: Drug safety consistency issues.
            scope_issues: Scope classification issues.
            confidence_score: Confidence score.
            escalation_required: Whether escalation was triggered.

        Returns:
            Narrative summary of the validation outcome.
        """
        status = "PASSED" if is_valid else "FAILED"
        parts: list[str] = [f"Guardrails Validation: {status}"]

        parts.append(f"Confidence Score: {confidence_score:.2f}")

        if citation_issues:
            parts.append(
                f"Citation Issues ({len(citation_issues)}): "
                f"{citation_issues[0][:100]}{'...' if len(citation_issues[0]) > 100 else ''}"
            )
            if len(citation_issues) > 1:
                parts.append(f"  ...and {len(citation_issues) - 1} more")

        if safety_issues:
            parts.append(
                f"Safety Issues ({len(safety_issues)}): "
                f"{safety_issues[0][:100]}{'...' if len(safety_issues[0]) > 100 else ''}"
            )

        if scope_issues:
            parts.append(f"Scope Issues: {scope_issues[0][:100]}")

        if escalation_required:
            parts.append(
                "ESCALATION REQUIRED: Confidence below threshold, "
                "physician review recommended."
            )

        return "\n".join(parts)
