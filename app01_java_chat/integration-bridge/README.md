# Integration Bridge (Java / Spring Boot / LangChain4j)

CodeFixer AI's "Enterprise Integration Bridge" — parses the Abstract Syntax Tree (AST) of
Java source snippets. Called only by the Orchestrator, and only when the detected
programming language is Java. See `../CONTRACT.md` §5 for the exact API contract this
service implements.

## Run standalone

```bash
mvn spring-boot:run
```

The service listens on `${SERVER_PORT:-8080}` (matches `docker-compose.yml`'s `8080:8080`
mapping).

## Run tests

```bash
mvn test
```

## API

- `POST /api/v1/ast/parse` — request `{"language": "java", "code": "..."}`, response
  `{"valid": bool, "issues": [{"line": int, "severity": "error"|"warning", "message": str}],
  "classNames": [str], "methodSignatures": [str]}`.
- `GET /health` — `{"status": "UP"}`.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SERVER_PORT` | no | `8080` | HTTP port the service listens on. |
| `OPENAI_API_KEY` | no | *(unset)* | If set, `LangChain4jService` uses it to call an `OpenAiChatModel` and summarize AST issues into one natural-language sentence (logged, not part of the contract response). If unset, the service gracefully falls back to a plain concatenation of issue messages — no LLM call is made, and the request never fails because of this. |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Model name used for the above summarization, when `OPENAI_API_KEY` is set. |

## Implementation notes

- Real AST parsing via [JavaParser](https://github.com/javaparser/javaparser)
  (`com.github.javaparser:javaparser-core`) — `AstParserService` walks a real
  `CompilationUnit`, it does not use regex heuristics.
- `LangChain4jService` is a genuine, small `langchain4j-open-ai` integration, wired but
  intentionally secondary: it never affects `valid`/`issues`/`classNames`/`methodSignatures`,
  it only produces a log-line summary.
- Controllers (`AstController`, `HealthController`) are kept thin; all logic lives in the
  `service` package.
