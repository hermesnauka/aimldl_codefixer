# CodeFixer AI — Gateway (Node.js / Express BFF)

Backend-for-Frontend for CodeFixer AI: authenticates users, persists sessions/chat
messages to Postgres, and proxies chat turns to the Orchestrator, re-framing its
newline-delimited JSON stream as Server-Sent Events for the browser. See
`../CONTRACT.md` (this service's binding spec) and `../documentation_codefixer_ai_en.md`
§2.1 for the product context.

## Run standalone in dev

```bash
npm install
cp ../.env.example .env   # or export the vars below directly
npm run dev               # ts-node-dev, restarts on file change
```

`npm run dev` reads env vars from the process environment (not dotenv — export
them or use your shell/tool of choice to load `.env`). Required:

| Var | Example | Notes |
| --- | --- | --- |
| `GATEWAY_PORT` | `4000` | Defaults to `4000` if unset. |
| `DATABASE_URL` | `postgres://codefixer:codefixer@localhost:5432/codefixer` | Must point at a Postgres with `db/migrations/001_init.sql` already applied. |
| `JWT_SECRET` | `dev-only-secret-change-me-min-32-bytes-long` | HS256 signing secret. Must match across restarts or existing tokens break. |
| `ORCHESTRATOR_URL` | `http://localhost:8000` | Base URL of the Orchestrator; the gateway calls `POST {ORCHESTRATOR_URL}/internal/v1/analyze`. |

Startup fails fast (throws before the HTTP server binds) if `JWT_SECRET`,
`DATABASE_URL`, or `ORCHESTRATOR_URL` is missing — see `src/config.ts`.

## Build & run compiled

```bash
npm install
npm run build     # tsc -> dist/
npm start         # node dist/server.js
```

## What this service needs to actually work end-to-end

- A reachable Postgres with `db/migrations/001_init.sql` applied (seeds the
  demo user: `username=demo`, `password=demo1234`).
- A reachable Orchestrator at `ORCHESTRATOR_URL` implementing
  `POST /internal/v1/analyze` per `CONTRACT.md` §3 (ndjson stream of SSE event
  shapes). If the Orchestrator is down, `POST /api/v1/chat` returns `502
  {"error":"orchestrator_unreachable"}` (or `"orchestrator_error"` if it
  responds but not with a usable body) rather than hanging.

Without both, `/health` still returns `200 {"status":"UP"}` (it does not probe
its dependencies), but `/api/v1/auth/login` and `/api/v1/chat` will fail.

## Routes implemented (CONTRACT.md §1)

- `POST /api/v1/auth/login` — bcrypt-verifies against `users.password_hash`,
  issues an HS256 JWT (`sub`=user id, `username`).
- `POST /api/v1/chat` — requires `Authorization: Bearer <token>`. Creates a
  `sessions` row when `sessionId` is null, writes the user's message to
  `chat_messages`, proxies to the Orchestrator, streams each ndjson line back
  as one SSE `data:` frame in real time (not buffered), and persists the
  `final_fix` event's `code` as the assistant's `chat_messages` row once the
  stream ends.
- `GET /api/v1/chat/:sessionId/history` — requires auth; 404s if the session
  doesn't belong to the caller.
- `GET /health` — unauthenticated, always `{"status":"UP"}`.

## Docker

```bash
docker build -t codefixer-gateway .
docker run -p 4000:4000 \
  -e DATABASE_URL=postgres://codefixer:codefixer@postgres:5432/codefixer \
  -e JWT_SECRET=change-me \
  -e ORCHESTRATOR_URL=http://orchestrator:8000 \
  codefixer-gateway
```

Multi-stage build: `npm ci && npm run build` in a `node:22-slim` build stage,
then a slim runtime stage running `node dist/server.js` on `${GATEWAY_PORT:-4000}`
— matches `../docker-compose.yml`'s `4000:4000` port mapping.

## Known deviations / notes

- Audit logging is a structured `console.log` per request (method, path,
  userId, status, duration, timestamp), emitted via `setImmediate` off the
  synchronous response path — matches Phase 1 scope in
  `documentation_codefixer_ai_en.md` §2.1 ("asynchronous audit log writing").
  There is no dedicated audit table in `db/migrations/001_init.sql`, so this
  intentionally does not write one.
- `POST /api/v1/chat` validates that a supplied `sessionId` belongs to the
  authenticated user (404 `session_not_found` otherwise) — not explicit in
  CONTRACT.md but necessary so one user can't read/write another's session by
  guessing a UUID.
- Uses `node-fetch@2` (not native `fetch`) for the Orchestrator call, purely
  for a well-typed, streamable Node `Readable` response body under
  `@types/node-fetch`.
