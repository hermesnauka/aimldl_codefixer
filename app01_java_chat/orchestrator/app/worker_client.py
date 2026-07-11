"""HTTP client for the Worker (OpenCode sandbox) — CONTRACT.md §4.

POST {WORKER_URL}/execute
Request:  {"language": "python"|"java"|"javascript", "code": str, "testCommand": str|None}
Response: {"exitCode": int, "stdout": str, "stderr": str, "timedOut": bool, "durationMs": int}
"""
from __future__ import annotations

import logging
import time
from typing import Optional, TypedDict

import httpx

from app import config, db

logger = logging.getLogger("orchestrator.worker_client")


class ExecutionResult(TypedDict):
    exitCode: Optional[int]
    stdout: str
    stderr: str
    timedOut: bool
    durationMs: int


class WorkerCallError(RuntimeError):
    """Raised when the Worker is unreachable or returns a non-200 response."""


async def execute(
    *,
    session_id: str,
    language: str,
    code: str,
    test_command: str | None = None,
) -> ExecutionResult:
    """Call the Worker's /execute endpoint and log one code_execution_logs
    row (best-effort, via app.db.log_code_execution).
    """
    payload = {"language": language, "code": code, "testCommand": test_command}
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=config.WORKER_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(f"{config.WORKER_URL}/execute", json=payload)
            response.raise_for_status()
            result: ExecutionResult = response.json()
        except httpx.HTTPError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("Worker call failed for session %s: %s", session_id, exc)
            await db.log_code_execution(
                session_id=session_id,
                language=language,
                exit_code=None,
                stdout="",
                stderr=str(exc),
                timed_out=isinstance(exc, httpx.TimeoutException),
                duration_ms=duration_ms,
            )
            raise WorkerCallError(f"Worker call failed: {exc}") from exc

    await db.log_code_execution(
        session_id=session_id,
        language=language,
        exit_code=result.get("exitCode"),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        timed_out=result.get("timedOut", False),
        duration_ms=result.get("durationMs", int((time.monotonic() - start) * 1000)),
    )
    return result
