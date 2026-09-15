"""
Token pricing and cost estimation for LLM observability.
Calculates prompt, completion, and total estimated USD cost for model runs.
"""
from __future__ import annotations

# Pricing per million tokens (USD)
# [Prompt Price / 1M, Completion Price / 1M]
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}

DEFAULT_PRICING_PER_1M = (0.10, 0.40)


def estimate_llm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Returns estimated cost in USD based on model name and token counts.
    """
    matched_pricing = None
    for key, pricing in MODEL_PRICING_PER_1M.items():
        if key in model_name.lower():
            matched_pricing = pricing
            break

    if not matched_pricing:
        matched_pricing = DEFAULT_PRICING_PER_1M

    prompt_price_per_token = matched_pricing[0] / 1_000_000
    completion_price_per_token = matched_pricing[1] / 1_000_000

    cost = (prompt_tokens * prompt_price_per_token) + (completion_tokens * completion_price_per_token)
    return round(cost, 8)
