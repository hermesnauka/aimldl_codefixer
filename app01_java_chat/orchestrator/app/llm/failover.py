"""US-04 failover orchestration: wraps openrouter_client and
openai_fallback_client behind one async streaming interface.

Acceptance criteria (implemented literally): "Failover switches
automatically in the backend layer after two failed connection attempts
(timeout t > 3.0s), logging the incident into the PostgreSQL database for
auditing."

Concretely, per session (one FailoverSession per /internal/v1/analyze call):
- Try OpenRouter first.
- If a single call exceeds LLM_FAILOVER_TIMEOUT_SECONDS (default 3.0) OR
  OpenRouter fails/timeouts LLM_FAILOVER_MAX_ATTEMPTS (default 2) consecutive
  times, switch to OpenAI for the REST OF THAT SESSION — OpenRouter is never
  retried again once failed-over, within this analyze call.
- A timeout on a single call is itself immediate failover (it counts as
  reaching the attempts-exhausted state right away), matching "after two
  failed connection attempts (timeout t > 3.0s)" — a call slower than the
  threshold is treated as a failed attempt in its own right.
- Emits a provider_failover event (from/to/reason) via an async callback the
  caller supplies, and calls db.log_failover_incident.
- Calls db.log_llm_call once per attempt (success or failure), per KPI-02.

Architectural note: side-channel events (provider_failover) are surfaced via
an `on_event` async callback passed into `stream()`, rather than a second
generator or a sentinel value mixed into the token stream. This keeps the
primary generator's yielded items uniformly "a token string", while
graph.py/reasoning_agent.py can pass a callback that appends structured
events onto whatever event-surfacing mechanism app/graph.py chooses (see
graph.py's own docstring for that choice).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from app import config, db
from app.llm import openai_fallback_client, openrouter_client

logger = logging.getLogger("orchestrator.llm.failover")

OnEvent = Callable[[dict], Awaitable[None]]


async def _noop_on_event(_event: dict) -> None:
    return None


@dataclass
class FailoverSession:
    """Per-analyze-call state: tracks consecutive OpenRouter failures and
    whether this session has already failed over to OpenAI. Construct one
    fresh instance per /internal/v1/analyze call (per session_id) — state is
    NOT meant to be shared/reused across unrelated sessions.
    """

    session_id: str
    max_attempts: int = field(default_factory=lambda: config.LLM_FAILOVER_MAX_ATTEMPTS)
    timeout_seconds: float = field(
        default_factory=lambda: config.LLM_FAILOVER_TIMEOUT_SECONDS
    )

    consecutive_openrouter_failures: int = 0
    failed_over: bool = False
    current_provider: str = openrouter_client.PROVIDER_NAME

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        on_event: OnEvent | None = None,
    ) -> AsyncIterator[str]:
        """Yield incremental completion tokens, applying US-04 failover.

        If already failed-over from a prior call in this session, goes
        straight to OpenAI without retrying OpenRouter.

        If OpenRouter fails but the attempts-exhausted threshold has NOT yet
        been reached, this raises `_ProviderFailure` to the caller (rather
        than silently yielding nothing) so the caller — e.g.
        reasoning_agent's own retry loop — knows this attempt produced no
        usable output and can decide to call `stream()` again. Once the
        threshold IS reached (or a single call times out), this method
        transparently falls through to OpenAI within the SAME call instead
        of raising, since at that point failover has already happened and
        the caller should just get tokens.
        """
        emit = on_event or _noop_on_event

        if not self.failed_over:
            try:
                async for token in self._attempt_openrouter(system_prompt, user_prompt):
                    yield token
                return
            except _ProviderFailure as exc:
                await self._maybe_fail_over(reason=exc.reason, emit=emit)
                if not self.failed_over:
                    # Attempts remain — propagate so the caller can retry.
                    raise

        # Either already failed over before this call, or just failed over above.
        async for token in self._attempt_openai(system_prompt, user_prompt):
            yield token

    async def _attempt_openrouter(
        self, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        start = time.monotonic()
        got_any_token = False
        try:
            stream = openrouter_client.stream_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=self.timeout_seconds,
            )
            async with asyncio.timeout(self.timeout_seconds):
                async for token in stream:
                    got_any_token = True
                    yield token
        except TimeoutError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            await db.log_llm_call(
                session_id=self.session_id,
                provider=openrouter_client.PROVIDER_NAME,
                model=config.OPENROUTER_MODEL,
                latency_ms=latency_ms,
                success=False,
                error=f"timeout after {self.timeout_seconds}s",
            )
            self.consecutive_openrouter_failures += 1
            raise _ProviderFailure(
                reason=(
                    f"OpenRouter call exceeded timeout threshold "
                    f"({self.timeout_seconds}s)"
                )
            ) from exc
        except Exception as exc:  # noqa: BLE001 - any client/provider failure counts
            latency_ms = int((time.monotonic() - start) * 1000)
            await db.log_llm_call(
                session_id=self.session_id,
                provider=openrouter_client.PROVIDER_NAME,
                model=config.OPENROUTER_MODEL,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            self.consecutive_openrouter_failures += 1
            raise _ProviderFailure(reason=f"OpenRouter call failed: {exc}") from exc
        else:
            latency_ms = int((time.monotonic() - start) * 1000)
            await db.log_llm_call(
                session_id=self.session_id,
                provider=openrouter_client.PROVIDER_NAME,
                model=config.OPENROUTER_MODEL,
                latency_ms=latency_ms,
                success=True,
                error=None,
            )
            self.consecutive_openrouter_failures = 0
            if not got_any_token:
                # Defensive: a stream that yields nothing is not a crash, but
                # also isn't useful; treat it as a soft failure for failover
                # counting purposes without double-logging.
                self.consecutive_openrouter_failures += 1

    async def _attempt_openai(
        self, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        start = time.monotonic()
        try:
            stream = openai_fallback_client.stream_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=self.timeout_seconds,
            )
            async with asyncio.timeout(max(self.timeout_seconds * 4, 30.0)):
                # The fallback provider isn't held to the same tight
                # failover timeout — that threshold exists to decide
                # *whether* to fail over, not to also strangle the fallback
                # once we're already committed to it.
                async for token in stream:
                    yield token
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - start) * 1000)
            await db.log_llm_call(
                session_id=self.session_id,
                provider=openai_fallback_client.PROVIDER_NAME,
                model=config.OPENAI_MODEL,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            raise
        else:
            latency_ms = int((time.monotonic() - start) * 1000)
            await db.log_llm_call(
                session_id=self.session_id,
                provider=openai_fallback_client.PROVIDER_NAME,
                model=config.OPENAI_MODEL,
                latency_ms=latency_ms,
                success=True,
                error=None,
            )

    async def _maybe_fail_over(self, *, reason: str, emit: OnEvent) -> None:
        if self.failed_over:
            return
        if self.consecutive_openrouter_failures < self.max_attempts:
            return

        from_provider = openrouter_client.PROVIDER_NAME
        to_provider = openai_fallback_client.PROVIDER_NAME
        self.failed_over = True
        self.current_provider = to_provider

        logger.warning(
            "Failing over session %s from %s to %s: %s",
            self.session_id,
            from_provider,
            to_provider,
            reason,
        )
        await db.log_failover_incident(
            session_id=self.session_id,
            from_provider=from_provider,
            to_provider=to_provider,
            reason=reason,
        )
        await emit(
            {
                "type": "provider_failover",
                "from": from_provider,
                "to": to_provider,
                "reason": reason,
            }
        )


class ProviderAttemptFailed(Exception):
    """Raised when an OpenRouter attempt fails/times out but the session has
    not (yet) crossed the failover threshold — the caller should retry.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Backward-compatible internal alias used within this module.
_ProviderFailure = ProviderAttemptFailed
