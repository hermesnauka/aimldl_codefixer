"""Real pytest tests against the actual `run_in_sandbox()` implementation.

These tests launch REAL Docker containers via the `docker` SDK — they are
skipped automatically (not faked/mocked) if no Docker daemon is reachable
from wherever `pytest` is run, via the `docker_available` fixture/marker
below. See ../README.md for exactly which images (`python:3.12-slim`,
`node:20-slim`, `eclipse-temurin:21-jdk-alpine`) must be pulled (or pullable)
for the full suite to pass.
"""
from __future__ import annotations

import time

import pytest
from docker.errors import DockerException

from app.sandbox import ExecutionResult, UnsupportedLanguageError, run_in_sandbox


def _docker_daemon_reachable() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except DockerException:
        return False
    except Exception:
        return False


DOCKER_AVAILABLE = _docker_daemon_reachable()

requires_docker = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason=(
        "No reachable Docker daemon in this environment — these tests are "
        "written to run for real once a daemon (Docker Desktop/dockerd/CI "
        "docker-in-docker) is available. See README.md."
    ),
)


@requires_docker
class TestPythonExecution:
    def test_hello_world_exits_zero_and_captures_stdout(self):
        result = run_in_sandbox("python", "print('hello')")

        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.timed_out is False
        assert result.duration_ms > 0

    def test_runtime_error_returns_nonzero_exit_and_stderr(self):
        result = run_in_sandbox("python", "raise ValueError('boom')")

        assert result.exit_code != 0
        assert "ValueError" in result.stderr
        assert "boom" in result.stderr
        assert result.timed_out is False

    def test_syntax_error_returns_nonzero_exit(self):
        result = run_in_sandbox("python", "def broken(:\n    pass")

        assert result.exit_code != 0
        assert result.timed_out is False

    def test_sleep_beyond_timeout_is_killed_and_flagged(self):
        start = time.monotonic()
        result = run_in_sandbox(
            "python",
            "import time\ntime.sleep(30)\nprint('should not reach here')",
            timeout_seconds=2,
        )
        elapsed = time.monotonic() - start

        assert result.timed_out is True
        assert "should not reach here" not in result.stdout
        # Wall-clock enforcement must actually bound real elapsed time, not
        # just the field in the response — this is the crux of the timeout
        # guarantee CONTRACT.md §4 requires.
        assert elapsed < 15, "container was not killed promptly at timeout"

    def test_network_is_disabled_inside_container(self):
        # Any outbound connection attempt must fail — this is the concrete,
        # executable proof of the "network_disabled" isolation flag, not just
        # an assertion about a flag we set and hope works.
        code = (
            "import socket\n"
            "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "s.settimeout(3)\n"
            "try:\n"
            "    s.connect(('1.1.1.1', 80))\n"
            "    print('CONNECTED')\n"
            "except OSError as e:\n"
            "    print('BLOCKED:', e)\n"
        )
        result = run_in_sandbox("python", code, timeout_seconds=8)

        assert "CONNECTED" not in result.stdout
        assert "BLOCKED" in result.stdout

    def test_filesystem_outside_sandbox_is_read_only(self):
        # read_only=True on the root filesystem should reject any write
        # attempt outside the /sandbox tmpfs.
        code = (
            "try:\n"
            "    open('/etc/pwned', 'w').write('x')\n"
            "    print('WROTE')\n"
            "except OSError as e:\n"
            "    print('BLOCKED:', e)\n"
        )
        result = run_in_sandbox("python", code, timeout_seconds=8)

        assert "WROTE" not in result.stdout
        assert "BLOCKED" in result.stdout

    def test_test_command_overrides_default_invocation(self):
        result = run_in_sandbox(
            "python",
            "print('unused')",
            test_command="python -c \"print('from test command')\"",
        )

        assert result.exit_code == 0
        assert "from test command" in result.stdout


@requires_docker
class TestJavaScriptExecution:
    def test_hello_world_exits_zero(self):
        result = run_in_sandbox("javascript", "console.log('hello from node')")

        assert result.exit_code == 0
        assert "hello from node" in result.stdout
        assert result.timed_out is False

    def test_thrown_error_returns_nonzero_exit(self):
        result = run_in_sandbox("javascript", "throw new Error('boom')")

        assert result.exit_code != 0
        assert "boom" in result.stderr


@requires_docker
class TestJavaExecution:
    def test_hello_world_compiles_and_runs(self):
        code = (
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            '        System.out.println("hello from java");\n'
            "    }\n"
            "}\n"
        )
        result = run_in_sandbox("java", code, timeout_seconds=30)

        assert result.exit_code == 0
        assert "hello from java" in result.stdout

    def test_compile_error_returns_nonzero_exit(self):
        code = "public class Main { this is not valid java }"
        result = run_in_sandbox("java", code, timeout_seconds=30)

        assert result.exit_code != 0
        assert result.timed_out is False


class TestUnsupportedLanguage:
    def test_raises_before_touching_docker(self):
        with pytest.raises(UnsupportedLanguageError):
            run_in_sandbox("ruby", "puts 'hi'")
