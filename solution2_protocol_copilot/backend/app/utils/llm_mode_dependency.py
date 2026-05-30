"""
Per-request LLM mode resolution.

A FastAPI dependency that picks the effective LLMMode for a single request:
1. The X-LLM-Mode header (case-insensitive: mock | fake | cached | live)
2. Falls back to the env-driven default in settings.llm_mode

The header lets the frontend's mode dropdown switch behavior at runtime without
a backend restart. Invalid header values silently fall back to the default —
a malformed request header shouldn't 500 the API.
"""
from typing import Optional
from fastapi import Header

from app.config import settings, LLMMode
from app.utils.llm_client import (
    LLMClient, MockLLMClient, FakeLLMClient, CachedLLMClient, LiveLLMClient,
)


def resolve_llm_mode(x_llm_mode: Optional[str] = Header(default=None)) -> LLMMode:
    """Resolve the effective LLM mode for this request."""
    if x_llm_mode:
        try:
            return LLMMode(x_llm_mode.strip().lower())
        except ValueError:
            pass  # invalid header value → fall through to default
    return settings.llm_mode


def get_llm_client_for_mode(mode: LLMMode) -> LLMClient:
    """Construct a fresh client for the given mode (no shared state)."""
    return {
        LLMMode.MOCK: MockLLMClient,
        LLMMode.FAKE: FakeLLMClient,
        LLMMode.CACHED: CachedLLMClient,
        LLMMode.LIVE: LiveLLMClient,
    }[mode]()
