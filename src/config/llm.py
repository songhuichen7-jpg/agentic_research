"""LLM client factories using OpenRouter, with retry and token tracking."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_openai import ChatOpenAI

from src.config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, UTILITY_MODEL, WRITER_MODEL

logger = logging.getLogger(__name__)


# ── Token usage tracking ──────────────────────────────────────


@dataclass
class _TokenBucket:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
                "calls": self.calls,
            }

    def reset(self) -> None:
        with self._lock:
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.calls = 0


_usage: dict[str, _TokenBucket] = {
    "writer": _TokenBucket(),
    "utility": _TokenBucket(),
}


def get_token_usage() -> dict[str, dict[str, int]]:
    """Return cumulative token usage for the current session."""
    return {k: v.snapshot() for k, v in _usage.items()}


def reset_token_usage() -> None:
    for v in _usage.values():
        v.reset()


# ── Retry wrapper ─────────────────────────────────────────────

_MAX_RETRIES = 3
_BASE_DELAY = 2.0


class _RetryLLM:
    """Wraps a ChatOpenAI instance with automatic retry + token tracking."""

    def __init__(self, llm: ChatOpenAI, role: str):
        self._llm = llm
        self._role = role

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._llm.invoke(*args, **kwargs)
                # Track tokens from response metadata
                usage_meta = getattr(resp, "usage_metadata", None) or {}
                if isinstance(usage_meta, dict):
                    _usage[self._role].add(
                        usage_meta.get("input_tokens", 0),
                        usage_meta.get("output_tokens", 0),
                    )
                return resp
            except Exception as e:
                last_err = e
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM call failed (attempt %d/%d, role=%s): %s — retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        self._role,
                        e,
                        delay,
                    )
                    time.sleep(delay)
        logger.error("LLM call exhausted retries (role=%s): %s", self._role, last_err)
        raise last_err  # type: ignore[misc]

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        """Stream tokens from the LLM. Yields AIMessageChunk objects.

        Usage::

            for chunk in llm.stream(prompt):
                print(chunk.content, end="")
        """
        # LangChain ChatOpenAI.stream() is a generator — no retry at this level
        # (the caller can handle errors per-chunk or wrap in their own retry).
        return self._llm.stream(*args, **kwargs)


# ── Factory functions ─────────────────────────────────────────


def get_writer_llm(temperature: float = 0.3, **kwargs) -> _RetryLLM:
    """Strong model for planning, writing, and summarisation — with retry."""
    llm = ChatOpenAI(
        model=WRITER_MODEL,
        temperature=temperature,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        **kwargs,
    )
    return _RetryLLM(llm, "writer")


def get_utility_llm(temperature: float = 0.0, **kwargs) -> _RetryLLM:
    """Fast / cheap model for routing, classification, extraction — with retry."""
    llm = ChatOpenAI(
        model=UTILITY_MODEL,
        temperature=temperature,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        **kwargs,
    )
    return _RetryLLM(llm, "utility")
