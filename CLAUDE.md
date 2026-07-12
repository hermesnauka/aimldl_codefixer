# CodeFixer AI (aimldl_codefixer)

An engineering chat assistant: paste a code snippet plus an error/stack trace, and a
multi-agent LLM pipeline reasons about the fix, validates it by executing the code in an
isolated sandbox, and streams the whole reasoning process back to you live.

This repo currently contains one implementation, `app01_java_chat/` — a 5-service polyglot
stack (React/TS frontend, Node/Express gateway, Python/FastAPI+LangGraph orchestrator,
Java/Spring Boot+LangChain4j integration bridge, Python/FastAPI worker sandbox, Postgres).

## Where to look

- `app01_java_chat/CLAUDE.md` — architecture, key decisions, and current status
  ("structurally complete, unexecuted" — real code, not yet run end-to-end here).
- `app01_java_chat/CONTRACT.md` — the binding API/event contract every service is built
  against. Read this before touching any one service's code; it's the actual source of truth
  for wire format, not the narrative docs below.
- `app01_java_chat/README.md` — quick start (Docker Compose, required API keys).
- `documentation_codefixer_ai_en.md` / `dokumentacja_codefixer_ai_PL.md` — the full
  PRD/ARD/SDLC narrative (product vision, personas, sprint plan). Background reading only:
  describes intent, not what's actually implemented — verify against `app01_java_chat/`
  before trusting a specific detail from it.

## Rules for this repo

- Root stays short and universal (this file). Stack-specific detail belongs in
  `app01_java_chat/CLAUDE.md`, not here.
- If a future `app02_*`-style sibling implementation is added, give it its own scoped
  `CLAUDE.md` the same way, and update the "Where to look" section above.
