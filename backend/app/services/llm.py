"""Shared LLM utilities.

Centralizes ChatOpenAI construction and structured-output calls so workflows
and services don't each duplicate setup or fallback handling.

All public functions return `None` (or a sentinel) when the LLM is unavailable
— callers must provide a deterministic fallback.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def _get_llm():
    """Return a cached ChatOpenAI instance, or None if no key is configured."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
    except Exception:
        return None


def llm_available() -> bool:
    return _get_llm() is not None


def llm_client():
    """Return the shared ChatOpenAI client, or None when not configured."""
    return _get_llm()


def llm_text(prompt: str) -> Optional[str]:
    """Call the LLM with a plain prompt; return text or None on failure."""
    llm = _get_llm()
    if llm is None:
        return None
    try:
        from langchain_core.messages import HumanMessage

        result = llm.invoke([HumanMessage(content=prompt)])
        text = (result.content or "").strip()
        return text or None
    except Exception:
        return None


def llm_structured(prompt: str, schema: Type[T]) -> Optional[T]:
    """Call the LLM with structured output bound to a Pydantic schema."""
    llm = _get_llm()
    if llm is None:
        return None
    try:
        from langchain_core.messages import HumanMessage

        structured = llm.with_structured_output(schema)
        result = structured.invoke([HumanMessage(content=prompt)])
        if isinstance(result, schema):
            return result
        # Some providers return dicts; coerce.
        return schema.model_validate(result)
    except Exception:
        return None
