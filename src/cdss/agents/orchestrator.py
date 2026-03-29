"""Orchestrator (Supervisor) Agent for the Clinical Decision Support System.

The orchestrator decomposes clinical queries, dispatches them to specialized
agents in parallel, resolves conflicts between agent outputs, synthesizes
a final clinical recommendation via GPT-4o, and validates the result through
guardrails before returning a response.

Architecture role:
    - Query Planner: decomposes queries, classifies type, identifies required agents
    - Session Manager: maintains conversation context via Cosmos DB
    - Context Assembler: merges agent outputs using cross-source fusion
    - Response Synthesizer: generates final clinical recommendation
    - Conflict Resolver: handles contradictory agent outputs
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import (
    AgentError,
    AgentTimeoutError,
    CDSSError,
)
from cdss.core.logging import get_logger, trace_id_var
from cdss.core.models import (
    AgentOutput,
    AgentTask,
    AuditLogEntry,
    Citation,
    ClinicalQuery,
    ClinicalResponse,
    ConversationTurn,
    DrugAlert,
    GuardrailsResult,
    QueryPlan,
)

logger = get_logger(__name__)

# Default disclaimers appended to every clinical response.
DEFAULT_DISCLAIMERS: list[str] = [
    "This is a clinical decision support tool and does not replace clinical judgment.",
    "Always verify recommendations against current institutional guidelines.",
    "AI-generated content should be reviewed by a qualified healthcare professional.",
]

# Agent dispatch timeout in seconds.
AGENT_TIMEOUT_SECONDS = 30

# System prompt for query planning via GPT-4o-mini.
QUERY_PLAN_SYSTEM_PROMPT = """\
You are a clinical query planner for a Clinical Decision Support System.
Analyze the clinical query and produce a JSON execution plan.

Respond with a JSON object containing:
- "query_type": one of "diagnosis", "treatment", "drug_check", "general", "emergency"
- "required_agents": list from ["patient_history", "literature", "protocol", "drug_safety"]
- "sub_queries": dict mapping each required agent name to a sub-query string optimized for that agent
- "priority": one of "low", "medium", "high", "critical"
- "parallel_dispatch": boolean (true unless sequential ordering is required)

Agent selection rules:
- "diagnosis": always include patient_history, literature
- "treatment": include patient_history, literature, protocol; add drug_safety if medications mentioned
- "drug_check": always include drug_safety; add patient_history if patient_id present
- "general": include literature; add others based on query content
- "emergency": include all agents; set priority to "critical"
- Always include patient_history if a patient_id is provided
"""

# System prompt for clinical response synthesis via GPT-4o.
SYNTHESIS_SYSTEM_PROMPT = """\
You are a clinical decision support AI synthesizing evidence from multiple \
specialized agents to produce a comprehensive clinical recommendation.

You MUST respond with a JSON object containing:
- "assessment": A concise clinical assessment based on the query and patient context.
- "recommendation": An evidence-based clinical recommendation. Be specific, actionable, and cite sources.
- "evidence_summary": A list of 3-7 key evidence points supporting the recommendation.
- "confidence_score": A float between 0.0 and 1.0 reflecting your confidence in the recommendation.
- "citations": A list of citation objects, each with "source_type" (one of "pubmed", "guideline", \
"patient_record", "drug_database"), "identifier", "title", "relevance_score" (0.0-1.0), and optional "url".

Guidelines:
1. Base recommendations on the strongest available evidence.
2. Clearly distinguish patient-specific data from general guidelines.
3. Flag any safety concerns prominently.
4. When evidence is insufficient, explicitly state uncertainty.
5. Use clinical terminology appropriate for healthcare professionals.
6. Never fabricate citations -- only reference sources provided in the context.
"""

# System prompt for guardrails validation via GPT-4o-mini.
GUARDRAILS_SYSTEM_PROMPT = """\
You are a clinical safety validator for a Clinical Decision Support System.
Evaluate the generated clinical response for safety and accuracy.

Analyze the response and return a JSON object:
- "is_valid": boolean, true if the response passes all checks
- "hallucination_flags": list of strings describing any unsupported claims
- "safety_concerns": list of strings describing any safety issues found
- "disclaimers": list of additional disclaimers to append (if any)

