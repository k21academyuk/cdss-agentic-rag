"""Structured JSON logging for the Clinical Decision Support System.

Provides a centralized logging setup with JSON-formatted output,
trace ID propagation across async calls via contextvars, and
convenience functions for obtaining named loggers.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Context variable for propagating trace IDs across async boundaries.
# Set this at the start of each request/agent invocation to correlate logs.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Each log line includes:
    - timestamp: ISO 8601 UTC timestamp
    - level: log level name
    - module: Python module that emitted the log
    - function: function name that emitted the log
    - line: line number in the source file
    - trace_id: request/session trace ID (from ContextVar)
    - message: the formatted log message
    - extra: any additional key-value pairs passed via the `extra` dict
    """

    RESERVED_ATTRS: set[str] = {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "trace_id": trace_id_var.get(""),
            "message": record.getMessage(),
        }

        # Collect extra fields that are not part of the standard LogRecord
        extra: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                extra[key] = value
        if extra:
            log_entry["extra"] = extra

        # Include exception info if present
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = record.stack_info

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Human-readable formatter for development/debug mode.

    Format: [TIMESTAMP] LEVEL [trace_id] module.function:line - message
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a human-readable string."""
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]
        trace_id = trace_id_var.get("")
        trace_part = f" [{trace_id}]" if trace_id else ""
        base = (
            f"[{timestamp}] {record.levelname:<8}{trace_part} "
            f"{record.module}.{record.funcName}:{record.lineno} - {record.getMessage()}"
        )
        if record.exc_info and record.exc_info[1] is not None:
            base += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            base += "\n" + record.stack_info
        return base
        
class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Adapter that converts keyword arguments to extra dict for structured logging."""
    
    def process(self, msg, kwargs):
        # Extract any non-standard kwargs and move them to 'extra'
        extra = kwargs.get('extra', {})
        standard_keys = {'exc_info', 'stack_info', 'stacklevel', 'extra'}
        
        for key in list(kwargs.keys()):
            if key not in standard_keys:
                extra[key] = kwargs.pop(key)
        if extra:
            kwargs['extra'] = extra
        return msg, kwargs


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure the root logger with structured output.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, emit JSON-formatted logs. If False, use a
            human-readable format suitable for local development.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create handler writing to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(PlainFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy_logger in ("azure", "httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLoggerAdapter:
    """Return a named logger for the given module or component.

    Usage::

        from cdss.core.logging import get_logger

        logger = get_logger(__name__)
        # Both syntaxes are supported:
        logger.info("Processing clinical query", extra={"patient_id": "P-12345"})
        logger.info("Processing clinical query", patient_id="P-12345")

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`StructuredLoggerAdapter` instance that accepts
        keyword arguments and converts them to structured extra fields.
    """
    logger = logging.getLogger(name)
    return StructuredLoggerAdapter(logger, {})
