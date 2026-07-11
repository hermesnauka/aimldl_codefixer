"""OpenCode Worker — FastAPI entrypoint.

Exposes exactly the two routes CONTRACT.md §4 defines for this service:
`POST /execute` and `GET /health`. Only ever called by the Orchestrator
(unauthenticated, internal-network-only per CONTRACT.md §6 — Phase 1 has no
service-to-service auth token yet).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.sandbox import ExecutionResult, UnsupportedLanguageError, run_in_sandbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opencode-worker")

app = FastAPI(
    title="OpenCode Worker",
    description=(
        "CodeFixer AI's sandboxed code-execution service. Runs each "
        "/execute request in a fresh, network-disabled, ephemeral Docker "
        "container — see README.md for the full isolation model and its "
        "honest limits."
    ),
    version="1.0.0",
)


class ExecuteRequest(BaseModel):
    """CONTRACT.md §4 request shape: {language, code, testCommand}."""

    language: str = Field(..., description='One of "python", "java", "javascript".')
    code: str = Field(..., description="The source snippet to execute.")
    testCommand: str | None = Field(
        default=None,
        description=(
            "Optional shell command to run instead of the default "
            "interpreter/compiler invocation (e.g. a pytest/junit/jest "
            "command). Runs inside the same isolated container."
        ),
    )


class ExecuteResponse(BaseModel):
    """CONTRACT.md §4 response shape."""

    exitCode: int
    stdout: str
    stderr: str
    timedOut: bool
    durationMs: int

    @classmethod
    def from_result(cls, result: ExecutionResult) -> "ExecuteResponse":
        return cls(
            exitCode=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timedOut=result.timed_out,
            durationMs=result.duration_ms,
        )


@app.get("/health")
def health() -> dict:
    """CONTRACT.md §1's /health shape, reused verbatim here for consistency
    with every other service in this stack."""
    return {"status": "UP"}


@app.post("/execute", response_model=ExecuteResponse)
def execute(request: ExecuteRequest) -> ExecuteResponse | JSONResponse:
    logger.info(
        "execute request received: language=%s code_len=%d has_test_command=%s",
        request.language,
        len(request.code),
        request.testCommand is not None,
    )

    try:
        result = run_in_sandbox(
            language=request.language,
            code=request.code,
            test_command=request.testCommand,
            timeout_seconds=settings.execution_timeout_seconds,
        )
    except UnsupportedLanguageError as exc:
        # Not in CONTRACT.md as an explicit error shape (the contract only
        # documents the 200 body), so we return 422 with FastAPI's standard
        # validation-error envelope — the Orchestrator only ever sends one of
        # the three contractual languages, so this path is a defensive
        # guard against a contract violation upstream, not an expected case.
        logger.warning("rejected unsupported language: %s", request.language)
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    logger.info(
        "execute request finished: exitCode=%d timedOut=%s durationMs=%d",
        result.exit_code,
        result.timed_out,
        result.duration_ms,
    )
    return ExecuteResponse.from_result(result)
