# OpenCode Worker (`worker/`)

CodeFixer AI's sandboxed code-execution service. Implements exactly one contractual
route pair — see `../CONTRACT.md` §4 — and is only ever called by the Orchestrator:

```
POST /execute   { "language": "python"|"java"|"javascript", "code": string, "testCommand": string|null }
                 -> { "exitCode": int, "stdout": string, "stderr": string, "timedOut": bool, "durationMs": int }
GET  /health     -> { "status": "UP" }
```

Every `/execute` call launches one brand-new, ephemeral Docker container via the
official `docker` Python SDK (`docker-py`), waits for it with a hard wall-clock
timeout, captures its logs and real exit code, and unconditionally removes it
(`container.remove(force=True)` in a `finally` block — never reused, never left
running, regardless of success/failure/timeout). See `app/sandbox.py` for the
implementation and D-01 below for why reuse is disallowed.

## D-01: why containers are never reused

Reusing a container across requests would let one user's leftover process state,
filesystem writes, or (if isolation were ever imperfect) injected code persist and
leak into the next, unrelated request — a cross-session contamination risk directly
against the product's NFR: "User code must not access host backend resources or
other user sessions." A fresh container per request is the simplest way to guarantee
no such state exists at the start of any execution.

## Isolation flags applied to every container

| Flag | Value | Purpose |
|---|---|---|
| `network_disabled` + `network_mode` | `True` / `"none"` | No network namespace access at all — code cannot reach the host, other containers, or the internet. Verified empirically (see Testing below): a raw socket `connect()` from inside the container fails. |
| `mem_limit` / `memswap_limit` | `256m` (env-configurable) | Hard memory ceiling; no swap beyond the same limit, so a memory bomb can't degrade the host via swap thrashing. |
| `nano_cpus` | `1_000_000_000` (1.0 CPU, env-configurable) | Hard CPU ceiling — a spin-loop can't starve the host or other sandboxes. |
| `pids_limit` | `64` (env-configurable) | Caps process/thread count — blocks classic fork-bomb DoS. |
| `read_only` | `True` | Root filesystem is immutable. Combined with... |
| `tmpfs={"/sandbox": "size=64m,exec,uid=65534,gid=65534,mode=1777"}` | | ...the *only* writable path in the whole container: a size-capped tmpfs, owned by the unprivileged user below, where the source file is written and (for Java) compiled. |
| `security_opt=["no-new-privileges"]` | | Blocks any setuid/setgid privilege escalation inside the container. |
| `cap_drop=["ALL"]` | | Drops every Linux capability (no `CAP_NET_RAW`, no `CAP_SYS_ADMIN`, nothing). |
| `user="65534:65534"` | | Runs as `nobody:nogroup`, never root-in-container — even a container-escape bug in the runtime image itself doesn't hand over root. |

All of these except the exact numbers are non-negotiable per-request; the numbers
themselves are env-configurable (`WORKER_CONTAINER_MEMORY_LIMIT`,
`WORKER_CONTAINER_NANO_CPUS`, `WORKER_CONTAINER_PIDS_LIMIT`,
`WORKER_CONTAINER_TMPFS_SIZE` — see `app/config.py`).

### How code gets into the container (and why not the obvious way)

The natural approach — `docker-py`'s `container.put_archive()` to write the source
file into the tmpfs after `create()` — **does not work here** and was confirmed to
fail against a real Docker daemon during this build: dockerd rejects any
`put_archive` call against a container whose `HostConfig.ReadonlyRootfs` is `true`,
with the literal error `"container rootfs is marked read-only"` — and this check
applies even when the archive's target path is itself a writable tmpfs mount, not
the read-only rootfs. Instead, the source code is base64-encoded and embedded
directly in the container's own command:

```sh
sh -c 'echo <base64> | base64 -d > /sandbox/code.py && python /sandbox/code.py'
```

so the container's own (unprivileged, capability-dropped, network-disabled)
entrypoint process decodes and writes the file itself, after every isolation flag
above is already in effect. No separate privileged write path against the Docker API
is ever needed.

### Per-language runtime mapping

| `language` | Image | Command |
|---|---|---|
| `python` | `python:3.12-slim` | `python /sandbox/code.py` |
| `javascript` | `node:20-slim` | `node /sandbox/code.js` |
| `java` | `eclipse-temurin:21-jdk-alpine` | `javac Main.java && java Main` (submitted code MUST define `public class Main` — the worker doesn't parse the snippet to discover a class name, so this convention is required) |

If `testCommand` is provided, it replaces the default interpreter/compiler
invocation entirely (source file is still written first), running instead inside
the same isolated container — e.g. `"pytest /sandbox/code.py"` or a JUnit/Mocha
invocation.

### Timeout enforcement

`WORKER_EXECUTION_TIMEOUT_SECONDS` (default `10`) is passed to `container.wait(timeout=...)`.
If the container hasn't exited by then, docker-py raises (a wrapped
`requests` timeout) instead of returning a status code — the worker treats this as
the container having timed out, force-kills it (`container.kill()`), sets
`timedOut: true` in the response, and still returns whatever stdout/stderr had been
written before the kill. The request never hangs past this timeout.

## Security model and its real limits — read this before deploying anywhere real

**This design mounts the host's Docker socket into the worker's own container**
(`docker-compose.yml`: `- /var/run/docker.sock:/var/run/docker.sock`) so this
service can launch sibling containers via the host daemon. This is a real,
well-known risk, not a hypothetical:

