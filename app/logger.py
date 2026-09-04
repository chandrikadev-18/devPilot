"""
DevPilot Structured Logging & Secret Redaction Module (v2.6).

Provides structured JSON and key-value logging with automatic secret redaction
(API keys, tokens, passwords) and execution metadata tracking.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Optional

from app.config import get_log_level

# Patterns for sensitive data that must never appear in logs
SENSITIVE_PATTERNS = [
    re.compile(r"(gsk_[a-zA-Z0-9_-]{20,})", re.IGNORECASE),
    re.compile(r"(Bearer\s+[a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret|password|token|auth)\s*[:=]\s*['\"]?)([^'\"\s,;]+)(['\"]?)", re.IGNORECASE),
    re.compile(r"((?:GROQ|OPENAI|ANTHROPIC|LLM)_API_KEY\s*=\s*)([^\s]+)", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """
    Redacts sensitive credentials, API keys, passwords, and tokens from log messages.
    """
    if not isinstance(text, str):
        return str(text)

    sanitized = text
    # 1. API Keys & Bearer tokens
    sanitized = re.sub(r"gsk_[a-zA-Z0-9_\-]{20,}", "[REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    # 2. Key-value pairs like api_key=..., password=...
    sanitized = re.sub(r"((?:api[_-]?key|secret|password|token|auth)\s*[:=]\s*['\"]?)([^'\"\s,;]+)(['\"]?)", r"\1[REDACTED]\3", sanitized, flags=re.IGNORECASE)
    # 3. Env var style keys
    sanitized = re.sub(r"((?:GROQ|OPENAI|ANTHROPIC|LLM)_API_KEY\s*=\s*)([^\s]+)", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized


def sanitize_payload(obj: Any) -> Any:
    """Recursively redacts sensitive fields in dictionaries or lists."""
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("password", "secret", "token", "api_key", "auth", "key")):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = sanitize_payload(v)
        return clean
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    elif isinstance(obj, str):
        return redact_secrets(obj)
    return obj


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as structured JSON entries with automatic secret redaction.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        message = redact_secrets(record.getMessage())

        log_data: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "module": record.name,
            "message": message,
        }

        # Include correlation ID
        req_id = getattr(record, "request_id", None)
        if not req_id:
            try:
                from app.observability.correlation import get_request_id
                req_id = get_request_id()
            except Exception:
                req_id = None
        if req_id:
            log_data["request_id"] = req_id

        # Include structured extra fields if present
        for attr in ("operation", "project_id", "operation_id", "task_id", "proposal_id", "review_id", "duration_ms", "status", "error", "path", "method", "status_code"):
            if hasattr(record, attr):
                val = getattr(record, attr)
                log_data[attr] = sanitize_payload(val) if val is not None else None

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_logger(name: str = "devpilot") -> logging.Logger:
    """
    Returns a configured structured logger instance.
    """
    logger = logging.getLogger(name)
    level_name = get_log_level()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    # Configure handler if not already present
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger


# Primary application logger
logger = get_logger("devpilot")


def log_operation_start(operation: str, project_id: Optional[str] = None, operation_id: Optional[str] = None, **kwargs: Any) -> None:
    """Logs the initiation of a backend operation."""
    extra = {
        "operation": operation,
        "project_id": project_id,
        "operation_id": operation_id,
        "status": "STARTED",
        **kwargs,
    }
    logger.info(f"Starting operation '{operation}'", extra=extra)


def log_operation_complete(
    operation: str,
    duration_ms: float,
    project_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Logs the successful completion of a backend operation."""
    extra = {
        "operation": operation,
        "project_id": project_id,
        "operation_id": operation_id,
        "duration_ms": round(duration_ms, 2),
        "status": "COMPLETED",
        **kwargs,
    }
    logger.info(f"Completed operation '{operation}' in {duration_ms:.2f}ms", extra=extra)


def log_operation_error(
    operation: str,
    error: Exception,
    duration_ms: Optional[float] = None,
    project_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Logs a failed backend operation with exception context."""
    extra = {
        "operation": operation,
        "project_id": project_id,
        "operation_id": operation_id,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "status": "FAILED",
        "error": redact_secrets(str(error)),
        **kwargs,
    }
    logger.error(f"Failed operation '{operation}': {redact_secrets(str(error))}", extra=extra, exc_info=True)
