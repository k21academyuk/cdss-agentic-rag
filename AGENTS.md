# AGENTS.md - CDSS Agentic RAG Codebase Guide

This document provides essential context for AI coding agents working on the Clinical Decision Support System (CDSS) with Agentic RAG.

## Project Overview

A production-grade clinical decision support platform orchestrating five specialized AI agents (Patient History, Medical Literature, Protocol, Drug Safety, Guardrails) to synthesize patient records, medical literature, treatment protocols, and drug safety data into evidence-based clinical recommendations.

**Tech Stack**: Python 3.12, FastAPI, Azure OpenAI (GPT-4o/GPT-4o-mini), Azure AI Search, Azure Cosmos DB, Redis, Pydantic, pytest.

## Build/Lint/Test Commands

```bash
# Install dependencies (create venv first)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run linter (Ruff)
ruff check src/

# Format code
ruff format src/

# Run type checker (mypy - strict mode)
mypy src/

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=cdss --cov-report=term-missing

# Run a single test file
pytest tests/unit/test_orchestrator.py -v

# Run a single test class
pytest tests/unit/test_orchestrator.py::TestOrchestratorProcessQuery -v

# Run a single test function
pytest tests/unit/test_orchestrator.py::TestOrchestratorProcessQuery::test_end_to_end_treatment_query -v

# Run only unit tests
pytest tests/unit/ -v

# Run integration tests (requires Azure credentials)
pytest tests/integration/ -v

# Run development server
uvicorn cdss.api.app:app --reload --host 0.0.0.0 --port 8000

# Run with Docker
docker-compose up --build
```

## Code Style Guidelines

### Imports

```python
# Standard library imports (alphabetical)
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

# Third-party imports (alphabetical)
from openai import AsyncAzureOpenAI
from pydantic import BaseModel, Field

# Local imports (alphabetical, use full module path)
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import CDSSError, AgentError
from cdss.core.logging import get_logger
```

**Rules**:
- Always include `from __future__ import annotations` for modern type hints
- Group imports: stdlib, third-party, local (separated by blank lines)
- Alphabetical ordering within each group
- Use explicit imports; avoid `from module import *`

### Formatting (Ruff)

- **Line length**: 120 characters
- **Target**: Python 3.12
- **Quote style**: Double quotes for strings
- **Indentation**: 4 spaces

```bash
# Check and fix formatting
ruff format src/
ruff check src/ --fix
```

### Type Hints (Strict mypy)

All functions must have complete type annotations. mypy runs in strict mode.

