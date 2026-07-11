"""Environment configuration for the Orchestrator service.

Fail-fast rule (per task spec): variables with no sensible default
(DATABASE_URL, WORKER_URL, INTEGRATION_BRIDGE_URL) raise at import time if
missing. OPENROUTER_API_KEY / OPENAI_API_KEY do NOT fail fast here — this
environment has no keys configured, and the service (and its test suite)
must still be importable and runnable without them. Those keys are only
required at the moment an actual LLM call is attempted (see
app/llm/openrouter_client.py and app/llm/openai_fallback_client.py).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Load a .env file if present (no-op if it doesn't exist). Never overrides
# variables already set in the real environment (e.g. by docker-compose).
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"See .env.example at the repo root for the expected shape."
        )
    return value


def _optional(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- Required, no sensible default -----------------------------------------
DATABASE_URL: str = _require("DATABASE_URL")
WORKER_URL: str = _require("WORKER_URL")
INTEGRATION_BRIDGE_URL: str = _require("INTEGRATION_BRIDGE_URL")

# --- LLM credentials — intentionally NOT fail-fast at import time ----------
# Read as plain optional values here. Each LLM client module raises its own
# ConfigError (see app/llm/*.py) only when a call is actually attempted
# without a key, so `import app.config` / `import app.main` always succeeds
# in an environment with no keys configured (this one).
OPENROUTER_API_KEY: str | None = os.environ.get("OPENROUTER_API_KEY") or None
OPENROUTER_MODEL: str = _optional(
    "OPENROUTER_MODEL", "nousresearch/hermes-3-llama-3.1-405b"
)

OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY") or None
OPENAI_MODEL: str = _optional("OPENAI_MODEL", "gpt-4o")

# --- US-04 failover thresholds -----------------------------------------------
LLM_FAILOVER_MAX_ATTEMPTS: int = int(_optional("LLM_FAILOVER_MAX_ATTEMPTS", "2"))
LLM_FAILOVER_TIMEOUT_SECONDS: float = float(
    _optional("LLM_FAILOVER_TIMEOUT_SECONDS", "3.0")
)

# --- Misc --------------------------------------------------------------------
ORCHESTRATOR_PORT: int = int(_optional("ORCHESTRATOR_PORT", "8000"))

# Self-correction loop retry cap (§2.2 Agent Topology: "cap retries, e.g. 3").
# Not in CONTRACT.md's env var list, so kept as an internal constant rather
# than a required/documented env var — override only if you know why.
MAX_RETRY_COUNT: int = int(_optional("ORCHESTRATOR_MAX_RETRY_COUNT", "3"))

# Worker/bridge HTTP client timeouts. Worker default execution timeout is
# 10s per WORKER_EXECUTION_TIMEOUT_SECONDS (.env.example) plus network
# overhead headroom; bridge is a fast AST parse, short timeout is fine.
WORKER_HTTP_TIMEOUT_SECONDS: float = float(
    _optional("WORKER_HTTP_TIMEOUT_SECONDS", "15.0")
)
BRIDGE_HTTP_TIMEOUT_SECONDS: float = float(
    _optional("BRIDGE_HTTP_TIMEOUT_SECONDS", "10.0")
)