Validation checks:
1. Hallucination Detection: Ensure every claim is supported by the provided agent context.
2. Safety: Flag dangerous dosing, missed contraindications, or missed drug interactions.
3. Scope: Ensure the response stays within clinical decision support (not definitive diagnosis).
4. Citation Integrity: Every cited source must appear in agent outputs.
5. Confidence Calibration: Confidence score should reflect evidence quality.
"""


class OrchestratorAgent:
    """Meta-agent that decomposes clinical queries, dispatches to specialized
    agents, resolves conflicts, and synthesizes final clinical responses.

    Attributes:
        patient_history_agent: Agent for patient record retrieval.
        literature_agent: Agent for PubMed / medical literature search.
        protocol_agent: Agent for clinical guideline and protocol matching.
        drug_safety_agent: Agent for drug interaction and safety checks.
        guardrails_agent: Agent for response validation.
        openai_client: Azure OpenAI client wrapper.
        cosmos_client: Cosmos DB client wrapper.
        settings: Application settings.
    """

    def __init__(
        self,
        patient_history_agent: object | None = None,
        literature_agent: object | None = None,
        protocol_agent: object | None = None,
        drug_safety_agent: object | None = None,
        guardrails_agent: object | None = None,
        openai_client: object | None = None,
        cosmos_client: object | None = None,
        embedding_service: object | None = None,
        fusion: object | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the orchestrator with agent and client dependencies.

        If dependencies are not provided, default instances are lazily created
        from the application settings.

        Args:
            patient_history_agent: Agent for patient record retrieval.
            literature_agent: Agent for medical literature search.
            protocol_agent: Agent for clinical guideline matching.
            drug_safety_agent: Agent for drug interaction checks.
            guardrails_agent: Agent for response validation.
            openai_client: Azure OpenAI client for LLM calls.
            cosmos_client: Cosmos DB client for persistence.
            embedding_service: Service for embedding generation.
            fusion: Cross-source fusion module for merging agent outputs.
            settings: Application settings instance.
        """
        self.settings = settings or get_settings()
        self._init_openai_client(openai_client)
        self._init_cosmos_client(cosmos_client)

        self.patient_history_agent = patient_history_agent
        self.literature_agent = literature_agent
        self.protocol_agent = protocol_agent
        self.drug_safety_agent = drug_safety_agent
        self.guardrails_agent = guardrails_agent
        self.embedding_service = embedding_service
        self.fusion = fusion

        logger.info("OrchestratorAgent initialized")

    async def _invoke_agent(self, agent: object, task: AgentTask) -> object:
        """Invoke an agent using the canonical ``execute`` contract.

        Falls back to legacy ``process`` for backward compatibility with
        older agent implementations.
        """
        execute_method = getattr(agent, "execute", None)
        if callable(execute_method):
            return await execute_method(task)

        process_method = getattr(agent, "process", None)
        if callable(process_method):
            return await process_method(task)

        raise AgentError(
            message="Agent does not expose an execute/process method.",
            agent_name=task.to_agent,
        )

    # ------------------------------------------------------------------
    # Lazy initialization helpers
    # ------------------------------------------------------------------

    def _init_openai_client(self, client: object | None) -> None:
        """Initialize OpenAI client, creating a default if not supplied."""
        if client is not None:
            self.openai_client = client
        else:
            from cdss.clients.openai_client import AzureOpenAIClient

            self.openai_client = AzureOpenAIClient(self.settings)

    def _init_cosmos_client(self, client: object | None) -> None:
        """Initialize Cosmos DB client, creating a default if not supplied."""
        if client is not None:
            self.cosmos_client = client
        else:
            try:
                from cdss.clients.cosmos_client import CosmosDBClient

                self.cosmos_client = CosmosDBClient(self.settings)
            except Exception:
                logger.warning(
                    "CosmosDBClient initialization failed; conversation history and audit logging will be unavailable"
                )
                self.cosmos_client = None

    # ==================================================================
    # Main entry point
    # ==================================================================

    async def process_query(
        self,
        query: ClinicalQuery,
        clinician_id: str = "system",
    ) -> ClinicalResponse:
        """Process a clinical query end-to-end.

        Steps:
            1. Query Planning -- classify, extract entities, determine agents.
            2. Parallel Agent Dispatch -- send tasks to required agents.
            3. Context Assembly -- merge agent outputs with cross-source fusion.
            4. Clinical Synthesis -- GPT-4o generates recommendation.
            5. Guardrails Validation -- verify safety, citations, scope.
            6. Logging -- save conversation turn and audit log to Cosmos DB.
            7. Return ``ClinicalResponse``.

        Args:
            query: The clinical query to process.
            clinician_id: Identifier of the clinician submitting the query.

        Returns:
            A fully populated ``ClinicalResponse``.
        """
        start_time = time.monotonic()
        trace_id = str(uuid4())
        trace_id_var.set(trace_id)

        logger.info(
            "Processing clinical query",
            extra={
                "query_text": query.text[:200],
                "patient_id": query.patient_id,
                "session_id": query.session_id,
                "clinician_id": clinician_id,
            },
        )

        try:
            # Step 1: Query planning
            plan = await self._plan_query(query)
            logger.info(
                "Query plan created",
                extra={
                    "query_type": plan.query_type,
                    "required_agents": plan.required_agents,
                    "priority": plan.priority,
                },
            )

            # Step 2: Parallel agent dispatch
            agent_outputs = await self._dispatch_agents(plan, query)
            logger.info(
                "Agent dispatch complete",
                extra={"agents_responded": list(agent_outputs.keys())},
            )

            # Step 3-4: Context assembly and clinical synthesis
            response = await self._synthesize_response(query, plan, agent_outputs)

            # Step 5: Guardrails validation
            response = await self._validate_response(response, agent_outputs)

            # Attach agent outputs to the response
            response.agent_outputs = agent_outputs

            # Ensure default disclaimers are always present
            for disclaimer in DEFAULT_DISCLAIMERS:
                if disclaimer not in response.disclaimers:
                    response.disclaimers.append(disclaimer)

            total_latency_ms = int((time.monotonic() - start_time) * 1000)

            # Step 6: Logging (fire-and-forget, do not block the response)
            asyncio.create_task(
                self._log_interaction(
                    query=query,
                    response=response,
                    agent_outputs=agent_outputs,
                    clinician_id=clinician_id,
                    total_latency_ms=total_latency_ms,
                )
            )

            logger.info(
                "Clinical query processed successfully",
                extra={
                    "total_latency_ms": total_latency_ms,
                    "confidence": response.confidence_score,
                    "citations_count": len(response.citations),
                    "drug_alerts_count": len(response.drug_alerts),
                },
            )

            return response

        except CDSSError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error processing clinical query",
                extra={"error": str(exc)},
                exc_info=True,
            )
            raise AgentError(
                message=f"Orchestrator failed to process query: {exc}",
                agent_name="orchestrator",
            ) from exc

    # ==================================================================
    # Step 1 -- Query Planning
    # ==================================================================

    async def _plan_query(self, query: ClinicalQuery) -> QueryPlan:
        """Use GPT-4o-mini to classify the query and build an execution plan.

        The LLM classifies the query into a type (diagnosis, treatment,
        drug_check, general, emergency) and determines which specialist
        agents are required.  Sub-queries tailored for each agent are also
        generated.

        Args:
            query: The clinical query to plan for.

        Returns:
            A ``QueryPlan`` describing the execution strategy.
        """
        # Use the OpenAI client's classify_query for initial classification
        classification = await self.openai_client.classify_query(query.text)

        # Map the classification's query_type to our broader set
        raw_type = classification.get("query_type", "general")
        query_type_map = {
            "diagnosis": "diagnosis",
            "treatment": "treatment",
            "drug_check": "drug_check",
            "general": "general",
            "emergency": "emergency",
        }
        query_type = query_type_map.get(raw_type, "general")

        # Extract entities from classification
        entities = classification.get("entities", [])

        # Update query with classification results if not already set
        if query.intent is None:
            query.intent = query_type
        if query.extracted_entities is None and entities:
            from cdss.core.models import ExtractedEntity

            query.extracted_entities = [
                ExtractedEntity(
                    entity_type="condition" if "condition" in str(e).lower() else "medication",
                    value=str(e),
                )
                for e in entities
            ]

        # Now generate the full execution plan with sub-queries
        messages = [
            {"role": "system", "content": QUERY_PLAN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "query": query.text,
                        "patient_id": query.patient_id,
                        "initial_classification": query_type,
                        "entities": entities,
                    }
                ),
            },
        ]

        result = await self.openai_client.chat_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        try:
            plan_data = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse query plan JSON, using fallback plan",
                extra={"content": result["content"][:500]},
            )
            plan_data = {
                "query_type": query_type,
                "required_agents": classification.get("required_agents", ["literature"]),
                "sub_queries": {"literature": query.text},
                "priority": "medium",
                "parallel_dispatch": True,
            }

        # Normalize query_type to a valid literal value
        valid_types = {"diagnosis", "treatment", "drug_check", "general", "emergency"}
        plan_query_type = plan_data.get("query_type", query_type)
        if plan_query_type not in valid_types:
            plan_query_type = query_type

        # Normalize required_agents
        valid_agents = {"patient_history", "literature", "protocol", "drug_safety"}
        required_agents = [a for a in plan_data.get("required_agents", []) if a in valid_agents]

        # Ensure patient_history is included when a patient_id is present
        if query.patient_id and "patient_history" not in required_agents:
            required_agents.insert(0, "patient_history")

        # For emergency queries, include all agents
        if plan_query_type == "emergency":
            required_agents = list(valid_agents)

        # Fallback: always query at least the literature agent
        if not required_agents:
            required_agents = ["literature"]

        # Build sub-queries, using the original query as fallback
        sub_queries = plan_data.get("sub_queries", {})
        for agent in required_agents:
            if agent not in sub_queries:
                sub_queries[agent] = query.text

        # Normalize priority
        valid_priorities = {"low", "medium", "high", "critical"}
        priority = plan_data.get("priority", "medium")
        if priority not in valid_priorities:
            priority = "medium"

        return QueryPlan(
            query_type=plan_query_type,
            required_agents=required_agents,
            sub_queries=sub_queries,
            priority=priority,
            parallel_dispatch=plan_data.get("parallel_dispatch", True),
        )

    # ==================================================================
    # Step 2 -- Parallel Agent Dispatch
    # ==================================================================

    async def _dispatch_agents(self, plan: QueryPlan, query: ClinicalQuery) -> dict[str, AgentOutput]:
        """Dispatch tasks to required agents in parallel.

        Creates an ``AgentTask`` for each agent listed in the plan and
        executes them concurrently via ``asyncio.gather``.  Individual
        agent failures are caught and logged; the orchestrator continues
        with partial results when possible.

        Args:
            plan: The query execution plan.
            query: The original clinical query.

        Returns:
            A mapping of agent name to ``AgentOutput``.
        """
        session_id = query.session_id or str(uuid4())
        trace_id = trace_id_var.get(str(uuid4()))

        tasks: dict[str, asyncio.Task] = {}
        timeout = self.settings.response_timeout_seconds or AGENT_TIMEOUT_SECONDS

        for agent_name in plan.required_agents:
            sub_query = plan.sub_queries.get(agent_name, query.text)

            task_payload: dict = {
                "query": sub_query,
                "original_query": query.text,
                "patient_id": query.patient_id,
            }

            # Enrich payload based on agent type
            if agent_name == "patient_history":
                task_payload["patient_id"] = query.patient_id

            elif agent_name == "literature":
                task_payload["entities"] = [e.value for e in (query.extracted_entities or [])]

            elif agent_name == "protocol":
                task_payload["conditions"] = [
                    e.value for e in (query.extracted_entities or []) if e.entity_type == "condition"
                ]

            elif agent_name == "drug_safety":
                task_payload["medications"] = [
                    e.value for e in (query.extracted_entities or []) if e.entity_type == "medication"
                ]

            agent_task = AgentTask(
                from_agent="orchestrator",
                to_agent=agent_name,
                message_type="task_request",
                payload=task_payload,
                session_id=session_id,
                trace_id=trace_id,
            )

            coro = self._execute_agent(agent_name, agent_task, timeout)
            tasks[agent_name] = asyncio.create_task(coro, name=f"agent-{agent_name}")

        # Await all agent tasks concurrently
        results: dict[str, AgentOutput] = {}
        if tasks:
            done_values = await asyncio.gather(*tasks.values(), return_exceptions=True)

            for agent_name_key, value in zip(tasks.keys(), done_values, strict=False):
                if isinstance(value, AgentOutput):
                    results[agent_name_key] = value
                elif isinstance(value, Exception):
                    logger.error(
                        "Agent execution failed",
                        extra={
                            "agent": agent_name_key,
                            "error": str(value),
                        },
                    )
                    results[agent_name_key] = AgentOutput(
                        agent_name=agent_name_key,
                        latency_ms=0,
                        sources_retrieved=0,
                        summary=f"Agent '{agent_name_key}' failed: {value}",
                        raw_data={"error": str(value)},
                    )

        return results

    async def _execute_agent(self, agent_name: str, task: AgentTask, timeout: int) -> AgentOutput:
        """Execute a single agent with a timeout guard.

        Args:
            agent_name: Name of the agent to execute.
            task: The ``AgentTask`` describing the work.
            timeout: Maximum seconds to wait for the agent.

        Returns:
            The ``AgentOutput`` produced by the agent.

        Raises:
            AgentTimeoutError: If the agent exceeds the timeout.
            AgentError: If the agent encounters an error.
        """
        start_ms = time.monotonic()

        agent_map: dict[str, object | None] = {
            "patient_history": self.patient_history_agent,
            "literature": self.literature_agent,
            "protocol": self.protocol_agent,
            "drug_safety": self.drug_safety_agent,
        }

        agent = agent_map.get(agent_name)
        if agent is None:
            logger.warning(
                "No agent registered for '%s', generating placeholder output",
                agent_name,
            )
            return AgentOutput(
                agent_name=agent_name,
                latency_ms=0,
                sources_retrieved=0,
                summary=(f"Agent '{agent_name}' is not configured. No data was retrieved for this component."),
                raw_data=None,
            )

        try:
            result = await asyncio.wait_for(
                self._invoke_agent(agent, task),
                timeout=timeout,
            )

            latency_ms = int((time.monotonic() - start_ms) * 1000)

            # If the agent returned a dict, wrap it in AgentOutput
            if isinstance(result, dict):
                return AgentOutput(
                    agent_name=agent_name,
                    latency_ms=latency_ms,
                    sources_retrieved=result.get("sources_retrieved", 0),
                    summary=result.get("summary", ""),
                    raw_data=result,
                )

            # If already an AgentOutput, update latency
            if isinstance(result, AgentOutput):
                result.latency_ms = latency_ms
                return result

            # Unexpected return type
            return AgentOutput(
                agent_name=agent_name,
                latency_ms=latency_ms,
                sources_retrieved=0,
                summary=str(result),
                raw_data=None,
            )

        except TimeoutError as exc:
            latency_ms = int((time.monotonic() - start_ms) * 1000)
            logger.error(
                "Agent timed out",
                extra={"agent": agent_name, "timeout_seconds": timeout},
            )
            raise AgentTimeoutError(
                message=f"Agent '{agent_name}' timed out after {timeout}s",
                agent_name=agent_name,
                timeout_seconds=float(timeout),
            ) from exc

        except AgentTimeoutError:
            raise

        except Exception as exc:
            latency_ms = int((time.monotonic() - start_ms) * 1000)
            logger.error(
                "Agent execution error",
                extra={"agent": agent_name, "error": str(exc)},
                exc_info=True,
            )
            raise AgentError(
                message=f"Agent '{agent_name}' failed: {exc}",
                agent_name=agent_name,
            ) from exc

    # ==================================================================
    # Steps 3-4 -- Context Assembly & Clinical Synthesis
    # ==================================================================

    async def _synthesize_response(
        self,
        query: ClinicalQuery,
        plan: QueryPlan,
        agent_outputs: dict[str, AgentOutput],
    ) -> ClinicalResponse:
        """Assemble context from agent outputs and synthesize a recommendation.

        Uses cross-source fusion (when available) to merge agent outputs,
        then calls GPT-4o with structured JSON output to produce the final
        clinical recommendation.

        Args:
            query: The original clinical query.
            plan: The execution plan.
            agent_outputs: Outputs collected from specialist agents.

        Returns:
            A ``ClinicalResponse`` with assessment, recommendation, citations, etc.
        """
        # Build the context prompt from agent outputs
        context_sections: list[str] = []

        for agent_name, output in agent_outputs.items():
            section = f"--- {agent_name.upper()} AGENT OUTPUT ---\n"
            section += f"Summary: {output.summary}\n"
            if output.raw_data:
                # Include structured data (truncated to prevent token overflow)
                raw_str = json.dumps(output.raw_data, default=str)
                if len(raw_str) > 3000:
                    raw_str = raw_str[:3000] + "... [truncated]"
                section += f"Data: {raw_str}\n"
            section += f"Sources Retrieved: {output.sources_retrieved}\n"
            section += f"Latency: {output.latency_ms}ms\n"
            context_sections.append(section)

        # If a fusion module is available, use it for enhanced context assembly
        if self.fusion is not None:
            try:
                fused_context = self.fusion.build_context_prompt(agent_outputs)
                context_sections.append(f"--- CROSS-SOURCE FUSION ---\n{fused_context}\n")
            except Exception as exc:
                logger.warning(
                    "Cross-source fusion failed, proceeding without it",
                    extra={"error": str(exc)},
                )

        # Resolve conflicts between agent outputs
        conflict_notes = await self._resolve_conflicts(agent_outputs)
        if conflict_notes:
            conflict_section = "--- CONFLICT RESOLUTION NOTES ---\n"
            for note in conflict_notes:
                conflict_section += f"- {note}\n"
            context_sections.append(conflict_section)

        context_prompt = "\n".join(context_sections)

        # Build messages for GPT-4o synthesis
        messages = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Clinical Query: {query.text}\n\n"
                    f"Query Type: {plan.query_type}\n"
                    f"Patient ID: {query.patient_id or 'Not provided'}\n\n"
                    f"Agent Context:\n{context_prompt}"
                ),
            },
        ]

        result = await self.openai_client.chat_completion(
            messages=messages,
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        try:
            response_data = json.loads(result["content"])
        except json.JSONDecodeError:
            logger.error(
                "Failed to parse synthesis response JSON",
                extra={"content": result["content"][:500]},
            )
            return ClinicalResponse(
                assessment="Unable to generate a structured assessment.",
                recommendation=result["content"],
                evidence_summary=[],
                confidence_score=0.3,
                citations=[],
                disclaimers=list(DEFAULT_DISCLAIMERS),
            )

        # Parse citations from the response data
        citations: list[Citation] = []
        for cit_data in response_data.get("citations", []):
            try:
                valid_source_types = {
                    "pubmed",
                    "guideline",
                    "patient_record",
                    "drug_database",
                }
                source_type = cit_data.get("source_type", "pubmed")
                if source_type not in valid_source_types:
                    source_type = "pubmed"

                citations.append(
                    Citation(
                        source_type=source_type,
                        identifier=str(cit_data.get("identifier", "")),
                        title=str(cit_data.get("title", "")),
                        relevance_score=max(
                            0.0,
                            min(1.0, float(cit_data.get("relevance_score", 0.5))),
                        ),
                        url=cit_data.get("url"),
                    )
                )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping invalid citation",
                    extra={"citation_data": str(cit_data), "error": str(exc)},
                )

        # Parse drug alerts from agent outputs
        drug_alerts: list[DrugAlert] = []
        drug_safety_output = agent_outputs.get("drug_safety")
        if drug_safety_output and drug_safety_output.raw_data:
            raw_alerts = drug_safety_output.raw_data.get(
                "drug_alerts",
                drug_safety_output.raw_data.get("alerts", []),
            )
            for alert_data in raw_alerts:
                try:
                    severity = alert_data.get("severity", "moderate")
                    if severity not in ("minor", "moderate", "major"):
                        severity = "moderate"
                    drug_alerts.append(
                        DrugAlert(
                            severity=severity,
                            description=str(alert_data.get("description", "")),
                            source=str(alert_data.get("source", "unknown")),
                            evidence_level=max(
                                1,
                                min(5, int(alert_data.get("evidence_level", 3))),
                            ),
                            alternatives=alert_data.get("alternatives", []),
                        )
                    )
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Skipping invalid drug alert",
                        extra={"alert_data": str(alert_data), "error": str(exc)},
                    )

        # Clamp confidence score
        confidence = max(0.0, min(1.0, float(response_data.get("confidence_score", 0.5))))

        return ClinicalResponse(
            assessment=response_data.get("assessment", "Assessment could not be generated."),
            recommendation=response_data.get("recommendation", "No recommendation available."),
            evidence_summary=response_data.get("evidence_summary", []),
            drug_alerts=drug_alerts,
            confidence_score=confidence,
            citations=citations,
            disclaimers=list(DEFAULT_DISCLAIMERS),
        )

    # ==================================================================
    # Step 5 -- Guardrails Validation
    # ==================================================================

    async def _validate_response(
        self,
        response: ClinicalResponse,
        agent_outputs: dict[str, AgentOutput],
    ) -> ClinicalResponse:
        """Run guardrails validation on the synthesized response.

        If a dedicated guardrails agent is available, it is used.
        Otherwise, GPT-4o-mini performs the validation directly.

        When validation fails and the confidence score is below the
        configured threshold, the response is modified with additional
        disclaimers and a lowered confidence score.

        Args:
            response: The synthesized clinical response.
            agent_outputs: Agent outputs for cross-referencing.

        Returns:
            The (potentially modified) ``ClinicalResponse``.
        """
        try:
            if self.guardrails_agent is not None:
                guardrails_task = AgentTask(
                    from_agent="orchestrator",
                    to_agent="guardrails",
                    message_type="task_request",
                    payload={
                        "response": response.model_dump(mode="json"),
                        "agent_outputs": {name: out.model_dump(mode="json") for name, out in agent_outputs.items()},
                    },
                    session_id=str(uuid4()),
                    trace_id=trace_id_var.get(str(uuid4())),
                )

                validation_result = await asyncio.wait_for(
                    self._invoke_agent(self.guardrails_agent, guardrails_task),
                    timeout=AGENT_TIMEOUT_SECONDS,
                )

                if isinstance(validation_result, GuardrailsResult):
                    guardrails = validation_result
                elif isinstance(validation_result, AgentOutput):
                    guardrails = self._parse_guardrails_payload(validation_result.raw_data)
                elif isinstance(validation_result, dict):
                    guardrails = self._parse_guardrails_payload(validation_result)
                else:
                    guardrails = GuardrailsResult(is_valid=True)
            else:
                guardrails = await self._validate_with_llm(response, agent_outputs)

        except Exception as exc:
            logger.warning(
                "Guardrails validation failed, applying conservative defaults",
                extra={"error": str(exc)},
            )
            guardrails = GuardrailsResult(
                is_valid=True,
                disclaimers=[
                    "Guardrails validation could not be completed. Exercise additional caution with this response."
                ],
            )

        # Apply guardrails results
        if not guardrails.is_valid:
            logger.warning(
                "Response failed guardrails validation",
                extra={
                    "hallucination_flags": guardrails.hallucination_flags,
                    "safety_concerns": guardrails.safety_concerns,
                },
            )

            # Lower confidence when guardrails fail
            confidence_threshold = self.settings.confidence_threshold
            if response.confidence_score > confidence_threshold:
                response.confidence_score = max(
                    confidence_threshold - 0.1,
                    response.confidence_score * 0.7,
                )

            # Add safety concern disclaimers
            for concern in guardrails.safety_concerns:
                disclaimer = f"SAFETY CONCERN: {concern}"
                if disclaimer not in response.disclaimers:
                    response.disclaimers.append(disclaimer)

            # Add hallucination warnings
            for flag in guardrails.hallucination_flags:
                disclaimer = f"VERIFICATION NEEDED: {flag}"
                if disclaimer not in response.disclaimers:
                    response.disclaimers.append(disclaimer)

        # Always append any extra disclaimers from guardrails
        for disclaimer in guardrails.disclaimers:
            if disclaimer not in response.disclaimers:
                response.disclaimers.append(disclaimer)

        return response

    def _parse_guardrails_payload(
        self,
        payload: dict | None,
    ) -> GuardrailsResult:
        """Normalize guardrails payloads into a ``GuardrailsResult`` model."""
        if not isinstance(payload, dict):
            return GuardrailsResult(is_valid=True)

        candidate = payload.get("guardrails_result", payload)
        if not isinstance(candidate, dict):
            return GuardrailsResult(is_valid=True)

        try:
            return GuardrailsResult(
                is_valid=bool(candidate.get("is_valid", True)),
                hallucination_flags=list(candidate.get("hallucination_flags", [])),
                safety_concerns=list(candidate.get("safety_concerns", [])),
                disclaimers=list(candidate.get("disclaimers", [])),
            )
        except (TypeError, ValueError):
            return GuardrailsResult(is_valid=True)

    async def _validate_with_llm(
        self,
        response: ClinicalResponse,
        agent_outputs: dict[str, AgentOutput],
    ) -> GuardrailsResult:
        """Validate the response using GPT-4o-mini when no guardrails agent is available.

        Args:
            response: The clinical response to validate.
            agent_outputs: Agent outputs for cross-referencing.

        Returns:
            A ``GuardrailsResult`` from the LLM validation.
        """
        agent_context = "\n".join(f"[{name}]: {out.summary}" for name, out in agent_outputs.items())

        messages = [
            {"role": "system", "content": GUARDRAILS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Clinical Response to Validate:\n"
                    f"Assessment: {response.assessment}\n"
                    f"Recommendation: {response.recommendation}\n"
                    f"Evidence Summary: {json.dumps(response.evidence_summary)}\n"
                    f"Confidence: {response.confidence_score}\n\n"
                    f"Agent Outputs for Cross-Reference:\n{agent_context}\n\n"
                    f"Citations: {json.dumps([c.model_dump(mode='json') for c in response.citations])}"
                ),
            },
        ]

        result = await self.openai_client.chat_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        try:
            validation_data = json.loads(result["content"])
            return GuardrailsResult(
                is_valid=bool(validation_data.get("is_valid", True)),
                hallucination_flags=validation_data.get("hallucination_flags", []),
                safety_concerns=validation_data.get("safety_concerns", []),
                disclaimers=validation_data.get("disclaimers", []),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "Failed to parse guardrails LLM response",
                extra={"error": str(exc)},
            )
            return GuardrailsResult(is_valid=True)

    # ==================================================================
    # Conflict Resolution
    # ==================================================================

    async def _resolve_conflicts(self, agent_outputs: dict[str, AgentOutput]) -> list[str]:
        """Resolve conflicts between agent outputs.

        Conflict resolution rules (from architecture):
            1. Drug Safety always wins -- safety alerts override all other outputs.
            2. Patient-specific data > generic guidelines.
            3. Evidence hierarchy: RCTs > cohort > case reports > expert opinion.
            4. Explicit uncertainty when unresolvable.

        Args:
            agent_outputs: Outputs from all dispatched agents.

        Returns:
            A list of human-readable conflict resolution notes.
        """
        notes: list[str] = []

        if len(agent_outputs) < 2:
            return notes

        # Rule 1: Drug Safety always wins
        drug_safety_output = agent_outputs.get("drug_safety")
        if drug_safety_output and drug_safety_output.raw_data:
            alerts = drug_safety_output.raw_data.get("alerts", [])
            interactions = drug_safety_output.raw_data.get("interactions", [])
            if alerts or interactions:
                notes.append(
                    "PRIORITY: Drug safety alerts detected. "
                    "Drug interaction and safety information takes precedence "
                    "over other agent recommendations."
                )

        # Rule 2: Patient-specific data > generic guidelines
        patient_output = agent_outputs.get("patient_history")
        protocol_output = agent_outputs.get("protocol")
        if patient_output and protocol_output:
            if patient_output.sources_retrieved > 0:
                notes.append(
                    "Patient-specific clinical data is available and should be "
                    "weighted more heavily than generic guideline recommendations."
                )

        # Rule 3: Evidence hierarchy
        literature_output = agent_outputs.get("literature")
        if literature_output and literature_output.raw_data:
            evidence_level = literature_output.raw_data.get("evidence_level", "")
            if "systematic review" in evidence_level.lower() or "rct" in evidence_level.lower():
                notes.append(
                    "High-quality evidence (systematic reviews/RCTs) is available "
                    "and should be given the greatest weight."
                )
            elif "case report" in evidence_level.lower() or "expert" in evidence_level.lower():
                notes.append(
                    "Available evidence is primarily from case reports or expert opinion. "
                    "Recommendations should be interpreted with appropriate caution."
                )

        # Rule 4: Explicit uncertainty detection
        low_confidence_agents = [
            name for name, output in agent_outputs.items() if output.sources_retrieved == 0 and output.raw_data is None
        ]
        if low_confidence_agents:
            agent_list = ", ".join(low_confidence_agents)
            notes.append(
                f"Limited data from agent(s): {agent_list}. "
                "Recommendation confidence may be reduced due to incomplete evidence."
            )

        # Check for contradictions between protocol and literature
        if protocol_output and literature_output:
            protocol_summary = protocol_output.summary.lower()
            literature_summary = literature_output.summary.lower()
            # Simple heuristic: look for negation patterns
            contradiction_markers = [
                ("recommend", "not recommend"),
                ("indicated", "contraindicated"),
                ("beneficial", "harmful"),
                ("safe", "unsafe"),
            ]
            for positive, negative in contradiction_markers:
                if (positive in protocol_summary and negative in literature_summary) or (
                    negative in protocol_summary and positive in literature_summary
                ):
                    notes.append(
                        "Potential contradiction detected between protocol guidelines "
                        "and medical literature. Review both sources carefully before "
                        "making a clinical decision."
                    )
                    break

        return notes

    # ==================================================================
    # Step 6 -- Interaction Logging
    # ==================================================================

    async def _log_interaction(
        self,
        query: ClinicalQuery,
        response: ClinicalResponse,
        agent_outputs: dict[str, AgentOutput],
        clinician_id: str,
        total_latency_ms: int,
    ) -> None:
        """Save the conversation turn and audit log entry to Cosmos DB.

        This method is designed to be called as a fire-and-forget task so
        that logging does not block the response to the clinician.  Errors
        are logged but not propagated.

        Args:
            query: The original clinical query.
            response: The final clinical response.
            agent_outputs: Outputs from dispatched agents.
            clinician_id: Identifier of the clinician.
            total_latency_ms: Total processing time in milliseconds.
        """
        if self.cosmos_client is None:
            logger.debug("Cosmos DB client not available, skipping interaction logging")
            return

        session_id = query.session_id or str(uuid4())
        now = datetime.now(timezone.utc)

        # Save conversation turn
        try:
            # Determine turn number by querying existing history
            existing_turns = await self.cosmos_client.get_conversation_history(session_id=session_id, limit=1)
            turn_number = len(existing_turns) + 1

            # Build guardrails result for the turn
            guardrails_result = GuardrailsResult(
                is_valid=True,
                hallucination_flags=[],
                safety_concerns=[
                    d.replace("SAFETY CONCERN: ", "") for d in response.disclaimers if d.startswith("SAFETY CONCERN:")
                ],
                disclaimers=response.disclaimers,
            )

            turn = ConversationTurn(
                session_id=session_id,
                patient_id=query.patient_id or "unknown",
                turn_number=turn_number,
                timestamp=now,
                clinician_id=clinician_id,
                query=query,
                agent_outputs={name: out for name, out in agent_outputs.items()},
                response=response,
                guardrails=guardrails_result,
                total_latency_ms=total_latency_ms,
            )

            await self.cosmos_client.save_conversation_turn(turn.model_dump(mode="json"))
            logger.debug(
                "Conversation turn saved",
                extra={
                    "session_id": session_id,
                    "turn_number": turn_number,
                },
            )

        except Exception as exc:
            logger.error(
                "Failed to save conversation turn",
                extra={"error": str(exc)},
            )

        # Save audit log entry
        try:
            audit_entry = AuditLogEntry(
                date_partition=now.strftime("%Y-%m-%d"),
                event_type="clinical_query",
                timestamp=now,
                actor={
                    "clinician_id": clinician_id,
                    "role": "clinician",
                },
                action="process_clinical_query",
                resource={
                    "type": "clinical_query",
                    "id": session_id,
                },
                session_id=session_id,
                justification=f"Clinical query: {query.text[:200]}",
                outcome="success",
                data_sent_to_llm=True,
                phi_fields_sent=(["patient_id", "conditions", "medications", "allergies"] if query.patient_id else []),
                phi_fields_redacted=["demographics.name", "demographics.ssn"],
            )

            await self.cosmos_client.log_audit_event(audit_entry.model_dump(mode="json"))
            logger.debug("Audit log entry saved", extra={"session_id": session_id})

        except Exception as exc:
            logger.error(
                "Failed to save audit log entry",
                extra={"error": str(exc)},
            )
