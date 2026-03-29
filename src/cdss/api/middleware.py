"""FastAPI middleware for the Clinical Decision Support System.

Provides cross-cutting concerns:
    - CORS configuration for allowed origins
    - Request ID injection for distributed tracing
    - Structured request/response logging
    - Global exception handling converting domain errors to HTTP responses
    - Simple in-memory rate limiting
"""

from __future__ import annotations

import time
from collections import defaultdict
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jwt import PyJWKClient  # type: ignore[import-untyped]
from jwt import decode as jwt_decode  # type: ignore[import-untyped]
from jwt.exceptions import InvalidTokenError, PyJWKClientError  # type: ignore[import-untyped]
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import (
    AgentError,
    AgentTimeoutError,
    AuthenticationError,
    AzureServiceError,
    CDSSError,
    DocumentProcessingError,
    DrugSafetyError,
    GuardrailsViolation,
    RateLimitError as CDSSRateLimitError,
    RetrieverError,
    ValidationError,
)
from cdss.core.logging import get_logger, trace_id_var

logger = get_logger(__name__)


# ==========================================================================
# CORS Middleware Configuration
# ==========================================================================


def add_cors_middleware(app: FastAPI, settings: Settings | None = None) -> None:
    """Add CORS middleware to the FastAPI application.

    Configures Cross-Origin Resource Sharing based on the allowed origins
    list in the application settings.

    Args:
        app: The FastAPI application instance.
        settings: Optional settings override.
    """
    settings = settings or get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        expose_headers=settings.cors_expose_headers,
    )

    logger.info(
        "CORS middleware configured",
        extra={"allowed_origins": settings.cors_origins},
    )


# ==========================================================================
# Entra ID JWT Authentication Middleware
# ==========================================================================


class EntraJWTAuthMiddleware(BaseHTTPMiddleware):
    """Validate Azure Entra ID bearer tokens for protected API routes."""

    _PUBLIC_PATHS: set[str] = {
        "/api/v1/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(self, app: FastAPI, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or get_settings()
        self._enabled = self._settings.auth_enabled
        self._tenant_id = self._settings.auth_tenant_id.strip()
        self._audience = self._settings.auth_audience.strip()
        self._required_scopes = set(self._settings.auth_required_scopes)

        self._issuer = (
            f"https://login.microsoftonline.com/{self._tenant_id}/v2.0"
            if self._tenant_id
            else ""
        )
        self._jwks_client = (
            PyJWKClient(
                f"https://login.microsoftonline.com/{self._tenant_id}/discovery/v2.0/keys"
            )
            if self._tenant_id
            else None
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self._enabled:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/") or path in self._PUBLIC_PATHS:
            return await call_next(request)

        if not self._tenant_id or not self._audience or self._jwks_client is None:
            logger.error(
                "Authentication is enabled but Entra JWT settings are incomplete",
                extra={
                    "tenant_id_set": bool(self._tenant_id),
                    "audience_set": bool(self._audience),
                },
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "type": "auth_configuration_error",
                        "message": (
                            "Authentication is enabled but auth configuration is incomplete. "
                            "Set CDSS_AUTH_TENANT_ID and CDSS_AUTH_AUDIENCE."
                        ),
                    }
                },
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "error": {
                        "type": "authentication_error",
                        "message": "Missing bearer token.",
                    }
                },
            )

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "error": {
                        "type": "authentication_error",
                        "message": "Empty bearer token.",
                    }
                },
            )

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt_decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_exp": True},
            )

            if self._required_scopes:
                token_scopes = set(str(claims.get("scp", "")).split())
                if not self._required_scopes.issubset(token_scopes):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "type": "authorization_error",
                                "message": "Token does not include required scopes.",
                                "details": {
                                    "required_scopes": sorted(self._required_scopes),
                                    "token_scopes": sorted(token_scopes),
                                },
                            }
                        },
                    )

            request.state.auth_claims = claims
            request.state.auth_subject = claims.get("oid") or claims.get("sub")

        except (PyJWKClientError, InvalidTokenError) as exc:
            # Decode token header without verification to extract diagnostic info
            token_audience_hint = "unknown"
            token_issuer_hint = "unknown"
            try:
                import base64
                parts = token.split(".")
                if len(parts) >= 2:
                    # Decode payload (second part) without verification
                    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                    payload_json = base64.urlsafe_b64decode(payload_b64)
                    import json
                    payload = json.loads(payload_json)
                    token_audience_hint = str(payload.get("aud", "missing"))
                    token_issuer_hint = str(payload.get("iss", "missing"))
            except Exception:
                pass

            logger.warning(
                "JWT validation failed",
                extra={
                    "path": path,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "expected_audience": self._audience,
                    "expected_issuer": self._issuer,
                    "token_audience_hint": token_audience_hint,
                    "token_issuer_hint": token_issuer_hint,
                },
            )
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "error": {
                        "type": "authentication_error",
                        "message": "Invalid or expired bearer token.",
                        "hint": (
                            f"Audience mismatch: token has '{token_audience_hint}', "
                            f"backend expects '{self._audience}'. "
                            "Check CDSS_AUTH_AUDIENCE environment variable."
                        ) if "audience" in str(exc).lower() or token_audience_hint != self._audience else None,
                    }
                },
            )

        return await call_next(request)


