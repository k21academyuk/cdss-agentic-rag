"""FastAPI application factory for the Clinical Decision Support System.

Creates and configures the FastAPI app with middleware, routes, exception
handlers, and lifecycle management (startup / shutdown).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cdss.api.middleware import register_middleware
from cdss.api.routes import router, set_query_service
from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import CDSSError
from cdss.core.logging import get_logger, setup_logging
from cdss.services.query_service import ClinicalQueryService

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up structured logging, middleware, routes, exception handlers, and
    application lifespan hooks for initializing and tearing down resources.

    Args:
        settings: Optional settings override. When ``None``, settings are
            loaded from environment variables and the ``.env`` file.

    Returns:
        A fully configured ``FastAPI`` application instance.
    """
    settings = settings or get_settings()

    # Configure structured logging before anything else
    setup_logging(
        level=settings.log_level,
        json_format=not settings.debug,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Manage application startup and shutdown lifecycle.

        Startup:
            - Initialize the ClinicalQueryService (and its orchestrator).
            - Register the service singleton for dependency injection.

        Shutdown:
            - Close HTTP clients and release resources.
        """
        logger.info(
            "CDSS application starting",
            extra={
                "debug": settings.debug,
                "log_level": settings.log_level,
            },
        )

        # ── Startup ──────────────────────────────────────────────────
        query_service = ClinicalQueryService(settings=settings)
        set_query_service(query_service)

        logger.info("CDSS application ready to accept requests")

        yield

        # ── Shutdown ─────────────────────────────────────────────────
        logger.info("CDSS application shutting down")

        # Close OpenAI client if it has an async close method
        orchestrator = query_service.orchestrator
        if hasattr(orchestrator, "openai_client"):
            client = orchestrator.openai_client
            if hasattr(client, "_client") and hasattr(client._client, "close"):
                try:
                    await client._client.close()
                    logger.debug("OpenAI client closed")
                except Exception as exc:
                    logger.warning(
                        "Error closing OpenAI client",
                        extra={"error": str(exc)},
                    )

        logger.info("CDSS application shutdown complete")

    application = FastAPI(
        title="CDSS - Clinical Decision Support System",
        description=(
            "Intelligent Clinical Decision Support with Agentic RAG on Azure. "
            "Provides evidence-based clinical recommendations through multi-agent "
            "orchestration combining patient history, medical literature, clinical "
            "protocols, and drug safety analysis."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ────────────────────────────────────────────────────
    register_middleware(application, settings)

    # ── Routes ───────────────────────────────────────────────────────
    application.include_router(router)

    # ── Exception Handlers ───────────────────────────────────────────
    _register_exception_handlers(application)

    logger.info("FastAPI application created and configured")
    return application


def _register_exception_handlers(application: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app.

    These handlers supplement the ErrorHandlingMiddleware by catching
    exceptions that might slip through (e.g. in WebSocket handlers or
    middleware itself).

    Args:
        application: The FastAPI application instance.
    """

    @application.exception_handler(CDSSError)
    async def cdss_error_handler(request: Request, exc: CDSSError) -> JSONResponse:
        """Handle all CDSS domain exceptions.

        Maps exception types to appropriate HTTP status codes and returns
        a structured JSON error body.

        Args:
            request: The HTTP request that triggered the error.
            exc: The CDSS domain exception.

        Returns:
            A ``JSONResponse`` with the error details.
        """
        from cdss.core.exceptions import (
            AgentTimeoutError as _AgentTimeoutError,
            AuthenticationError as _AuthenticationError,
            RateLimitError as _RateLimitError,
            ValidationError as _ValidationError,
        )

        status_map: dict[type, int] = {
            _ValidationError: 422,
            _AuthenticationError: 401,
            _RateLimitError: 429,
            _AgentTimeoutError: 504,
        }

        # Walk the MRO for the most specific match
        status_code = 500
        for exc_type in type(exc).__mro__:
            if exc_type in status_map:
                status_code = status_map[exc_type]
                break

        logger.error(
            "CDSS error handled by exception handler",
            extra={
                "exception_class": type(exc).__name__,
                "message": exc.message,
                "status_code": status_code,
                "path": request.url.path,
            },
        )

        body = {
            "error": {
                "type": type(exc).__name__,
                "message": exc.message,
            }
        }
        if exc.details:
            body["error"]["details"] = exc.details

        return JSONResponse(status_code=status_code, content=body)

    @application.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unexpected exceptions.

        Logs the full traceback and returns a generic 500 error.

        Args:
            request: The HTTP request that triggered the error.
            exc: The unhandled exception.

        Returns:
            A ``JSONResponse`` with a generic error message.
        """
        logger.error(
            "Unhandled exception",
            extra={
                "exception_class": type(exc).__name__,
                "message": str(exc),
                "path": request.url.path,
            },
            exc_info=True,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "InternalServerError",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
        )


# Create the default application instance for ASGI servers
# (e.g., ``uvicorn cdss.api.app:app``)
app = create_app()
