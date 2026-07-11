# CodeFixer AI — Orchestrator (Python/FastAPI + LangGraph)

Agent DAG service: router -> reasoning -> execute -> self-correction loop -> finalize.
See `../CONTRACT.md` for the binding API contract this service implements, and
`../CLAUDE.md` for the overall app topology.

## Status

Real, complete code against real client libraries (LangGraph, LangChain,
`langchain-openai`, `httpx`, `psycopg`) — not stubs. This environment has no
`OPENROUTER_API_KEY`/`OPENAI_API_KEY` and no reachable Worker/Integration
Bridge/Postgres, so nothing has been run end-to-end with real credentials.
Everything below (imports, graph compilation, the full request-handling path,
the self-correction retry loop, and the US-04 failover threshold logic) has
been exercised with `pytest` against real modules with only the
HTTP/LangChain client boundary mocked — see "Running tests" below for the
actual output.

## Python version note

This dev machine only has Python 3.14 available. The dependency versions
below are the newest compatible set that installs cleanly under 3.14 (see the
comment at the top of `requirements.txt` for why the originally-suggested
older pins, e.g. `pydantic==2.10.x`/`langchain==0.3.x`, fail to build here —
`pydantic-core`'s Rust extension has no prebuilt wheel for `cp314` at those
versions and PyO3 refuses to compile against "too new" a Python). The
`Dockerfile` targets `python:3.12-slim`, where the original older pins would
also install fine if you prefer them for the container image — just re-check
`app/llm/*.py` against LangChain's API surface if you downgrade, since
0.3.x -> 1.x changed some import paths.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # runtime + test deps
# or: .venv/bin/pip install -r requirements.txt  # runtime only
```

## Required environment variables

Fail-fast at import time (no sensible default — the service will not start
without these):

- `DATABASE_URL` — Postgres connection string (telemetry tables only; schema
  owned by `../db/migrations/001_init.sql`)
- `WORKER_URL` — base URL of the Worker sandbox service (e.g. `http://worker:8100`)
- `INTEGRATION_BRIDGE_URL` — base URL of the Java Integration Bridge (e.g. `http://integration-bridge:8080`)

Optional, with defaults (see `.env.example` at the repo root for the full list):

- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` (default `nousresearch/hermes-3-llama-3.1-405b`)
- `OPENAI_API_KEY` / `OPENAI_MODEL` (default `gpt-4o`)
- `LLM_FAILOVER_MAX_ATTEMPTS` (default `2`), `LLM_FAILOVER_TIMEOUT_SECONDS` (default `3.0`)
- `ORCHESTRATOR_PORT` (default `8000`)

`OPENROUTER_API_KEY`/`OPENAI_API_KEY` are intentionally NOT required at
import/startup — the service and its test suite must be importable/runnable
without them. An LLM call attempted with no key raises a `ConfigError`-style
exception at call time (see `app/llm/openrouter_client.py` /
`app/llm/openai_fallback_client.py`).

A `.env` file (loaded via `python-dotenv`) is picked up automatically if
present — copy `../.env.example` and fill in real values for a live run.

## Running the service

```bash
.venv/bin/uvicorn app.main:app --reload
```

- `POST /internal/v1/analyze` — `{sessionId, userId, language, errorLog, code}`
  -> streams `application/x-ndjson`, one JSON event per line (see
  `../CONTRACT.md` §2 for the event shapes), ending with `{"type":"done"}`.
- `GET /health` -> `{"status": "UP"}`

## Running tests

```bash
.venv/bin/pytest tests/ -v
```

Real result from this environment (Python 3.14.4, all deps installed, no
real DB/LLM/network — everything mocked at the httpx/LangChain client
boundary):

```
17 passed in 0.99s
```

Covers: the self-correction loop's conditional-edge routing at every
retry_count/cap boundary; the US-04 failover threshold logic in isolation
(below-threshold stays on OpenRouter, at-threshold switches to OpenAI and
logs the incident, once-failed-over never retries OpenRouter again, a
single call exceeding the timeout is immediate failover); the router
agent's deterministic language heuristics; and two full end-to-end runs of
the real compiled LangGraph graph through `app.main`'s actual streaming
generator (happy path, and the execute -> self_correct -> reasoning retry
loop).

## Architecture notes

- **Graph** (`app/graph.py`): a real LangGraph `StateGraph` — nodes `router`,
  `reasoning`, `execute`, `self_correct`, `finalize`, compiled via
  `.compile()`. Edges: `router -> reasoning -> execute`; a conditional edge
  after `execute` routes to `self_correct` (failed and `retry_count` below
  the cap) or `finalize`; `self_correct -> reasoning` closes the loop;
  `finalize -> END`.
- **Event streaming**: LangGraph's `astream()` yields one item per node
  completion, too coarse for token-by-token `reasoning_token` events. Instead
  an `asyncio.Queue` is created per `/internal/v1/analyze` call and threaded
  through every node via `RunnableConfig`'s `configurable` dict; nodes push
  event dicts onto it as they're produced (including per-token during
  reasoning), and `app/main.py` drains the queue concurrently with a
  background `graph.ainvoke()` task.
- **Failover** (`app/llm/failover.py`): one `FailoverSession` per analyze
  call, tracking consecutive OpenRouter failures and a `failed_over` flag.
  Implements US-04 literally: 2 consecutive failures (or one call exceeding
  the timeout) switches to OpenAI for the rest of that session, emits a
  `provider_failover` event, and logs one `failover_incidents` row.
- **Telemetry** (`app/db.py`): every insert into `llm_call_logs` /
  `code_execution_logs` / `failover_incidents` is wrapped in its own
  try/except — a missing `sessions` FK row (e.g. a fresh sessionId the
  Gateway hasn't persisted yet) logs a warning and is swallowed, never
  crashing the main response stream.
