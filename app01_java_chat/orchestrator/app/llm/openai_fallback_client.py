"""LangChain-based streaming client for the fallback provider: OpenAI
(Codex/ChatGPT family, e.g. gpt-4o) called directly against OpenAI's API.
Same shape as openrouter_client.py by design, so failover.py can swap
between the two behind one interface.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app import config

PROVIDER_NAME = "openai/codex"


class OpenAIConfigError(RuntimeError):
    """Raised when a call is attempted with no OPENAI_API_KEY configured."""


def _build_client(timeout: float) -> ChatOpenAI:
    if not config.OPENAI_API_KEY:
        raise OpenAIConfigError(
            "OPENAI_API_KEY is not set — cannot call the OpenAI fallback. "
            "Set it in .env or the environment before making LLM calls."
        )
    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        api_key=config.OPENAI_API_KEY,
        streaming=True,
        timeout=timeout,
        max_retries=0,  # failover.py owns retry/attempt-counting logic, not the client
    )


async def stream_completion(
    *, system_prompt: str, user_prompt: str, timeout: float
) -> AsyncIterator[str]:
    """Stream a chat completion from OpenAI. Same contract as
    openrouter_client.stream_completion: yields incremental string tokens,
    raises on failure/timeout.
    """
    client = _build_client(timeout)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    async for chunk in client.astream(messages):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            content = chunk.content
            if isinstance(content, str):
                yield content
            else:
                for part in content:
                    if isinstance(part, str):
                        yield part
                    elif isinstance(part, dict) and "text" in part:
                        yield part["text"]
