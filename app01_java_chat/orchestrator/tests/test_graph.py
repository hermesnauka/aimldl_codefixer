"""Real pytest tests against the actual modules (app.graph, app.llm.failover,
app.agents.router_agent) — everything mocked at the httpx/LangChain client
boundary, no real network/API keys/DB required.

Covers:
  1. The self-correction loop's conditional-edge routing (_route_after_execute).
  2. The US-04 failover threshold logic in FailoverSession, in isolation.
  3. The router agent's deterministic language detection.
"""
from __future__ import annotations

import asyncio

import pytest

from app import config
from app.graph import GraphState, _route_after_execute
from app.llm import failover as failover_module
from app.llm.failover import FailoverSession, ProviderAttemptFailed


# ---------------------------------------------------------------------------
# 1. Conditional-edge routing after `execute`
# ---------------------------------------------------------------------------


def _base_state(**overrides) -> GraphState:
    state: GraphState = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "22222222-2222-2222-2222-222222222222",
        "language": "python",
        "code": "print('hi')",
        "retry_count": 0,
        "failed": False,
    }
    state.update(overrides)
    return state


def test_route_retries_when_failed_and_below_cap():
    state = _base_state(failed=True, retry_count=0)
    assert _route_after_execute(state) == "retry"


def test_route_retries_up_to_just_below_cap():
    state = _base_state(failed=True, retry_count=config.MAX_RETRY_COUNT - 1)
    assert _route_after_execute(state) == "retry"


def test_route_finalizes_when_retry_count_at_cap():
    state = _base_state(failed=True, retry_count=config.MAX_RETRY_COUNT)
    assert _route_after_execute(state) == "finalize"


def test_route_finalizes_when_retry_count_above_cap():
    state = _base_state(failed=True, retry_count=config.MAX_RETRY_COUNT + 5)
    assert _route_after_execute(state) == "finalize"


def test_route_finalizes_on_success_regardless_of_retry_count():
    state = _base_state(failed=False, retry_count=0)
    assert _route_after_execute(state) == "finalize"

    state2 = _base_state(failed=False, retry_count=config.MAX_RETRY_COUNT)
    assert _route_after_execute(state2) == "finalize"


# ---------------------------------------------------------------------------
# 2. US-04 failover threshold logic, in isolation
# ---------------------------------------------------------------------------


class _FakeAsyncIterator:
    """Wraps a list of tokens (or an exception to raise) as an async
    generator, mimicking openrouter_client.stream_completion's shape.
    """

    def __init__(self, tokens=None, exc: Exception | None = None, delay: float = 0.0):
        self._tokens = tokens or []
        self._exc = exc
        self._delay = delay

    async def __call__(self, **kwargs):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        for token in self._tokens:
            yield token


@pytest.fixture(autouse=True)
def _reset_db_calls(monkeypatch):
    """Mock every app.db telemetry call so no real Postgres connection is
    attempted, and record calls for assertions.
    """
    calls = {"llm": [], "failover": [], "execution": []}

    async def fake_log_llm_call(**kwargs):
        calls["llm"].append(kwargs)

    async def fake_log_failover_incident(**kwargs):
        calls["failover"].append(kwargs)

    async def fake_log_code_execution(**kwargs):
        calls["execution"].append(kwargs)

    monkeypatch.setattr(failover_module.db, "log_llm_call", fake_log_llm_call)
    monkeypatch.setattr(failover_module.db, "log_failover_incident", fake_log_failover_incident)
    monkeypatch.setattr(failover_module.db, "log_code_execution", fake_log_code_execution)
    return calls


async def _drain(agen):
    return [item async for item in agen]


@pytest.mark.asyncio
async def test_below_threshold_stays_on_openrouter(monkeypatch, _reset_db_calls):
    """max_attempts=2: a single OpenRouter failure (attempt 1 of 2) must NOT
    trigger failover yet — still using openrouter, no failover event/log.
    """
    session = FailoverSession(session_id="s1", max_attempts=2, timeout_seconds=3.0)

    monkeypatch.setattr(
        failover_module.openrouter_client,
        "stream_completion",
        _FakeAsyncIterator(exc=RuntimeError("connection refused")),
    )

    events = []

    async def on_event(evt):
        events.append(evt)

    with pytest.raises(ProviderAttemptFailed):
        await _drain(
            session.stream(system_prompt="sys", user_prompt="usr", on_event=on_event)
        )

    assert session.failed_over is False
    assert session.current_provider == "openrouter/hermes-3"
    assert session.consecutive_openrouter_failures == 1
    assert events == []  # no provider_failover event yet
    assert _reset_db_calls["failover"] == []


