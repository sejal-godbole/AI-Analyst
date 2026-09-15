"""
Thin wrapper around an OpenAI-compatible chat completion call with full observability.

Uses the `openai` SDK client, pointed at Gemini's OpenAI-compatibility endpoint by default.
Automatically tracks latency, prompts, token usage, estimated costs, and reports to
the Observability Tracer & LangSmith.
"""
from __future__ import annotations

import time
from typing import Optional
from openai import OpenAI

from app.config import get_settings
from app.observability.tracer import tracer

_client: OpenAI | None = None


def get_llm_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return _client


def chat(
    system: str,
    user: str,
    temperature: float = 0.0,
    node_name: str = "llm_call",
    trace_id: Optional[str] = None,
) -> str:
    settings = get_settings()
    client = get_llm_client()
    start_t = time.time()
    error_msg = None
    content = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = (response.choices[0].message.content or "").strip()

        # Extract token usage
        if hasattr(response, "usage") and response.usage:
            prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
            total_tokens = getattr(response.usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        else:
            # Fallback token estimation
            prompt_tokens = max(1, (len(system) + len(user)) // 4)
            completion_tokens = max(1, len(content) // 4)
            total_tokens = prompt_tokens + completion_tokens

    except Exception as e:
        error_msg = str(e)
        raise
    finally:
        duration_ms = (time.time() - start_t) * 1000.0
        tracer.record_llm_call(
            node_name=node_name,
            model=settings.llm_model,
            system_prompt=system,
            user_prompt=user,
            response_text=content,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            error=error_msg,
            trace_id=trace_id,
        )

    return content
