"""HTTP client for the Integration Bridge (Java AST parsing) — CONTRACT.md §5.

POST {INTEGRATION_BRIDGE_URL}/api/v1/ast/parse
Request:  {"language": "java", "code": str}
Response: {"valid": bool, "issues": [{"line": int, "severity": "error"|"warning", "message": str}],
           "classNames": [str], "methodSignatures": [str]}

Only ever invoked by graph.py when language == "java" — every other language
skips this service entirely (CONTRACT.md §5).
"""
from __future__ import annotations

import logging
from typing import TypedDict

import httpx

from app import config

logger = logging.getLogger("orchestrator.bridge_client")


class AstIssue(TypedDict):
    line: int
    severity: str
    message: str


class AstParseResult(TypedDict):
    valid: bool
    issues: list[AstIssue]
    classNames: list[str]
    methodSignatures: list[str]


class BridgeCallError(RuntimeError):
    """Raised when the Integration Bridge is unreachable or errors."""


async def parse_java_ast(*, code: str) -> AstParseResult:
    payload = {"language": "java", "code": code}
    async with httpx.AsyncClient(timeout=config.BRIDGE_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                f"{config.INTEGRATION_BRIDGE_URL}/api/v1/ast/parse", json=payload
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error("Integration Bridge call failed: %s", exc)
            raise BridgeCallError(f"Integration Bridge call failed: {exc}") from exc
