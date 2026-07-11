"""API-layer tests for /execute and /health, independent of Docker.

These mock `app.main.run_in_sandbox` so they exercise request/response wiring
(status codes, field names matching CONTRACT.md §4) without needing a real
container runtime — the real, unmocked container behavior is covered by
tests/test_sandbox.py's `@requires_docker` tests instead.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.sandbox import ExecutionResult

client = TestClient(app)


def test_health_returns_up():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_execute_returns_contract_shaped_response():
    fake_result = ExecutionResult(
        exit_code=0, stdout="hello\n", stderr="", timed_out=False, duration_ms=842
    )
    with patch("app.main.run_in_sandbox", return_value=fake_result) as mocked:
        response = client.post(
            "/execute",
            json={"language": "python", "code": "print('hello')", "testCommand": None},
        )

    assert response.status_code == 200
    body = response.json()
    # Exact keys from CONTRACT.md §4.
    assert set(body.keys()) == {"exitCode", "stdout", "stderr", "timedOut", "durationMs"}
    assert body == {
        "exitCode": 0,
        "stdout": "hello\n",
        "stderr": "",
        "timedOut": False,
        "durationMs": 842,
    }
    mocked.assert_called_once()
    _, kwargs = mocked.call_args
    assert kwargs["language"] == "python"
    assert kwargs["code"] == "print('hello')"
    assert kwargs["test_command"] is None


def test_execute_missing_required_field_returns_422():
    response = client.post("/execute", json={"code": "print(1)"})

    assert response.status_code == 422


def test_execute_unsupported_language_returns_422():
    from app.sandbox import UnsupportedLanguageError

    with patch(
        "app.main.run_in_sandbox",
        side_effect=UnsupportedLanguageError("unsupported language: 'ruby'"),
    ):
        response = client.post(
            "/execute", json={"language": "ruby", "code": "puts 1", "testCommand": None}
        )

    assert response.status_code == 422


def test_execute_timed_out_flag_propagates():
    fake_result = ExecutionResult(
        exit_code=-1, stdout="", stderr="[worker] timeout", timed_out=True, duration_ms=2005
    )
    with patch("app.main.run_in_sandbox", return_value=fake_result):
        response = client.post(
            "/execute",
            json={
                "language": "python",
                "code": "import time; time.sleep(30)",
                "testCommand": None,
            },
        )

    assert response.status_code == 200
    assert response.json()["timedOut"] is True