@pytest.mark.asyncio
async def test_at_threshold_switches_to_openai_and_logs(monkeypatch, _reset_db_calls):
    """max_attempts=2: two consecutive OpenRouter failures must trigger
    failover — switched to openai, a failover event fired, and
    log_failover_incident called.
    """
    session = FailoverSession(session_id="s2", max_attempts=2, timeout_seconds=3.0)

    monkeypatch.setattr(
        failover_module.openrouter_client,
        "stream_completion",
        _FakeAsyncIterator(exc=RuntimeError("connection refused")),
    )
    monkeypatch.setattr(
        failover_module.openai_fallback_client,
        "stream_completion",
        _FakeAsyncIterator(tokens=["fallback ", "response"]),
    )

    events = []

    async def on_event(evt):
        events.append(evt)

    # Attempt 1: fails, below threshold, raises.
    with pytest.raises(ProviderAttemptFailed):
        await _drain(
            session.stream(system_prompt="sys", user_prompt="usr", on_event=on_event)
        )
    assert session.failed_over is False

    # Attempt 2: fails, reaches threshold (2/2) -> fails over to OpenAI
    # within THIS same call, so tokens should come from the fallback.
    tokens = await _drain(
        session.stream(system_prompt="sys", user_prompt="usr", on_event=on_event)
    )

    assert session.failed_over is True
    assert session.current_provider == "openai/codex"
    assert tokens == ["fallback ", "response"]

    failover_events = [e for e in events if e["type"] == "provider_failover"]
    assert len(failover_events) == 1
    assert failover_events[0]["from"] == "openrouter/hermes-3"
    assert failover_events[0]["to"] == "openai/codex"

    assert len(_reset_db_calls["failover"]) == 1
    assert _reset_db_calls["failover"][0]["from_provider"] == "openrouter/hermes-3"
    assert _reset_db_calls["failover"][0]["to_provider"] == "openai/codex"

    # KPI-02: log_llm_call once per attempt (2 failed openrouter attempts + 1 successful openai attempt)
    assert len(_reset_db_calls["llm"]) == 3


@pytest.mark.asyncio
async def test_once_failed_over_never_retries_openrouter_again(monkeypatch, _reset_db_calls):
    """Once failed_over is True, subsequent stream() calls in the SAME
    session must go straight to OpenAI, never touching OpenRouter again.
    """
    session = FailoverSession(session_id="s3", max_attempts=2, timeout_seconds=3.0)
    session.failed_over = True
    session.current_provider = "openai/codex"

    openrouter_calls = []

    def tracking_openrouter(**kwargs):
        openrouter_calls.append(kwargs)
        raise AssertionError("OpenRouter must never be called again after failover")

    monkeypatch.setattr(failover_module.openrouter_client, "stream_completion", tracking_openrouter)
    monkeypatch.setattr(
        failover_module.openai_fallback_client,
        "stream_completion",
        _FakeAsyncIterator(tokens=["ok"]),
    )

    tokens = await _drain(session.stream(system_prompt="sys", user_prompt="usr"))
    assert tokens == ["ok"]
    assert openrouter_calls == []


@pytest.mark.asyncio
async def test_single_call_exceeding_timeout_is_immediate_failover(monkeypatch, _reset_db_calls):
    """A single OpenRouter call exceeding LLM_FAILOVER_TIMEOUT_SECONDS must
    itself reach the failed-over state within that same analyze call, per
    US-04 ("timeout t > 3.0s"), even with max_attempts=2 — i.e. a slow call
    counts toward exhausting attempts immediately, and with max_attempts=1
    it should fail over on the very first call.
    """
    session = FailoverSession(session_id="s4", max_attempts=1, timeout_seconds=0.05)

    monkeypatch.setattr(
        failover_module.openrouter_client,
        "stream_completion",
        _FakeAsyncIterator(tokens=["too", "slow"], delay=1.0),
    )
    monkeypatch.setattr(
        failover_module.openai_fallback_client,
        "stream_completion",
        _FakeAsyncIterator(tokens=["fallback"]),
    )

    events = []

    async def on_event(evt):
        events.append(evt)

    tokens = await _drain(
        session.stream(system_prompt="sys", user_prompt="usr", on_event=on_event)
    )

    assert session.failed_over is True
    assert tokens == ["fallback"]
    failover_events = [e for e in events if e["type"] == "provider_failover"]
    assert len(failover_events) == 1
    assert "timeout" in failover_events[0]["reason"].lower()


# ---------------------------------------------------------------------------
# 3. Router agent language detection (deterministic heuristics)
# ---------------------------------------------------------------------------

from app.agents import router_agent  # noqa: E402


def test_router_passes_through_explicit_hint():
    assert (
        router_agent.detect_language(code="whatever", error_log=None, language_hint="java")
        == "java"
    )


def test_router_detects_python_from_code():
    code = "def foo():\n    import sys\n    print('hi')\n"
    assert router_agent.detect_language(code=code, error_log=None, language_hint=None) == "python"


def test_router_detects_java_from_code_and_error():
    code = "public class Main {\n  public static void main(String[] args) {}\n}"
    error_log = 'Exception in thread "main" java.lang.NullPointerException\n\tat Main.main(Main.java:3)'
    assert router_agent.detect_language(code=code, error_log=error_log, language_hint=None) == "java"


def test_router_detects_javascript_from_code_and_error():
    code = "const add = (a, b) => { return a + b; };\nconsole.log(add(1,2));"
    error_log = "TypeError: add is not a function\n    at Object.<anonymous> (/app/index.js:3:1)"
    assert (
        router_agent.detect_language(code=code, error_log=error_log, language_hint=None)
        == "javascript"
    )


def test_router_defaults_to_python_when_ambiguous():
    assert router_agent.detect_language(code="", error_log="", language_hint=None) == "python"


def test_router_ignores_invalid_hint_and_falls_back_to_heuristics():
    code = "function hello() { console.log('hi'); }"
    assert (
        router_agent.detect_language(code=code, error_log=None, language_hint="not-a-real-language")
        == "javascript"
    )
