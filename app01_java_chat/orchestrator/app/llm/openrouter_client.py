"""LangChain-based streaming client for the primary provider: Hermes 3 via
OpenRouter. OpenRouter exposes an OpenAI-compatible Chat Completions API, so
this is a real `langchain_openai.ChatOpenAI` instance pointed at OpenRouter's
base_url — not a hand-rolled HTTP client, not a stub.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app import config

PROVIDER_NAME = "openrouter/hermes-3"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterConfigError(RuntimeError):
    """Raised when a call is attempted with no OPENROUTER_API_KEY configured."""


def _build_client(timeout: float) -> ChatOpenAI:
    if not config.OPENROUTER_API_KEY:
        raise OpenRouterConfigError(
            "OPENROUTER_API_KEY is not set — cannot call OpenRouter. "
            "Set it in .env or the environment before making LLM calls."
        )
    return ChatOpenAI(
        model=config.OPENROUTER_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        streaming=True,
        timeout=timeout,
        max_retries=0,  # failover.py owns retry/attempt-counting logic, not the client
    )


async def stream_completion(
    *, system_prompt: str, user_prompt: str, timeout: float
) -> AsyncIterator[str]:
    """Stream a chat completion from Hermes 3 via OpenRouter.

    Yields incremental string tokens as they arrive (US-02: reasoning tokens
    must be emitted incrementally, not as one blob). Raises on failure/timeout
    so the caller (app/llm/failover.py) can apply the US-04 threshold logic.
    """
    client = _build_client(timeout)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    async for chunk in client.astream(messages):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            content = chunk.content
            # ChatOpenAI content is normally a str; be defensive about the
            # occasional list-of-parts shape some providers/streaming modes use.
            if isinstance(content, str):
                yield content
            else:
                for part in content:
                    if isinstance(part, str):
                        yield part
                    elif isinstance(part, dict) and "text" in part:
                        yield part["text"]
