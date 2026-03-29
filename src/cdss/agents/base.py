"""Base agent class for all CDSS specialist agents.

Provides a standardized execution lifecycle with timing, error handling,
structured logging, and a consistent AgentOutput contract. All specialist
agents must inherit from BaseAgent and implement the _execute method.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from cdss.core.exceptions import AgentError
from cdss.core.logging import get_logger
from cdss.core.models import AgentOutput, AgentTask


class BaseAgent(ABC):
    """Base class for all CDSS agents.

    Every specialist agent inherits from this class and implements the
    ``_execute`` method. The public ``execute`` method wraps ``_execute``
    with automatic latency measurement, structured logging, and error
    handling that converts uncaught exceptions into ``AgentError``.

    Attributes:
        name: Unique agent identifier used in logs and AgentOutput.
        model: Azure OpenAI deployment name for this agent's LLM calls.
        logger: Structured logger scoped to ``agent.<name>``.
    """

    def __init__(self, name: str, model: str = "gpt-4o") -> None:
        """Initialize the base agent.

        Args:
            name: Unique agent name (e.g., ``"patient_history_agent"``).
            model: Azure OpenAI deployment name (e.g., ``"gpt-4o"`` or ``"gpt-4o-mini"``).
        """
        self.name = name
        self.model = model
        self.logger = get_logger(f"agent.{name}")

    async def execute(self, task: AgentTask) -> AgentOutput:
        """Execute the agent task with timing and error handling.

        Wraps the subclass ``_execute`` implementation with:
        - Performance timing (latency_ms).
        - Structured logging of start, completion, and failure events.
        - Conversion of uncaught exceptions to ``AgentError``.

        Args:
            task: The agent task containing the payload with input parameters.

        Returns:
            A standardized ``AgentOutput`` with the agent's summary,
            source count, latency, and raw structured data.

        Raises:
            AgentError: If the agent's internal ``_execute`` raises any exception.
        """
        self.logger.info(
            "Agent execution started",
            extra={
                "agent_name": self.name,
                "task_id": task.message_id,
                "session_id": task.session_id,
            },
        )

        start = time.perf_counter()
        try:
            result = await self._execute(task)
            latency = int((time.perf_counter() - start) * 1000)

            output = AgentOutput(
                agent_name=self.name,
                latency_ms=latency,
                sources_retrieved=result.get("sources_retrieved", 0),
                summary=result.get("summary", ""),
                raw_data=result,
            )

            self.logger.info(
                "Agent execution completed",
                extra={
                    "agent_name": self.name,
                    "task_id": task.message_id,
                    "latency_ms": latency,
                    "sources_retrieved": output.sources_retrieved,
                },
            )

            return output

        except AgentError:
            # Re-raise AgentErrors without wrapping
            raise

        except Exception as exc:
            latency = int((time.perf_counter() - start) * 1000)
            self.logger.error(
                "Agent execution failed",
                extra={
                    "agent_name": self.name,
                    "task_id": task.message_id,
                    "latency_ms": latency,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise AgentError(
                message=f"Agent {self.name} failed after {latency}ms: {exc}",
                agent_name=self.name,
                details={
                    "task_id": task.message_id,
                    "session_id": task.session_id,
                    "latency_ms": latency,
                    "error_type": type(exc).__name__,
                },
            ) from exc

    async def process(self, task: AgentTask) -> AgentOutput:
        """Compatibility alias for legacy callers that still use ``process``."""
        return await self.execute(task)

    @abstractmethod
    async def _execute(self, task: AgentTask) -> dict:
        """Implement agent-specific logic.

        Subclasses must override this method to perform their specialized
        clinical reasoning. The returned dict must include:

        - ``"summary"`` (str): Human-readable summary of findings.
        - ``"sources_retrieved"`` (int): Number of sources consulted.

        Any additional keys are preserved in ``AgentOutput.raw_data``.

        Args:
            task: The agent task containing the payload with input parameters.

        Returns:
            Dictionary with at minimum ``summary`` and ``sources_retrieved`` keys,
            plus any agent-specific structured data.
        """