> **Anyone or anything that gains code execution inside the Worker's own FastAPI
> process (not the sandboxed user code — the Worker service itself, e.g. via a
> dependency vulnerability, a bug in this app, or a misconfigured deploy) inherits
> full control of the Docker socket, which is equivalent to root access on the host
> machine.** They could launch a privileged container, bind-mount the host root
> filesystem into it, and read/write anything as root. The per-request sandbox
> containers this service launches are well-isolated *from each other and from
> arbitrary user code running inside them* — but the Worker process itself sits
> outside that isolation boundary, with root-equivalent power, by construction of
> the socket-mount pattern.

This means the actual security boundary this Phase-1 build provides is: **isolates
untrusted *executed code* from the host and from other requests, but does NOT
isolate a compromise of the Worker application code itself.** That's an accurate,
not overstated, description of what "socket-mounted sibling containers" gives you.

**What a production-grade version would need instead** (not built here — see why,
below):
- A hardened container runtime for the actual sandbox containers — **gVisor**
  (`runsc`), **Firecracker** microVMs (what AWS Lambda/Fargate use), or **Kata
  Containers** — any of which give real kernel-level isolation instead of relying
  entirely on standard Linux namespaces/cgroups + the flags above.
- At minimum, if socket-mounting is kept: a **second, dedicated Docker daemon**
  that only this service can reach, network-isolated from the host's primary
  daemon and from every other service's containers, so a Worker compromise can't
  pivot to the rest of the stack via the *same* socket other things depend on.
- Ideally, no socket mount at all — a small privileged sidecar/API that the Worker
  calls to request container creation, so the Worker process itself never holds
  the raw Docker socket.

**Why Phase 1 doesn't build that yet:** this is a course/demo-scope system (see
`../CLAUDE.md`, `../documentation_codefixer_ai_en.md`'s SDLC plan — a 6-month
plan compressed into a structural skeleton, not an ongoing production service).
gVisor/Firecracker/Kata all add real operational cost (custom runtime install,
often a different orchestration story, meaningfully more infra to run and
maintain) that isn't justified before this ever handles real, non-demo,
potentially-adversarial input. The honest scope here is: real container-per-request
isolation with real resource/network/capability limits, on the standard Docker
runtime — a genuine, meaningful isolation boundary for "code that might be buggy or
fail to compile," but explicitly not a boundary hardened against a sophisticated,
motivated attacker targeting the Worker service itself.

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `WORKER_PORT` | `8100` | Port this FastAPI app listens on (matches `docker-compose.yml`'s `8100:8100`). |
| `WORKER_EXECUTION_TIMEOUT_SECONDS` | `10` | Hard wall-clock timeout per `/execute` call. |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker daemon the `docker` SDK connects to. |
| `WORKER_CONTAINER_MEMORY_LIMIT` | `256m` | Per-container memory ceiling (`mem_limit`/`memswap_limit`). |
| `WORKER_CONTAINER_NANO_CPUS` | `1000000000` (1.0 CPU) | Per-container CPU ceiling. |
| `WORKER_CONTAINER_PIDS_LIMIT` | `64` | Per-container process count ceiling. |
| `WORKER_CONTAINER_TMPFS_SIZE` | `64m` | Size of the one writable tmpfs mount (`/sandbox`). |

## Running standalone

```sh
cd worker
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DOCKER_HOST=unix:///var/run/docker.sock   # or leave unset to use the default
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Requires a reachable Docker daemon (local Docker Desktop/dockerd, or the socket
mounted in via `docker-compose.yml` when run as part of the full stack) and the
three runtime images pulled at least once (`docker pull python:3.12-slim`,
`docker pull node:20-slim`, `docker pull eclipse-temurin:21-jdk-alpine`) — the
worker does not pull images on demand; a missing image surfaces as a
`sandbox setup failed: runtime image not available` message in the response
rather than a hang.

## Running the tests

```sh
cd worker
pip install -r requirements.txt pytest httpx
pytest -v
```

`tests/test_main.py` mocks `run_in_sandbox` and only exercises the FastAPI
request/response wiring — no Docker needed. `tests/test_sandbox.py` launches
**real containers against a real Docker daemon** and is automatically skipped
(via a `docker.from_env().ping()` check, not a hardcoded flag) if none is
reachable — see "Verification" below for the real, current result of running it
in this repo's dev environment.

## Verification

This service's dependencies (`docker`-py, `fastapi`) and a genuine Docker daemon
were both actually reachable in the environment this was built in, so the full
suite was run for real, not just written-but-unverified:

- **17/17 tests passed** (`pytest -v`), including:
  - Python: hello-world exit 0 + stdout capture, a raised exception producing a
    nonzero exit code and matching stderr, a syntax error producing a nonzero
    exit, `time.sleep(30)` against a 2-second timeout correctly returning
    `timedOut: true` and killing the container within ~2s (not 30s), a live
    socket-`connect()` attempt to `1.1.1.1:80` failing (proves
    `network_disabled` actually blocks traffic, not just that the flag is set),
    a live write attempt to `/etc/pwned` failing (proves `read_only` actually
    blocks writes outside `/sandbox`), and a custom `testCommand` overriding
    the default invocation.
  - JavaScript: hello-world exit 0, a thrown `Error` producing a nonzero exit
    and matching stderr.
  - Java: a `Main` class compiling and running to produce real stdout, and a
    deliberate compile error producing a nonzero exit without hanging.
  - An unsupported language (`"ruby"`) raising before any Docker call is made.
- After the full run, `docker ps -a` showed **zero** leftover
  `opencode-worker-*` containers — the `finally: container.remove(force=True)`
  cleanup path was exercised on every test, including the timeout path, and
  verified to actually work, not just assumed correct from reading the code.

If you're running this somewhere Docker is genuinely unavailable, `test_sandbox.py`
will report a clean skip (with the reason above) rather than a false pass or a
hang — `test_main.py`'s 5 API-layer tests still run and pass regardless.
