"""Postgres access layer (async, psycopg3) for the Orchestrator's own
telemetry tables: llm_call_logs, code_execution_logs, failover_incidents.

Schema is owned by ../db/migrations/001_init.sql — this module is a client
only, it never creates or alters tables.

Every write here is best-effort: session_id is a NOT NULL FK to sessions(id),
and sessions are created by the Gateway, not by us. If a sessionId arrives
that doesn't exist yet as a row in `sessions` (e.g. Gateway sends a fresh UUID
it hasn't persisted before calling us, or this is a standalone test run), the
INSERT would violate the FK constraint. Per the task spec, telemetry is
best-effort, not a spec requirement — a missing FK row must never crash or
abort the main /internal/v1/analyze stream. Every helper below wraps its
INSERT in its own try/except that logs a warning and swallows the error.
"""
from __future__ import annotations

import logging
from typing import Optional

from psycopg_pool import AsyncConnectionPool

from app.config import DATABASE_URL

logger = logging.getLogger("orchestrator.db")

# Lazily-created global pool. `open=False` so pytest / import-time doesn't
# attempt a real network connection; call get_pool()/open_pool() explicitly
# from the FastAPI startup hook.
_pool: Optional[AsyncConnectionPool] = None


def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(conninfo=DATABASE_URL, open=False, min_size=1, max_size=5)
    return _pool


async def open_pool() -> None:
    pool = get_pool()
    if pool.closed:
        await pool.open()


async def close_pool() -> None:
    global _pool
    if _pool is not None and not _pool.closed:
        await _pool.close()


async def log_llm_call(
    *,
    session_id: str,
    provider: str,
    model: str,
    latency_ms: int,
    success: bool,
    error: Optional[str] = None,
) -> None:
    """Insert one row into llm_call_logs. Best-effort — see module docstring."""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO llm_call_logs
                        (session_id, provider, model, latency_ms, success, error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, provider, model, latency_ms, success, error),
                )
    except Exception:  # noqa: BLE001 - telemetry must never crash the caller
        logger.warning(
            "log_llm_call failed (session_id=%s, provider=%s) — continuing without telemetry",
            session_id,
            provider,
            exc_info=True,
        )


async def log_code_execution(
    *,
    session_id: str,
    language: str,
    exit_code: Optional[int],
    stdout: str,
    stderr: str,
    timed_out: bool,
    duration_ms: int,
) -> None:
    """Insert one row into code_execution_logs. Best-effort — see module docstring."""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO code_execution_logs
                        (session_id, language, exit_code, stdout, stderr, timed_out, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, language, exit_code, stdout, stderr, timed_out, duration_ms),
                )
    except Exception:  # noqa: BLE001 - telemetry must never crash the caller
        logger.warning(
            "log_code_execution failed (session_id=%s, language=%s) — continuing without telemetry",
            session_id,
            language,
            exc_info=True,
        )


async def log_failover_incident(
    *,
    session_id: str,
    from_provider: str,
    to_provider: str,
    reason: str,
) -> None:
    """Insert one row into failover_incidents. Best-effort — see module docstring."""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO failover_incidents
                        (session_id, from_provider, to_provider, reason)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, from_provider, to_provider, reason),
                )
    except Exception:  # noqa: BLE001 - telemetry must never crash the caller
        logger.warning(
            "log_failover_incident failed (session_id=%s, %s->%s) — continuing without telemetry",
            session_id,
            from_provider,
            to_provider,
            exc_info=True,
        )
