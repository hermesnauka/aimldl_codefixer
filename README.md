# CodeFixer AI

An engineering chat assistant: paste a code snippet plus an error/stack trace, and a
multi-agent LLM pipeline reasons about the fix, validates it by executing the code in an
isolated sandbox, and streams the whole reasoning process back to you live.

Built as a course project for self-educational purposes, exploring a polyglot multi-agent
architecture (LangGraph orchestration, LLM provider failover, sandboxed code execution,
Java AST parsing) rather than any single-language stack.

## Quick start

This repo currently contains one implementation, `app01_java_chat/`. See that directory's
`README.md` for the actual quick start (Docker Compose, required API keys):

```bash
cd app01_java_chat
cp .env.example .env
# edit .env: OPENROUTER_API_KEY (required), OPENAI_API_KEY (recommended), JWT_SECRET
docker compose up --build
```

## Documentation

- `CLAUDE.md` — repo map and pointers for AI coding assistants.
- `app01_java_chat/CLAUDE.md` — architecture and current status.
- `app01_java_chat/CONTRACT.md` — the binding API/event contract across all 5 services.
- `documentation_codefixer_ai_en.md` / `dokumentacja_codefixer_ai_PL.md` — full PRD/ARD/SDLC
  (product vision, personas, sprint plan).
