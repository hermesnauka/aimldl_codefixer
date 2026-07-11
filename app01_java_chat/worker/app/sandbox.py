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
"""
from __future__ import annotations

import io
import tarfile
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

import docker
from docker.errors import ContainerError, DockerException, ImageNotFound, NotFound
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
    # Builds the shell command run as the container's entrypoint, given the
    # in-container path the source file was written to and the optional
    # user-supplied test command (CONTRACT.md §4's `testCommand`).
    build_command: Callable[[str, Optional[str]], list[str]]


def _python_command(code_path: str, test_command: Optional[str]) -> list[str]:
    if test_command:
        return ["sh", "-c", test_command]
    return ["python", code_path]


def _node_command(code_path: str, test_command: Optional[str]) -> list[str]:
    if test_command:
        return ["sh", "-c", test_command]
    return ["node", code_path]


def _java_command(code_path: str, test_command: Optional[str]) -> list[str]:
    # code_path is always /sandbox/src/Main.java (see LANGUAGE_SPECS) — javac
    # then java, chained with && so a compile failure short-circuits with its
    # own real exit code/stderr instead of falling through to `java`.
    if test_command:
        return ["sh", "-c", test_command]
    return [
        "sh",
        "-c",
        "cd /sandbox/src && javac Main.java && java Main",
    ]


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


def _get_docker_client() -> docker.DockerClient:
    if settings.docker_host:
        return docker.DockerClient(base_url=settings.docker_host)
    return docker.from_env()


def _make_tar_with_file(filename: str, content: bytes) -> io.BytesIO:
    """Builds an in-memory tar archive containing one file, suitable for
    `container.put_archive()` — this is how we inject the user's source code
    into the container's writable /sandbox/src tmpfs without ever needing a
    host-side temp file or a host bind-mount of user-controlled content."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(content))
    buffer.seek(0)
    return buffer


def run_in_sandbox(
    language: str,
    code: str,
    test_command: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> ExecutionResult:
    """Runs `code` inside a fresh, isolated, ephemeral container for `language`.

    Isolation flags applied to every container (see README.md for the full
    rationale of each):
      - network_disabled=True           no network namespace access at all
      - mem_limit / nano_cpus            hard resource ceilings (no fork bombs /
                                          memory exhaustion escaping to the host)
      - pids_limit                       caps process count (fork-bomb guard)
      - read_only=True                   root filesystem is immutable
      - tmpfs={"/sandbox": ...}          the ONLY writable path, size-capped,
                                          holds just the source + build output
      - security_opt=["no-new-privileges"]  blocks setuid privilege escalation
      - cap_drop=["ALL"]                 drops every Linux capability
      - user="65534:65534"               runs as `nobody`, never root-in-container
      - remove is handled explicitly in `finally` (container.remove(force=True))
        rather than relying on run(..., remove=True), so we can still read logs
        after a timeout-triggered kill.
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
        command = spec.build_command(f"/sandbox/src/{spec.filename}", test_command)

        container = client.containers.create(
            image=spec.image,
            command=command,
            name=container_name,
            working_dir="/sandbox/src",
            # --- isolation flags ---
            network_disabled=True,
            network_mode="none",
            mem_limit=settings.container_memory_limit,
            memswap_limit=settings.container_memory_limit,  # no swap beyond mem_limit
            nano_cpus=settings.container_nano_cpus,
            pids_limit=settings.container_pids_limit,
            read_only=True,
            tmpfs={"/sandbox": f"size={settings.container_tmpfs_size},exec"},
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            user="65534:65534",
            detach=True,
        )

        # Inject the source file into the writable tmpfs after creation, before
        # start — put_archive works on created-but-not-started containers.
        tar_stream = _make_tar_with_file(spec.filename, code.encode("utf-8"))
        container.put_archive("/sandbox/src", tar_stream)

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
            except (NotFound, DockerException):
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

    except (ImageNotFound, ContainerError) as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            exit_code=-1,
            stdout="",
            stderr=f"[worker] sandbox setup failed: {exc}",
            timed_out=False,
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
