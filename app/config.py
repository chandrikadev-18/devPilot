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
