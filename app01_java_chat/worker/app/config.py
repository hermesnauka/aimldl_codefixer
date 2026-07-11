"""Environment-driven configuration for the OpenCode Worker.

Every value here is read once at import time from the process environment. See
../README.md and ../../.env.example for the authoritative list of variables and
their defaults across the whole app01_java_chat stack.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Settings:
    """Loaded once at module import; re-instantiate (or reload the module) in
    tests if you need to exercise different env values."""

    def __init__(self) -> None:
        # Port this FastAPI app itself listens on (matches docker-compose.yml's
        # "8100:8100" mapping — see ../Dockerfile).
        self.worker_port: int = _int_env("WORKER_PORT", 8100)

        # Hard wall-clock timeout applied to every sandboxed container run.
        # CONTRACT.md §4 says "default 10s" — this is that default.
        self.execution_timeout_seconds: float = _float_env(
            "WORKER_EXECUTION_TIMEOUT_SECONDS", 10.0
        )

        # Docker daemon the `docker` SDK client connects to. In docker-compose.yml
        # this is the host's socket, bind-mounted into this service's own
        # container (see README.md's security-caveat section for exactly what
        # that means and why it's a real, known risk of this pattern).
        self.docker_host: str | None = os.environ.get("DOCKER_HOST") or None

        # Per-container resource caps. Not in CONTRACT.md (which only mandates
        # "network-disabled ... hard wall-clock timeout"), but NFR "Security" in
        # documentation_codefixer_ai_en.md demands "total isolation" and these are
        # the minimum resource-exhaustion guardrails any real sandbox needs.
        self.container_memory_limit: str = os.environ.get(
            "WORKER_CONTAINER_MEMORY_LIMIT", "256m"
        )
        self.container_nano_cpus: int = _int_env(
            "WORKER_CONTAINER_NANO_CPUS", 1_000_000_000  # 1.0 CPU
        )
        self.container_pids_limit: int = _int_env("WORKER_CONTAINER_PIDS_LIMIT", 64)
        # Size of the writable /tmp tmpfs mounted into an otherwise read-only
        # container filesystem (holds the source file + compiled artifacts).
        self.container_tmpfs_size: str = os.environ.get(
            "WORKER_CONTAINER_TMPFS_SIZE", "64m"
        )


settings = Settings()