```python
# Good: Complete type annotations
async def process_query(
    self,
    query: ClinicalQuery,
    clinician_id: str = "system",
) -> ClinicalResponse:
    ...

# Good: Optional types with | None
def get_patient(self, patient_id: str) -> dict | None:
    ...

# Good: Literal types for enums
severity: Literal["minor", "moderate", "major"]

# Good: Collections with type parameters
conditions: list[MedicalCondition]
agent_outputs: dict[str, AgentOutput]
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `OrchestratorAgent`, `ClinicalQuery` |
| Functions/Methods | snake_case | `process_query`, `_plan_query` |
| Variables | snake_case | `agent_outputs`, `query_type` |
| Constants | SCREAMING_SNAKE | `DEFAULT_MAX_RETRIES`, `AGENT_TIMEOUT_SECONDS` |
| Private methods | Leading underscore | `_init_openai_client`, `_dispatch_agents` |
| Pydantic models | PascalCase | `PatientProfile`, `DrugAlert` |
| Module names | snake_case | `orchestrator.py`, `openai_client.py` |

### Pydantic Models

Use Pydantic v2 with `Field` for validation and documentation:

```python
class ClinicalQuery(BaseModel):
    """A clinical question submitted by a clinician."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"text": "What are treatment options for...?"}]
        }
    )

    text: str = Field(
        ...,
        min_length=1,
        description="The clinical question in natural language.",
    )
    patient_id: str | None = Field(
        default=None,
        description="Patient ID to load context from the patient profile.",
    )
```

### Error Handling

Use the custom exception hierarchy in `cdss.core.exceptions`:

```python
from cdss.core.exceptions import (
    CDSSError,
    AgentError,
    AgentTimeoutError,
    AzureServiceError,
    RetrieverError,
    DrugSafetyError,
    GuardrailsViolation,
    RateLimitError,
)

# Raise specific exceptions with context
raise AgentError(
    message=f"Agent '{agent_name}' failed: {exc}",
    agent_name=agent_name,
    details={"original_error": str(exc)},
)

# Catch at appropriate levels
try:
    result = await agent.process(task)
except AgentTimeoutError:
    logger.error("Agent timed out", extra={"agent": agent_name})
    raise
except CDSSError:
    raise  # Re-raise CDSS errors
except Exception as exc:
    # Wrap unexpected errors
    raise AgentError(message=str(exc), agent_name=agent_name) from exc
```

### Logging

Use structured logging with `structlog` via `get_logger`:

```python
from cdss.core.logging import get_logger

logger = get_logger(__name__)

logger.info(
    "Processing clinical query",
    extra={
        "query_text": query.text[:200],
        "patient_id": query.patient_id,
    },
)

logger.error(
    "Agent execution failed",
    extra={"agent": agent_name, "error": str(exc)},
    exc_info=True,
)
```

### Async Patterns

Use `asyncio` for concurrent operations:

```python
# Parallel execution with gather
results = await asyncio.gather(
    *tasks.values(),
    return_exceptions=True,
)

# Timeout handling
try:
    result = await asyncio.wait_for(
        agent.process(task),
        timeout=timeout_seconds,
    )
except asyncio.TimeoutError:
    raise AgentTimeoutError(...)

# Fire-and-forget tasks
asyncio.create_task(self._log_interaction(...))
```

## Project Structure

```
src/cdss/
├── agents/           # Specialist agents + orchestrator
│   ├── orchestrator.py    # Main coordinator (GPT-4o)
│   ├── patient_history.py # Patient record retrieval
│   ├── medical_literature.py  # PubMed search
│   ├── protocol.py    # Treatment protocols
│   ├── drug_safety.py # Drug interactions
│   └── guardrails.py  # Safety validation
├── api/              # FastAPI routes and schemas
├── clients/          # Azure + external API clients
├── core/             # config, models, exceptions, logging
├── ingestion/        # Document processing pipeline
├── rag/              # RAG pipeline (retriever, chunker, etc.)
├── services/         # Business logic services
└── utils/            # Shared utilities

tests/
├── conftest.py       # Shared fixtures
├── unit/             # Unit tests (mocked)
├── integration/      # Integration tests (real services)
└── e2e/              # End-to-end tests
```

## Key Domain Models

- **ClinicalQuery**: Input query with patient_id, intent, extracted entities
- **ClinicalResponse**: Output with assessment, recommendation, citations, drug_alerts, confidence_score
- **PatientProfile**: Demographics, conditions, medications, allergies, labs
- **AgentOutput**: Agent response with summary, latency, sources_retrieved
- **QueryPlan**: Execution plan with required_agents, sub_queries, priority

## Agent Architecture

1. **OrchestratorAgent** receives query → classifies → dispatches to specialists
2. **Specialist agents** run in parallel via `asyncio.gather`
3. **GuardrailsAgent** validates final response for hallucinations and safety
4. **Conflict resolution**: Drug safety wins > patient data > generic guidelines

## Environment Variables

Copy `.env.example` to `.env` and configure Azure credentials. All settings use `CDSS_` prefix via Pydantic Settings.

## Before Committing

1. Run `ruff check src/` and `ruff format src/`
2. Run `mypy src/` (must pass with no errors)
3. Run `pytest tests/ -v` (all tests must pass)
4. Ensure new code has corresponding tests in `tests/`
