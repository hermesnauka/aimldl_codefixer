"""Real container-based code execution sandbox.

Every call to `run_in_sandbox()` launches one brand-new, ephemeral Docker
container via the `docker` SDK, waits (with a hard timeout) for it to finish,
captures its stdout/stderr/exit code, and unconditionally removes it. No
container is ever reused across requests — see ../README.md D-01 for why.

This is a REAL isolation boundary (separate container => separate filesystem,
PID namespace, network namespace, cgroup) but it is explicitly NOT a hardened
multi-tenant sandbox (no gVisor/Firecracker/Kata Containers) and this service's
own container has the host Docker socket mounted into it — see ../README.md's
"Security model and its real limits" section before treating this as safe
against a truly hostile/adversarial payload, as opposed to "code that might
fail to compile or crash," which is the actual Phase-1 threat model.

Code-injection note: the source code is never written to the host filesystem
and never `put_archive()`-ed into the container. Docker's daemon rejects
`put_archive` against any container whose HostConfig has `ReadonlyRootfs=true`
— confirmed empirically against a real dockerd (see git history/README for
the exact error: `"container rootfs is marked read-only"`), and that
restriction applies even when the archive's target path is itself a writable
tmpfs mount. Instead, the code is base64-encoded and embedded directly in the
container's command (`sh -c 'echo <b64> | base64 -d > /sandbox/<file> && ...'`)
so it's decoded and written by the container's own entrypoint process, after
the read-only rootfs + tmpfs are already in effect — no separate write step
against the Docker API is needed at all.
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

from app.config import settings


class UnsupportedLanguageError(ValueError):
    """Raised when `language` isn't one of the languages this worker supports."""


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


@dataclass
class _RuntimeSpec:
    """How to run one language's code inside its runtime image."""

    image: str
    filename: str
    # Builds the in-container shell command, given the base64-encoded source
    # and the optional user-supplied test command (CONTRACT.md §4's
    # `testCommand`). Always returns an argv list for `sh -c '...'`.
    build_command: Callable[[str, str, Optional[str]], list[str]]


def _write_and_run(filename: str, b64_code: str, run_cmd: str, test_command: Optional[str]) -> list[str]:
    write_step = f"echo {b64_code} | base64 -d > /sandbox/{filename}"
    if test_command:
        # testCommand runs in place of the default interpreter/compiler
        # invocation, but the source file is still written first so a custom
        # test command (e.g. "pytest /sandbox/code.py") has something to
        # operate on.
        return ["sh", "-c", f"{write_step} && {test_command}"]
    return ["sh", "-c", f"{write_step} && {run_cmd}"]


def _python_command(filename: str, b64_code: str, test_command: Optional[str]) -> list[str]:
    return _write_and_run(filename, b64_code, f"python /sandbox/{filename}", test_command)


def _node_command(filename: str, b64_code: str, test_command: Optional[str]) -> list[str]:
    return _write_and_run(filename, b64_code, f"node /sandbox/{filename}", test_command)


def _java_command(filename: str, b64_code: str, test_command: Optional[str]) -> list[str]:
    # javac then java, chained with && so a compile failure short-circuits
    # with its own real exit code/stderr instead of falling through to `java`.
    return _write_and_run(
        filename, b64_code, "javac Main.java && java Main", test_command
    )


LANGUAGE_SPECS: dict[str, _RuntimeSpec] = {
    "python": _RuntimeSpec(
        image="python:3.12-slim",
        filename="code.py",
        build_command=_python_command,
    ),
    "javascript": _RuntimeSpec(
        image="node:20-slim",
        filename="code.js",
        build_command=_node_command,
    ),
    "java": _RuntimeSpec(
        # Java requires the source file be named after its public class. We
        # force the convention that the submitted snippet defines `class Main`
        # (documented in README.md) so we always know the filename in advance
        # without parsing the source ourselves.
        image="eclipse-temurin:21-jdk-alpine",
        filename="Main.java",
        build_command=_java_command,
    ),
}

# Owned by the unprivileged `nobody` uid/gid we run containers as, so that
# uid can write the decoded source file and (for Java) javac's output classes
# into it. 1777 (sticky + world rwx) mirrors /tmp's own real-world permission
# convention rather than inventing something more permissive than necessary.
_SANDBOX_UID_GID = 65534
_SANDBOX_TMPFS_MODE = "1777"


