"""FastAPI entrypoint for the Orchestrator service.

CONTRACT.md §3: POST /internal/v1/analyze — driven by the compiled LangGraph
graph in app/graph.py, streamed back as newline-delimited JSON
(application/x-ndjson), one JSON object per line, ending with {"type": "done"}.
Also GET /health -> {"status": "UP"} per CONTRACT.md §1/§9's health shape.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import db
from app.graph import GraphState, compiled_graph
from app.llm.failover import FailoverSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.open_pool()
    try:
        yield
    finally:
        await db.close_pool()


app = FastAPI(title="CodeFixer AI — Orchestrator", lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    sessionId: str
    userId: str
    language: str | None = None
    errorLog: str | None = None
    code: str


@app.get("/health")
async def health() -> dict:
    return {"status": "UP"}


@app.post("/internal/v1/analyze")
async def analyze(request: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(
        _run_analyze_stream(request), media_type="application/x-ndjson"
    )


async def _run_analyze_stream(request: AnalyzeRequest) -> AsyncIterator[str]:
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    initial_state: GraphState = {
        "session_id": request.sessionId,
        "user_id": request.userId,
        "language": request.language,
        "error_log": request.errorLog,
        "code": request.code,
        "reasoning_trace": [],
        "execution_result": None,
        "bridge_result": None,
        "prior_failures": [],
        "retry_count": 0,
        "current_provider": "openrouter/hermes-3",
        "fix_code": None,
        "fix_explanation": None,
        "failed": False,
        "error_message": None,
        "failover_session": FailoverSession(session_id=request.sessionId),
    }

    run_config = {"configurable": {"event_queue": event_queue, "thread_id": request.sessionId}}

    async def run_graph() -> None:
        try:
            await compiled_graph.ainvoke(initial_state, config=run_config)
        except Exception as exc:  # noqa: BLE001 - convert any graph crash into an error event
            logger.exception("Graph execution failed for session %s", request.sessionId)
            await event_queue.put({"type": "error", "message": f"Internal error: {exc}"})
        finally:
            await event_queue.put(None)  # sentinel: graph task finished

    graph_task = asyncio.create_task(run_graph())

    try:
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield json.dumps(event) + "\n"
    finally:
        # Ensure the background task is awaited/cleaned up even if the
        # client disconnects mid-stream.
        if not graph_task.done():
            graph_task.cancel()
        try:
            await graph_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    yield json.dumps({"type": "done"}) + "\n"
