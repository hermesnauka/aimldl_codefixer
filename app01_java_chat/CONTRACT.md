# CodeFixer AI — Service Contract (app01_java_chat)

This is the single source of truth every service in this app is built against. If you're
implementing one service, read this file fully before writing code — it defines every
boundary your service crosses. Do not invent a different shape; if something is ambiguous,
prefer the most literal reading of `../CLAUDE.md`'s PRD/ARD.

## Topology

```
Browser (frontend, React/TS, :5173 dev / served by nginx in prod)
   │  HTTPS, cookie/Bearer auth
   ▼
Gateway (Node.js/Express BFF, :4000)
   │  proxies chat turns as SSE, writes audit/session rows to Postgres
   ▼
Orchestrator (Python/FastAPI + LangGraph, :8000)
   │                              │
   │ POST /execute                │ POST /api/v1/ast/parse
   ▼                              ▼
Worker (OpenCode sandbox, :8100)   Integration Bridge (Java/Spring Boot, :8080)

Postgres (:5432) — written to by Gateway (sessions/audit) and Orchestrator (llm_call_logs,
code_execution_logs, failover_incidents, chat_messages).
```

## 1. Frontend ↔ Gateway

### `POST /api/v1/auth/login`
Request: `{ "username": string, "password": string }`
Response `200`: `{ "token": string, "username": string }`
Response `401`: `{ "error": "invalid_credentials" }`

### `POST /api/v1/chat`
Headers: `Authorization: Bearer <token>`
Request:
```json
{
  "sessionId": "uuid-or-null-to-create-new",
  "language": "python" | "java" | "javascript" | null,
  "errorLog": "string, optional stack trace / compiler output",
  "code": "string, the user's source snippet"
}
```
Response: `Content-Type: text/event-stream`. Each SSE event's `data:` field is one JSON object,
one of the shapes in **"SSE Event Shapes"** below. The stream ends with a `done` event.

### `GET /api/v1/chat/:sessionId/history`
Response `200`: `{ "sessionId": string, "messages": ChatMessage[] }` where `ChatMessage` is
`{ "id": string, "role": "user"|"assistant", "content": string, "reasoningTokens": string|null, "createdAt": string }`.

### `GET /health`
Response `200`: `{ "status": "UP" }`

## 2. SSE Event Shapes (Gateway → Frontend, and Orchestrator → Gateway — same shape, Gateway
just re-frames Orchestrator's stream as SSE if Orchestrator itself emits newline-delimited JSON)

```json
{"type": "status", "stage": "routing" | "reasoning" | "executing" | "self_correcting" | "finalizing"}
{"type": "reasoning_token", "token": "string, one incremental token of Chain-of-Thought"}
{"type": "provider_failover", "from": "openrouter/hermes-3", "to": "openai/codex", "reason": "string"}
{"type": "execution_result", "language": "string", "exitCode": 0, "stdout": "string", "stderr": "string", "durationMs": 1234}
{"type": "final_fix", "code": "string", "explanation": "string", "language": "string"}
{"type": "error", "message": "string"}
{"type": "done"}
```

## 3. Gateway ↔ Orchestrator

### `POST /internal/v1/analyze` (Orchestrator, FastAPI)
Request: `{ "sessionId": string, "userId": string, "language": string|null, "errorLog": string|null, "code": string }`
Response: `Content-Type: application/x-ndjson` — newline-delimited JSON, each line one of the
"SSE Event Shapes" objects above. Gateway reads this stream line-by-line and re-emits each
line as one SSE `data:` frame to the browser, unchanged.

## 4. Orchestrator ↔ Worker (OpenCode sandbox)

### `POST /execute` (Worker, FastAPI, :8100)
Request: `{ "language": "python"|"java"|"javascript", "code": string, "testCommand": string|null }`
Response `200`:
```json
{ "exitCode": 0, "stdout": "string", "stderr": "string", "timedOut": false, "durationMs": 842 }
```
The worker MUST run each request in a freshly-created, network-disabled container (or
equivalent isolation) with a hard wall-clock timeout (default 10s) and MUST NOT reuse
containers across requests — see `worker/README.md` D-01 for why.

## 5. Orchestrator ↔ Integration Bridge (Java)

### `POST /api/v1/ast/parse` (Integration Bridge, Spring Boot, :8080)
Request: `{ "language": "java", "code": string }`
Response `200`:
```json
{
  "valid": true,
  "issues": [{"line": 12, "severity": "error"|"warning", "message": "string"}],
  "classNames": ["string"],
  "methodSignatures": ["string"]
}
```
Only called by the Orchestrator when `language == "java"` — every other language skips this
service entirely and goes straight to the Reasoning Agent.

### `GET /health` (Integration Bridge)
Response `200`: `{ "status": "UP" }`

## 6. Auth model (Phase 1)

One hardcoded demo user seeded by `db/migrations/001_init.sql` (`username=demo`,
bcrypt-hashed `password=demo1234`, overridable via `DEMO_USER_PASSWORD` env var at seed time).
Gateway issues a JWT HS256 token (`JWT_SECRET` env var, never committed) on successful login;
every other route requires `Authorization: Bearer <token>`, verified by Gateway middleware.
Orchestrator/Worker/Integration-Bridge trust Gateway's internal network calls unauthenticated
(Phase 1 scope — no service-to-service auth token yet, matching this being a BFF-fronted
internal topology, not a public multi-tenant one).

## 7. Postgres schema — see `db/migrations/001_init.sql` for the authoritative DDL

Tables: `users`, `sessions`, `chat_messages`, `llm_call_logs`, `code_execution_logs`,
`failover_incidents`. Every service that writes telemetry (Gateway for audit/session rows,
Orchestrator for LLM/execution/failover rows) connects with its own narrowly-scoped
`DATABASE_URL` — see `.env.example`.

## 8. NBP.pl visual identity tokens (frontend, CLAUDE.md §2.3)

```
--color-navy: #002C5B;   /* dominant, headers/nav/primary buttons */
--color-gold: #B59A57;   /* highlights, callout borders, secondary headings */
--color-bg:   #FCFBFA;   /* matte cream/light-gray page background */
```
Serif typography for the logo/masthead; thin, distinct borders on cards/tables (formal
financial-report aesthetic, not a generic SaaS template).

## 9. What "Phase 1, structurally complete" means here

Every service below is real, runnable code against real client libraries (LangChain,
LangChain4j, `pg`, `psycopg`, Docker SDK, etc.) — not stubs. But this environment has no
`OPENROUTER_API_KEY`/`OPENAI_API_KEY` and no Docker daemon reachable for the sandbox worker,
so nothing has actually been executed end-to-end. Treat every service the same way: correct
and complete against this contract, unverified until run somewhere with real credentials and
a real container runtime.
