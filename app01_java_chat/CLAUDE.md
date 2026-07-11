# CodeFixer AI (app01_java_chat)

Full implementation of the PRD/ARD/SDLC plan in `../documentation_codefixer_ai_en.md` (Polish:
`../dokumentacja_codefixer_ai_PL.md`) — an engineering chat assistant that takes a code
snippet + error/stack trace, reasons about the fix with an LLM agent graph, validates the fix
by executing it in an isolated sandbox, and streams the whole reasoning process back to the
user. See `CONTRACT.md` in this directory for the authoritative API/event contract every
service below is built against — read that before touching any service's code.

## Architecture: 5 services + Postgres, one polyglot stack per the ARD

```
frontend/            React + TypeScript + Vite — chat UI, NBP.pl visual identity, SSE client
gateway/              Node.js/Express — BFF: auth, session persistence, SSE proxy, audit log
orchestrator/         Python/FastAPI + LangGraph — the agent DAG (router → reasoning → worker
                      loop), LLM failover (OpenRouter Hermes 3 → OpenAI Codex)
integration-bridge/   Java/Spring Boot + LangChain4j — Java AST parsing, only called when the
                      detected language is Java
worker/               Python/FastAPI + Docker SDK — OpenCode sandbox: runs generated code in
                      an isolated, network-disabled, per-request container
db/migrations/        Postgres schema (users, sessions, chat_messages, llm_call_logs,
                      code_execution_logs, failover_incidents)
```

## Status: structurally complete, unexecuted

Every service is real, complete code against real client libraries (LangChain, LangChain4j,
`pg`, the Docker SDK, `python-jose`/`bcrypt`, etc.) — not stubs or pseudocode. But this
environment has no `OPENROUTER_API_KEY`/`OPENAI_API_KEY` and no reachable Docker daemon for the
sandbox worker to actually launch containers against, so **nothing here has been run
end-to-end**. Treat every service as correct-and-complete-but-unverified until it's run
somewhere with real credentials and a real container runtime — the same posture this
directory's own build process took for every piece.

## Key decisions

- **Auth (Phase 1):** one hardcoded demo user (`demo`/`demo1234`, real bcrypt hash, seeded by
  `db/migrations/001_init.sql`), JWT HS256 issued by the Gateway. No OAuth, no user
  registration flow yet — matches PRD §1.5's security scope without over-building auth this
  system's actual spec doesn't ask for in Phase 1.
- **LLM failover (US-04):** the Orchestrator tries OpenRouter/Hermes 3 first; after
  `LLM_FAILOVER_MAX_ATTEMPTS` consecutive failures or a `LLM_FAILOVER_TIMEOUT_SECONDS` timeout,
  it fails over to OpenAI Codex/ChatGPT and logs the incident to `failover_incidents` — exactly
  the acceptance criteria in US-04.
- **Sandbox isolation (NFR "Security"):** the Worker never executes code in its own process —
  every `/execute` call launches a fresh, network-disabled sibling container via the Docker
  socket, torn down after the run. This is a real isolation boundary (separate container,
  separate PID/network namespace) but **not** a hardened multi-tenant sandbox (no gVisor/
  Firecracker/Kata) — see `worker/README.md` for exactly what would be needed before this ever
  runs against untrusted, non-demo input, and don't claim stronger isolation than that.
- **Java AST parsing is its own service, not inlined into the Orchestrator:** matches the
  ARD's stated rationale (strong Java typing, legacy enterprise repo integration) — the
  Orchestrator only calls it when `language == "java"`, every other language skips it entirely.
- **NBP.pl visual identity is load-bearing, not decorative:** navy `#002C5B` / gold `#B59A57`
  / cream `#FCFBFA`, serif masthead, thin bordered cards — see `CONTRACT.md` §8 and
  `frontend/README.md` for the actual token file. Don't "modernize" this into a generic SaaS
  theme without checking the ARD first.

## Where to look for more

`../documentation_codefixer_ai_en.md` is the primary source (PRD §1, ARD §2, SDLC plan §3).
`CONTRACT.md` in this directory is the binding API/event contract across all 5 services — the
actual source of truth for request/response shapes, since the PRD/ARD describe intent, not
wire format. Each service also has its own `README.md` with stack-specific run/build/test
commands.
