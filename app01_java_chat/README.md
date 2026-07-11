# CodeFixer AI

An engineering chat assistant: paste a code snippet plus an error/stack trace, and a
multi-agent LLM pipeline reasons about the fix, validates it by executing the code in an
isolated sandbox, and streams the whole reasoning process back to you live. Full spec:
`../documentation_codefixer_ai_en.md`. Architecture/status: `CLAUDE.md`. API contract:
`CONTRACT.md`.

## Prerequisites

- Docker + Docker Compose
- An OpenRouter API key (primary LLM, Hermes 3) — required
- An OpenAI API key (fallback LLM, Codex/ChatGPT) — optional but recommended, since without it
  US-04's failover has nowhere to fail over to

## Quick start

```bash
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY (required), OPENAI_API_KEY (recommended),
# JWT_SECRET (any random 32+ byte string)

docker compose up --build
```

This starts, in order: Postgres → `db-init` (applies the schema once, then exits) →
Integration Bridge + Worker (independent) → Orchestrator → Gateway → Frontend.

- Frontend: http://localhost:5173
- Gateway API: http://localhost:4000/api/v1/...
- Gateway health: http://localhost:4000/health
- Orchestrator (internal): http://localhost:8000
- Integration Bridge health: http://localhost:8080/health
- Worker (internal): http://localhost:8100

Log in at http://localhost:5173 with the seeded demo account: **username `demo`, password
`demo1234`**.

## Verifying it's working

```bash
curl http://localhost:4000/health
# {"status":"UP"}

curl -X POST http://localhost:4000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo1234"}'
# {"token":"...", "username":"demo"}
```

Then open http://localhost:5173, log in, and paste a small broken code snippet (e.g. a Python
`IndexError`) with its traceback into the chat box — you should see status updates stream in
(`routing` → `reasoning` → `executing` → `finalizing`), followed by a final fix and
explanation.

## Running each service outside Docker (development)

See each service's own `README.md` for language-specific commands:
`frontend/README.md`, `gateway/README.md`, `orchestrator/README.md`,
`integration-bridge/README.md`, `worker/README.md`.

## What hasn't been verified

This was built in an environment with no LLM API keys and no reachable Docker daemon for the
sandbox worker, so the full chat→reasoning→execution→fix loop has never been run end-to-end.
Every service is real, complete code — not stubs — but treat it as unverified until you run it
somewhere with real credentials and a real container runtime.
