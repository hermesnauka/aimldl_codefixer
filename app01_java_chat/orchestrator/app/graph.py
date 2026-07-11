"""The Orchestrator's actual agent DAG, built with LangGraph's `StateGraph`
(§2.2 Agent Topology): router -> reasoning -> execute -> [conditional:
reasoning | finalize] -> finalize.

Event-surfacing architectural choice: nodes need to emit fine-grained SSE/
ndjson events (status, reasoning_token, provider_failover,
execution_result, final_fix, error) as they run — not just a final state
snapshot. LangGraph's `astream()` yields one item per *node completion*,
which is too coarse for token-by-token reasoning_token events. So instead:
an `asyncio.Queue[dict]` is created per `/internal/v1/analyze` call and
passed into every node via the LangGraph `RunnableConfig`'s `configurable`
dict (`config["configurable"]["event_queue"]`). Nodes push event dicts onto
that queue as they produce them (including mid-node, e.g. once per reasoning
token). `app/main.py` runs `graph.ainvoke(...)` as a background asyncio task
and concurrently drains the queue into the ndjson HTTP response as items
arrive, then appends a final `{"type": "done"}` once the task completes.
This keeps the graph itself a real, declarative StateGraph (nodes only
compute state transitions) while still supporting true incremental
streaming, which a bare `astream()` over graph steps cannot provide at
token granularity.

Implementation note (LangGraph 1.x): node functions receive the
`RunnableConfig` only if a parameter is literally named `config` (LangGraph
inspects the function signature by parameter name, not position) — so every
node below takes `(state, config)`, not `(state, config_)`. To keep that
name free, `app/config.py` (env var settings) is imported here under the
alias `app_config`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app import bridge_client, worker_client
from app import config as app_config
from app.agents import router_agent
from app.agents.reasoning_agent import run_reasoning, safe_json_preview
from app.llm.failover import FailoverSession

logger = logging.getLogger("orchestrator.graph")


class ExecutionResultState(TypedDict, total=False):
    exitCode: Optional[int]
    stdout: str
    stderr: str
    timedOut: bool
    durationMs: int


class GraphState(TypedDict, total=False):
    # Inputs (from CONTRACT.md §3 request body)
    session_id: str
    user_id: str
    language: Optional[str]
    error_log: Optional[str]
    code: str

    # Working state
    reasoning_trace: list[str]
    execution_result: Optional[ExecutionResultState]
    bridge_result: Optional[dict]
    prior_failures: list[str]
    retry_count: int
    current_provider: str

    # Outcome
    fix_code: Optional[str]
    fix_explanation: Optional[str]
    failed: bool
    error_message: Optional[str]

    # Not part of the "data" state conceptually, but threaded through
    # LangGraph state since node functions only receive (state, config):
    # the FailoverSession instance is per-analyze-call, stateful, and must
    # survive across reasoning<->execute loop iterations without being
    # rebuilt (rebuilding it would reset the consecutive-failure counter and
    # break the "no retrying OpenRouter once failed over" rule).
    failover_session: Any


async def _emit(config: RunnableConfig, event: dict) -> None:
    queue = config.get("configurable", {}).get("event_queue")
    if queue is not None:
        await queue.put(event)


def _build_bridge_failure_context(bridge_result: dict) -> str:
    error_issues = [i for i in bridge_result.get("issues", []) if i.get("severity") == "error"]
    return (
        "Integration Bridge AST parse reported issues: "
        f"{safe_json_preview({'valid': bridge_result.get('valid'), 'issues': error_issues})}"
    )


def _build_execution_failure_context(execution_result: dict) -> str:
    return (
        "Worker execution failed: "
        f"{safe_json_preview({k: execution_result.get(k) for k in ('exitCode', 'stdout', 'stderr', 'timedOut')})}"
    )


async def router_node(state: GraphState, config: RunnableConfig) -> dict:
    await _emit(config, {"type": "status", "stage": "routing"})
    language = router_agent.detect_language(
        code=state.get("code"),
        error_log=state.get("error_log"),
        language_hint=state.get("language"),
    )
    return {"language": language}


async def reasoning_node(state: GraphState, config: RunnableConfig) -> dict:
    await _emit(config, {"type": "status", "stage": "reasoning"})

    failover_session: FailoverSession = state["failover_session"]

    async def on_reasoning_token(token: str) -> None:
        await _emit(config, {"type": "reasoning_token", "token": token})

    async def on_event(event: dict) -> None:
        await _emit(config, event)

    outcome = await run_reasoning(
        failover_session=failover_session,
        code=state["code"],
        language=state.get("language") or "python",
        error_log=state.get("error_log"),
        retry_count=state.get("retry_count", 0),
        prior_failures=state.get("prior_failures", []),
        on_reasoning_token=on_reasoning_token,
        on_event=on_event,
    )

    reasoning_trace = list(state.get("reasoning_trace", []))
    if outcome.reasoning_trace:
        reasoning_trace.append(outcome.reasoning_trace)

    return {
        "reasoning_trace": reasoning_trace,
        "fix_code": outcome.fix_code,
        "fix_explanation": outcome.fix_explanation,
        "current_provider": failover_session.current_provider,
    }


async def execute_node(state: GraphState, config: RunnableConfig) -> dict:
    await _emit(config, {"type": "status", "stage": "executing"})

    language = state.get("language") or "python"
    fix_code = state.get("fix_code")
    result: dict = {"failed": True}

    if not fix_code:
        # Reasoning produced no structured fix this attempt — nothing to
        # execute. Treat as a failed attempt so the conditional edge below
        # can decide whether to retry reasoning or give up.
        result["execution_result"] = None
        result["bridge_result"] = None
        return result

    bridge_result = None
    if language == "java":
        try:
            bridge_result = await bridge_client.parse_java_ast(code=fix_code)
        except bridge_client.BridgeCallError as exc:
            logger.error("Bridge call failed: %s", exc)
            bridge_result = {"valid": False, "issues": [], "classNames": [], "methodSignatures": []}
            result["error_message"] = f"Integration Bridge unavailable: {exc}"

    try:
        execution_result = await worker_client.execute(
            session_id=state["session_id"], language=language, code=fix_code
        )
    except worker_client.WorkerCallError as exc:
        logger.error("Worker call failed: %s", exc)
        await _emit(config, {"type": "error", "message": f"Worker call failed: {exc}"})
        execution_result = {
            "exitCode": None,
            "stdout": "",
            "stderr": str(exc),
            "timedOut": False,
            "durationMs": 0,
        }

    await _emit(
        config,
        {
            "type": "execution_result",
            "language": language,
            "exitCode": execution_result.get("exitCode"),
            "stdout": execution_result.get("stdout", ""),
            "stderr": execution_result.get("stderr", ""),
            "durationMs": execution_result.get("durationMs", 0),
        },
    )

    bridge_failed = bool(bridge_result) and (
        bridge_result.get("valid") is False
        or any(i.get("severity") == "error" for i in bridge_result.get("issues", []))
    )
    execution_failed = execution_result.get("exitCode") not in (0,)

    result["execution_result"] = execution_result
    result["bridge_result"] = bridge_result
    result["failed"] = bool(execution_failed or bridge_failed)
    return result


async def finalize_node(state: GraphState, config: RunnableConfig) -> dict:
    await _emit(config, {"type": "status", "stage": "finalizing"})

    fix_code = state.get("fix_code")
    still_failed = state.get("failed", False)

    if fix_code and not still_failed:
        await _emit(
            config,
            {
                "type": "final_fix",
                "code": fix_code,
                "explanation": state.get("fix_explanation") or "",
                "language": state.get("language") or "python",
            },
        )
        return {}

    if fix_code and still_failed:
        # Retries exhausted but we still have a last-attempted fix — surface
        # it as the final answer along with an error note, rather than
        # emitting nothing. This favors giving the user *something* over a
        # bare error when a fix exists but couldn't be verified in time.
        await _emit(
            config,
            {
                "type": "final_fix",
                "code": fix_code,
                "explanation": (
                    (state.get("fix_explanation") or "")
                    + " (Note: retries exhausted; this fix could not be fully verified "
                    "by execution.)"
                ).strip(),
                "language": state.get("language") or "python",
            },
        )
        return {}

    await _emit(
        config,
        {
            "type": "error",
            "message": state.get("error_message")
            or "Unable to produce a working fix within the retry budget.",
        },
    )
    return {}


def _route_after_execute(state: GraphState) -> str:
    failed = state.get("failed", False)
    retry_count = state.get("retry_count", 0)

    if failed and retry_count < app_config.MAX_RETRY_COUNT:
        return "retry"
    return "finalize"


async def _increment_retry_and_record_failure(state: GraphState, config: RunnableConfig) -> dict:
    """Edge-adjacent state update: bump retry_count and stash a summary of
    what failed into prior_failures, so the next reasoning_node call has
    context (§2.2: "feeds back into the Reasoning Agent ... if errors
    persist"). Implemented as its own node (rather than inline in the
    conditional-edge function) since conditional-edge functions in LangGraph
    only choose the next node name — they don't mutate state themselves.
    """
    await _emit(config, {"type": "status", "stage": "self_correcting"})

    prior_failures = list(state.get("prior_failures", []))
    execution_result = state.get("execution_result")
    bridge_result = state.get("bridge_result")

    if bridge_result and (
        bridge_result.get("valid") is False
        or any(i.get("severity") == "error" for i in bridge_result.get("issues", []))
    ):
        prior_failures.append(_build_bridge_failure_context(bridge_result))
    if execution_result and execution_result.get("exitCode") not in (0,):
        prior_failures.append(_build_execution_failure_context(execution_result))
    if not execution_result and not bridge_result:
        prior_failures.append("Reasoning agent produced no parsable fix on the previous attempt.")

    return {
        "retry_count": state.get("retry_count", 0) + 1,
        "prior_failures": prior_failures,
    }


def build_graph():
    """Compile and return the LangGraph StateGraph.

    Nodes: router, reasoning, execute, self_correct, finalize
    Edges:
        START -> router -> reasoning -> execute
        execute -[conditional: _route_after_execute]-> self_correct | finalize
        self_correct -> reasoning   (loop back)
        finalize -> END
    """
    graph = StateGraph(GraphState)

    graph.add_node("router", router_node)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("execute", execute_node)
    graph.add_node("self_correct", _increment_retry_and_record_failure)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("router")
    graph.add_edge("router", "reasoning")
    graph.add_edge("reasoning", "execute")
    graph.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"retry": "self_correct", "finalize": "finalize"},
    )
    graph.add_edge("self_correct", "reasoning")
    graph.add_edge("finalize", END)

    return graph.compile()


# Module-level compiled graph, built once at import time (no I/O happens at
# compile time — LangGraph compilation is pure graph-structure validation).
compiled_graph = build_graph()
