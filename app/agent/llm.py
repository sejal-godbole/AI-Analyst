"""
Thin wrapper around an OpenAI-compatible chat completion call.

Uses the `openai` SDK client, but pointed at Gemini's OpenAI-compatibility
endpoint by default (see app/config.py). This works because Gemini exposes
a `/v1beta/openai/` base URL that speaks the same request/response shape as
OpenAI's /chat/completions — no code change needed to switch providers,
only LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in .env.
"""
from __future__ import annotations

from openai import OpenAI

from app.config import get_settings

_client: OpenAI | None = None


def get_llm_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return _client


def chat(system: str, user: str, temperature: float = 0.0) -> str:
    settings = get_settings()
    client = get_llm_client()
    response = client.chat.completions.create(
        model=settings.llm_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()
