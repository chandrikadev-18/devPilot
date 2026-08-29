"""
DevPilot Central Configuration Module.

Provides centralized management for LLM, RAG context limits,
and search parameters with support for environment variables and optional .env file.
"""

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Optional[Path] = None) -> None:
    """
    Loads environment variables from a .env file if it exists,
    without overwriting already set environment variables.
    """
    if env_path is None:
        env_path = Path(".env")

    if not env_path.is_file():
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        # Ignore errors during best-effort .env loading
        pass


# Auto-load .env on import if present
load_env_file()


def get_llm_provider() -> str:
    """Returns the configured LLM provider name (default: 'groq')."""
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def get_llm_model(default: str = "llama-3.3-70b-versatile") -> str:
    """Returns the configured LLM model name."""
    return os.getenv("LLM_MODEL", default).strip()


def get_llm_api_key(provider: Optional[str] = None) -> Optional[str]:
    """
    Retrieves the API key for the specified provider or general LLM key.
    Checks LLM_API_KEY, and provider-specific keys like GROQ_API_KEY.
    """
    key = os.getenv("LLM_API_KEY")
    if key and key.strip():
        return key.strip()

    prov = (provider or get_llm_provider()).lower()
    if prov == "groq":
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key and groq_key.strip():
            return groq_key.strip()

    return None


def get_max_context_chunks() -> int:
    """Returns the maximum number of code chunks to include in LLM context."""
    val = os.getenv("MAX_CONTEXT_CHUNKS", "5")
    try:
        parsed = int(val)
        return max(1, parsed)
    except ValueError:
        return 5


def get_max_context_characters() -> int:
    """Returns the maximum number of characters allowed in the assembled code context."""
    val = os.getenv("MAX_CONTEXT_CHARACTERS", "20000")
    try:
        parsed = int(val)
        return max(500, parsed)
    except ValueError:
        return 20000


def get_default_top_k() -> int:
    """Returns the default top-k search limit."""
    val = os.getenv("DEFAULT_TOP_K", "5")
    try:
        parsed = int(val)
        return max(1, parsed)
    except ValueError:
        return 5


def get_default_min_score() -> Optional[float]:
    """Returns the default minimum score threshold or None."""
    val = os.getenv("DEFAULT_MIN_SCORE")
    if val is not None and val.strip():
        try:
            return float(val)
        except ValueError:
            return None
    return None


def get_max_agent_iterations() -> int:
    """Returns the maximum number of reasoning/tool iterations for the agent."""
    val = os.getenv("MAX_AGENT_ITERATIONS", "5")
    try:
        parsed = int(val)
        return max(1, parsed)
    except ValueError:
        return 5


def get_max_tool_calls() -> int:
    """Returns the maximum number of total tool calls allowed per agent run (default: 4)."""
    val = os.getenv("MAX_TOOL_CALLS", "4")
    try:
        parsed = int(val)
        return max(1, parsed)
    except ValueError:
        return 4


def get_max_tool_result_characters() -> int:
    """Returns the maximum character limit for an individual tool result."""
    val = os.getenv("MAX_TOOL_RESULT_CHARACTERS", "12000")
    try:
        parsed = int(val)
        return max(500, parsed)
    except ValueError:
        return 12000


# ============================================================================
# DevPilot v2.6 Central Configuration Additions
# ============================================================================

def get_environment() -> str:
    """Returns the current deployment environment (e.g. 'development', 'production', 'test')."""
    return os.getenv("DEVPILOT_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()


def get_log_level() -> str:
    """Returns the configured log level (DEBUG, INFO, WARNING, ERROR). Default: 'INFO'."""
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return level
    return "INFO"


def get_project_storage_location() -> Optional[str]:
    """Returns custom project storage location path if configured, else None."""
    val = os.getenv("PROJECT_STORAGE_LOCATION")
    if val and val.strip():
        return val.strip()
    return None


def get_operation_timeout() -> float:
    """Returns maximum duration in seconds allowed for a project operation (default: 60.0)."""
    val = os.getenv("OPERATION_TIMEOUT", "60.0")
    try:
        parsed = float(val)
        return max(1.0, parsed)
    except ValueError:
        return 60.0


def get_test_timeout() -> float:
    """Returns maximum duration in seconds allowed for test runner execution (default: 30.0)."""
    val = os.getenv("TEST_TIMEOUT", "30.0")
    try:
        parsed = float(val)
        return max(1.0, parsed)
    except ValueError:
        return 30.0


def get_max_project_size_mb() -> float:
    """Returns maximum allowed project directory size in MB (default: 500.0)."""
    val = os.getenv("MAX_PROJECT_SIZE_MB", "500.0")
    try:
        parsed = float(val)
        return max(1.0, parsed)
    except ValueError:
        return 500.0


def get_api_host() -> str:
    """Returns the REST API host to bind to (default: '127.0.0.1')."""
    return os.getenv("DEVPILOT_API_HOST", os.getenv("API_HOST", "127.0.0.1")).strip()


def get_api_port() -> int:
    """Returns the REST API port to bind to (default: 8000)."""
    val = os.getenv("DEVPILOT_API_PORT", os.getenv("API_PORT", "8000"))
    try:
        parsed = int(val)
        return max(1, min(65535, parsed))
    except ValueError:
        return 8000


def get_config_summary() -> dict:
    """
    Returns a safe summary of current configuration parameters with
    all secrets redacted.
    """
    return {
        "environment": get_environment(),
        "log_level": get_log_level(),
        "llm_provider": get_llm_provider(),
        "llm_model": get_llm_model(),
        "llm_api_key_configured": bool(get_llm_api_key()),
        "max_context_chunks": get_max_context_chunks(),
        "max_context_characters": get_max_context_characters(),
        "default_top_k": get_default_top_k(),
        "default_min_score": get_default_min_score(),
        "max_agent_iterations": get_max_agent_iterations(),
        "max_tool_calls": get_max_tool_calls(),
        "operation_timeout_sec": get_operation_timeout(),
        "test_timeout_sec": get_test_timeout(),
        "max_project_size_mb": get_max_project_size_mb(),
        "api_host": get_api_host(),
        "api_port": get_api_port(),
        "project_storage_location": get_project_storage_location(),
    }