def _get_docker_client() -> docker.DockerClient:
    if settings.docker_host:
        return docker.DockerClient(base_url=settings.docker_host)
    return docker.from_env()


def run_in_sandbox(
    language: str,
    code: str,
    test_command: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> ExecutionResult:
    """Runs `code` inside a fresh, isolated, ephemeral container for `language`.

    Isolation flags applied to every container (see README.md for the full
    rationale of each):
      - network_disabled=True + network_mode="none"  no network namespace access at all
      - mem_limit / memswap_limit / nano_cpus         hard resource ceilings (no memory
                                                       exhaustion or unbounded CPU spin
                                                       escaping to the host)
      - pids_limit                                    caps process count (fork-bomb guard)
      - read_only=True                                root filesystem is immutable
      - tmpfs={"/sandbox": "...,uid=65534,gid=65534,mode=1777"}
                                                       the ONLY writable path, size-capped,
                                                       owned by the unprivileged user below
      - security_opt=["no-new-privileges"]            blocks setuid privilege escalation
      - cap_drop=["ALL"]                              drops every Linux capability
      - user="65534:65534"                            runs as `nobody`, never root-in-container
      - container.remove(force=True) in `finally`     never left running or reused, even
                                                       on an exception or a timeout
    """
    if language not in LANGUAGE_SPECS:
        raise UnsupportedLanguageError(
            f"unsupported language: {language!r} (supported: {sorted(LANGUAGE_SPECS)})"
        )

    spec = LANGUAGE_SPECS[language]
    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else settings.execution_timeout_seconds
    )

    client = _get_docker_client()
    container: Optional[Container] = None
    container_name = f"opencode-worker-{uuid.uuid4().hex[:12]}"
    start = time.monotonic()
    timed_out = False

    try:
        b64_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
        command = spec.build_command(spec.filename, b64_code, test_command)

        tmpfs_opts = (
            f"size={settings.container_tmpfs_size},exec,"
            f"uid={_SANDBOX_UID_GID},gid={_SANDBOX_UID_GID},mode={_SANDBOX_TMPFS_MODE}"
        )

        try:
            container = client.containers.create(
                image=spec.image,
                command=command,
                name=container_name,
                working_dir="/sandbox",
                # --- isolation flags ---
                network_disabled=True,
                network_mode="none",
                mem_limit=settings.container_memory_limit,
                memswap_limit=settings.container_memory_limit,  # no swap beyond mem_limit
                nano_cpus=settings.container_nano_cpus,
                pids_limit=settings.container_pids_limit,
                read_only=True,
                tmpfs={"/sandbox": tmpfs_opts},
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                user=f"{_SANDBOX_UID_GID}:{_SANDBOX_UID_GID}",
            )
        except ImageNotFound as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"[worker] sandbox setup failed: runtime image not available: {exc}",
                timed_out=False,
                duration_ms=duration_ms,
            )

        container.start()

        try:
            wait_result = container.wait(timeout=effective_timeout)
            exit_code = int(wait_result.get("StatusCode", -1))
        except Exception:
            # docker-py raises (requests ReadTimeout / ConnectionError wrapped)
            # when the container hasn't exited by `timeout` seconds — this is
            # our hard wall-clock enforcement, not a real docker daemon error.
            timed_out = True
            exit_code = -1
            try:
                container.kill()
            except (NotFound, APIError, DockerException):
                pass  # already dead / gone — nothing to kill

        duration_ms = int((time.monotonic() - start) * 1000)

        try:
            raw_logs_stdout = container.logs(stdout=True, stderr=False)
            raw_logs_stderr = container.logs(stdout=False, stderr=True)
        except (NotFound, DockerException):
            raw_logs_stdout, raw_logs_stderr = b"", b""

        stdout = raw_logs_stdout.decode("utf-8", errors="replace")
        stderr = raw_logs_stderr.decode("utf-8", errors="replace")

        if timed_out:
            stderr = (stderr + "\n" if stderr else "") + (
                f"[worker] execution exceeded {effective_timeout}s wall-clock "
                "timeout; container was forcibly killed."
            )

        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )

    finally:
        # Never leave a container running or reusable, regardless of the path
        # taken above — this is the one invariant CONTRACT.md §4 calls out by
        # name ("MUST NOT reuse containers across requests").
        if container is not None:
            try:
                container.remove(force=True)
            except (NotFound, DockerException):
                pass
        try:
            client.close()
        except Exception:
            pass
