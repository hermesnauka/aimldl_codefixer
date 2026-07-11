# CodeFixer AI — Frontend

React 18 + TypeScript 5 + Vite chat UI for CodeFixer AI. Talks only to the
Gateway (`/api/v1/auth/login`, `/api/v1/chat` SSE, `/api/v1/chat/:sessionId/history`,
`/health`) — see `../CONTRACT.md` for the exact wire shapes and `../CLAUDE.md`
for how this service fits into the 5-service polyglot stack.

## Run standalone in dev mode

```bash
npm install
npm run dev
```

This starts Vite's dev server on `http://localhost:5173`. The app needs a
running Gateway to actually log in or chat — point it at one via the
`VITE_GATEWAY_URL` env var (see `.env.example` at the repo root, `app01_java_chat/`):

```bash
VITE_GATEWAY_URL=http://localhost:4000 npm run dev
```

If unset, it defaults to `http://localhost:4000`. Note Vite env vars are
compile-time: in the Docker image the value is baked in at `npm run build`
time via the `VITE_GATEWAY_URL` build arg (see `Dockerfile`), not read at
container-start time.

## Build

```bash
npm run build
```

Runs `tsc -b` (type-check, no emit) then `vite build`, producing static
assets in `dist/`. Verified in this environment: `npm install` and
`npm run build` both complete successfully with zero TypeScript errors.

## Lint

```bash
npm run lint
```

ESLint (flat-config-free `.eslintrc.cjs`, `@typescript-eslint` +
`react-hooks` + `react-refresh` plugins). Verified clean (zero errors/warnings)
in this environment.

## Tests

No test suite exists yet for this Phase-1 slice (`npm test` is wired to
`vitest run` but no `*.test.ts(x)` files or vitest devDependency have been
added — add `vitest`/`@testing-library/react` before writing the first spec).

## Docker

```bash
docker build -t codefixer-frontend .
docker run -p 5173:80 codefixer-frontend
```

Multi-stage build: `node:22-alpine` builds the static bundle, then
`nginx:1.27-alpine` serves `dist/` on port 80 with a SPA fallback
(`nginx.conf`). The root `docker-compose.yml` maps host `5173` to the
container's `80` — do not change that mapping.

## Architecture notes

- **Routing:** no react-router — `src/App.tsx` is a simple state-based switch
  between `Login` and `Chat` gated on whether a JWT is present in
  `localStorage` (`src/api/client.ts`). Real for a two-screen Phase-1 app;
  revisit if more screens are added.
- **Auth storage:** JWT + username in `localStorage` (Phase 1 only, per
  `CONTRACT.md` §6 — no refresh tokens, no httpOnly cookie yet).
- **SSE consumption (`src/hooks/useChatStream.ts`):** `POST /api/v1/chat`
  needs a JSON body, which native `EventSource` cannot send (GET-only). This
  hook uses `fetch` + the response body's `ReadableStream`, manually
  splitting on blank lines (`\n\n`) for SSE frame boundaries and parsing each
  frame's `data:` line(s) as JSON — a real hand-rolled SSE parser, not a
  disguised `EventSource`.
- **Visual identity (`src/styles/tokens.css`):** every NBP.pl color
  (`--color-navy #002C5B`, `--color-gold #B59A57`, `--color-bg #FCFBFA`) is a
  CSS custom property consumed by every component's class names — no
  ad hoc hex values in component code. Serif masthead (`--font-serif`), thin
  bordered "financial report" cards throughout.

## Deviations from CONTRACT.md

- `ChatRequest.sessionId` is client-managed only. CONTRACT.md's SSE event
  shapes (section 2) never echo a `sessionId` back to the caller, so there is
  no wire-level way for the frontend to learn a Gateway-assigned session id
  after the first turn. The UI keeps `sessionId` as `null` (i.e. "let the
  Gateway create one") for an entire browser session and exposes a manual
  "New session" button to reset the client-side conversation and force a new
  server-side session on the next turn. If a future contract revision adds a
  `sessionId` field to one of the SSE events (e.g. `status` or `done`), wire
  it up in `useChatStream`/`Chat.tsx` instead of leaving this as client-only
  state.
- Everything else (request/response bodies, all 7 SSE event `type` variants,
  the NBP color tokens) is implemented exactly as CONTRACT.md specifies —
  no other shape deviations were needed.
