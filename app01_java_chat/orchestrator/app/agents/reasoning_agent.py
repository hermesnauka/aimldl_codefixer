"""Reasoning Agent (§2.2 Agent Topology): Hermes 3 via OpenRouter, LangChain
failover to OpenAI Codex, emits reasoning tokens incrementally (US-02).

This module holds the real logic — prompt construction from graph state,
streaming loop against app.llm.failover.FailoverSession, and parsing the
final fix out of the model's output. app/graph.py only wires this into a
LangGraph node; it contains no reasoning logic itself.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.llm.failover import FailoverSession, ProviderAttemptFailed

logger = logging.getLogger("orchestrator.agents.reasoning")

_SYSTEM_PROMPT = (
    "You are CodeFixer AI, an expert software engineer assistant. You are given a "
    "code snippet, optionally an error log / stack trace, and the detected "
    "programming language. Think step by step about the root cause (this is your "
    "Chain-of-Thought reasoning, which the user can see live), then produce a "
    "corrected version of the code.\n\n"
    "Once you have finished reasoning, output a final section delimited exactly as:\n"
    "===FINAL_FIX===\n"
    "<the complete corrected code>\n"
    "===EXPLANATION===\n"
    "<a concise explanation of what was wrong and what you changed>\n"
    "===END===\n"
    "Everything before ===FINAL_FIX=== is treated as visible reasoning tokens."
)

_FIX_BLOCK_RE = re.compile(
    r"===FINAL_FIX===\s*(?P<code>.*?)\s*===EXPLANATION===\s*(?P<explanation>.*?)\s*===END===",
    re.DOTALL,
)


@dataclass
class ReasoningOutcome:
    reasoning_trace: str
    fix_code: str | None
    fix_explanation: str | None


def build_user_prompt(
    *,
    code: str,
    language: str,
    error_log: str | None,
    retry_count: int,
    prior_failures: list[str],
) -> str:
    """Build the user-turn prompt from current graph state, including any
    prior execution/bridge failures accumulated across self-correction loop
    iterations (§2.2: "feeds back into the Reasoning Agent ... if errors
    persist").
    """
    parts = [f"Language: {language}", "", "Code:", "```", code, "```"]
    if error_log:
        parts += ["", "Error log / stack trace:", "```", error_log, "```"]
    if retry_count > 0 and prior_failures:
        parts += ["", f"This is retry attempt {retry_count}. Prior attempts failed:"]
        for i, failure in enumerate(prior_failures, start=1):
            parts += [f"--- Prior failure {i} ---", failure]
        parts += ["", "Take the above failures into account and produce a fix that avoids them."]
    return "\n".join(parts)


def _parse_fix(full_text: str) -> tuple[str | None, str | None]:
    match = _FIX_BLOCK_RE.search(full_text)
    if not match:
        return None, None
    return match.group("code").strip(), match.group("explanation").strip()


async def run_reasoning(
    *,
    failover_session: FailoverSession,
    code: str,
    language: str,
    error_log: str | None,
    retry_count: int,
    prior_failures: list[str],
    on_reasoning_token=None,
    on_event=None,
) -> ReasoningOutcome:
    """Stream a completion from the Reasoning Agent (via FailoverSession),
    surfacing each incremental token through `on_reasoning_token` as it
    arrives (US-02), and returning the parsed final fix once the stream
    completes.

    `on_reasoning_token` and `on_event` are both optional async callables;
    graph.py wires them to whatever event-surfacing mechanism it uses.
    """
    user_prompt = build_user_prompt(
        code=code,
        language=language,
        error_log=error_log,
        retry_count=retry_count,
        prior_failures=prior_failures,
    )

    full_text_parts: list[str] = []
    try:
        async for token in failover_session.stream(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            on_event=on_event,
        ):
            full_text_parts.append(token)
            if on_reasoning_token is not None:
                await on_reasoning_token(token)
    except ProviderAttemptFailed as exc:
        # Attempts remain (failover threshold not yet crossed) — this
        # reasoning attempt produced nothing usable. Surface as an outcome
        # with no fix so the graph's conditional edge treats it like any
        # other failed attempt and can loop back (bounded by retry_count).
        logger.warning("Reasoning attempt failed, no fix produced: %s", exc)
        return ReasoningOutcome(reasoning_trace="", fix_code=None, fix_explanation=None)

    full_text = "".join(full_text_parts)
    fix_code, fix_explanation = _parse_fix(full_text)

    if fix_code is None:
        # Model didn't follow the delimiter format. Fall back to treating
        # the entire response as reasoning trace with no structured fix,
        # rather than crashing — finalize/graph logic handles fix_code=None.
        logger.warning(
            "Reasoning output did not contain a ===FINAL_FIX=== block; "
            "treating entire response as reasoning trace only."
        )
        return ReasoningOutcome(reasoning_trace=full_text, fix_code=None, fix_explanation=None)

    # Reasoning trace is everything before the delimiter.
    delimiter_index = full_text.find("===FINAL_FIX===")
    reasoning_trace = full_text[:delimiter_index].strip() if delimiter_index >= 0 else full_text

    return ReasoningOutcome(
        reasoning_trace=reasoning_trace, fix_code=fix_code, fix_explanation=fix_explanation
    )


def safe_json_preview(value: object, limit: int = 2000) -> str:
    """Small helper used when stuffing structured failure context (worker
    stdout/stderr, bridge issues) into `prior_failures` strings for the next
    reasoning attempt — keeps prompts bounded.
    """
    text = json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"