# ==========================================================================
# Request ID Middleware
# ==========================================================================


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injects a unique request/trace ID into every request.

    The trace ID is:
        - Generated as a UUID4 if not provided in the ``X-Request-ID`` header.
        - Set in the ``trace_id_var`` context variable for log correlation.
        - Returned in the ``X-Request-ID`` response header.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, injecting a trace ID.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response with the trace ID header set.
        """
        trace_id = request.headers.get("X-Request-ID", str(uuid4()))
        trace_id_var.set(trace_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        response.headers["X-Trace-ID"] = trace_id

        return response


# ==========================================================================
# Logging Middleware
# ==========================================================================


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs structured information about every HTTP request and response.

    Captures method, path, status code, and latency for observability.
    Skips verbose logging for health-check endpoints to reduce noise.
    """

    # Paths to suppress from INFO-level logging to reduce noise.
    _QUIET_PATHS: set[str] = {"/api/v1/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Log the request and response.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response.
        """
        start_time = time.monotonic()
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # Log the incoming request
        if path not in self._QUIET_PATHS:
            logger.info(
                "Request received",
                extra={
                    "method": method,
                    "path": path,
                    "client": client_host,
                    "query_params": str(request.query_params),
                },
            )

        response = await call_next(request)

        latency_ms = int((time.monotonic() - start_time) * 1000)

        log_extra = {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "client": client_host,
        }

        if path in self._QUIET_PATHS:
            logger.debug("Request completed", extra=log_extra)
        elif response.status_code >= 500:
            logger.error("Request failed", extra=log_extra)
        elif response.status_code >= 400:
            logger.warning("Client error", extra=log_extra)
        else:
            logger.info("Request completed", extra=log_extra)

        return response


# ==========================================================================
# Error Handling Middleware
# ==========================================================================


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and converts them to structured HTTP responses.

    Maps CDSS domain exceptions to appropriate HTTP status codes with
    JSON error bodies.
    """

    # Maps exception types to (HTTP status code, user-facing error type string).
    _EXCEPTION_MAP: dict[type, tuple[int, str]] = {
        ValidationError: (422, "validation_error"),
        AuthenticationError: (401, "authentication_error"),
        CDSSRateLimitError: (429, "rate_limit_error"),
        AgentTimeoutError: (504, "agent_timeout"),
        AgentError: (502, "agent_error"),
        RetrieverError: (502, "retriever_error"),
        DrugSafetyError: (502, "drug_safety_error"),
        DocumentProcessingError: (502, "document_processing_error"),
        GuardrailsViolation: (422, "guardrails_violation"),
        AzureServiceError: (502, "azure_service_error"),
        CDSSError: (500, "internal_error"),
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, catching and converting domain exceptions.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response, or a JSON error response if an exception occurred.
        """
        try:
            return await call_next(request)

        except Exception as exc:
            return self._build_error_response(exc, request)

    def _build_error_response(self, exc: Exception, request: Request) -> JSONResponse:
        """Convert an exception into a structured JSON error response.

        Args:
            exc: The caught exception.
            request: The original HTTP request (for context in logs).

        Returns:
            A ``JSONResponse`` with the appropriate status code and error body.
        """
        trace_id = trace_id_var.get("")

        # Walk the MRO to find the most specific matching exception type
        for exc_type in type(exc).__mro__:
            if exc_type in self._EXCEPTION_MAP:
                status_code, error_type = self._EXCEPTION_MAP[exc_type]
                break
        else:
            status_code = 500
            error_type = "internal_error"

        # Extract message from CDSS exceptions or use generic message
        if isinstance(exc, CDSSError):
            message = exc.message
            details = exc.details
        else:
            message = "An unexpected internal error occurred."
            details = {}

        logger.error(
            "Unhandled exception converted to HTTP error",
            extra={
                "error_type": error_type,
                "status_code": status_code,
                "exception_class": type(exc).__name__,
                "message": str(exc),
                "path": request.url.path,
                "trace_id": trace_id,
            },
            exc_info=True,
        )

        body = {
            "error": {
                "type": error_type,
                "message": message,
                "trace_id": trace_id,
            }
        }

        if details:
            body["error"]["details"] = details

        # Add Retry-After header for rate limit errors
        headers: dict[str, str] = {}
        if isinstance(exc, CDSSRateLimitError) and exc.retry_after is not None:
            headers["Retry-After"] = str(int(exc.retry_after))

        return JSONResponse(
            status_code=status_code,
            content=body,
            headers=headers,
        )


# ==========================================================================
# Rate Limiting Middleware
# ==========================================================================


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter using a sliding window approach.

    Limits requests per client IP address.  This is suitable for
    development and single-instance deployments.  For production with
    multiple instances, replace with a Redis-backed solution.

    Attributes:
        max_requests: Maximum requests allowed per window.
        window_seconds: Duration of the sliding window in seconds.
    """

    def __init__(
        self,
        app: FastAPI,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            app: The FastAPI application.
            max_requests: Max requests per IP per window.
            window_seconds: Sliding window duration in seconds.
        """
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._request_log: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check the rate limit before processing the request.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response, or a 429 response if the rate limit is exceeded.
        """
        # Skip rate limiting for health checks
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Clean up expired entries and count recent requests
        timestamps = self._request_log[client_ip]
        # Remove timestamps outside the window
        self._request_log[client_ip] = [
            ts for ts in timestamps if ts > window_start
        ]
        current_count = len(self._request_log[client_ip])

        if current_count >= self.max_requests:
            retry_after = self.window_seconds
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client": client_ip,
                    "current_count": current_count,
                    "max_requests": self.max_requests,
                    "window_seconds": self.window_seconds,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "type": "rate_limit_error",
                        "message": (
                            f"Rate limit exceeded. Maximum {self.max_requests} "
                            f"requests per {self.window_seconds} seconds."
                        ),
                        "retry_after": retry_after,
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Record this request
        self._request_log[client_ip].append(now)

        # Periodic cleanup of stale IPs to prevent memory growth
        if len(self._request_log) > 10000:
            stale_ips = [
                ip
                for ip, times in self._request_log.items()
                if not times or times[-1] < window_start
            ]
            for ip in stale_ips:
                del self._request_log[ip]

        return await call_next(request)


# ==========================================================================
# Middleware Registration Helper
# ==========================================================================


def register_middleware(app: FastAPI, settings: Settings | None = None) -> None:
    """Register all middleware on the FastAPI application in the correct order.

    Middleware is applied in reverse order of registration (outermost first),
    so the order here matters:
        1. CORS (outermost -- must run first for preflight requests)
        2. Request ID (sets trace context before anything else)
        3. Entra JWT Auth (validates bearer token when enabled)
        4. Logging (wraps everything for observability)
        5. Error Handling (catches exceptions from inner layers)
        6. Rate Limiting (innermost before route handlers)

    Args:
        app: The FastAPI application instance.
        settings: Optional settings override.
    """
    settings = settings or get_settings()

    # Register in reverse desired execution order
    # (last registered = outermost = runs first)
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(EntraJWTAuthMiddleware, settings=settings)
    app.add_middleware(RequestIDMiddleware)

    # CORS must be outermost, added last
    add_cors_middleware(app, settings)

    logger.info("All middleware registered")
