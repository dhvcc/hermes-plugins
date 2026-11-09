"""The only Hermes internals the router reads, imported lazily so unit tests run without Hermes."""
from __future__ import annotations

from typing import Any, Optional

DECISIONS_TIMEOUT_S = 2.0


def price(model: str, prompt_tokens: int, cached_tokens: int, output_tokens: int) -> Optional[float]:
    """API-equivalent USD from Hermes's official OpenAI snapshot; uncached prompt is billed as a cache write."""
    from agent.usage_pricing import CanonicalUsage, estimate_usage_cost

    cached = max(0, min(cached_tokens, prompt_tokens))
    usage = CanonicalUsage(cache_read_tokens=cached, cache_write_tokens=prompt_tokens - cached,
                           output_tokens=output_tokens)
    result = estimate_usage_cost(model, usage, provider="openai")
    if result.status != "estimated" or result.amount_usd is None:
        return None
    return float(result.amount_usd)


def catalog() -> frozenset[str]:
    """Account-scoped Codex model ids from Hermes's cache; empty when unknown."""
    from hermes_cli.models import cached_provider_model_ids

    return frozenset(cached_provider_model_ids("openai-codex", non_blocking=True) or ())


def estimate_tokens(messages: list, tools: Optional[list]) -> int:
    from agent.model_metadata import estimate_request_tokens_rough

    return estimate_request_tokens_rough(messages, tools=tools)


def clamp_effort(model: str, effort: str) -> Optional[str]:
    from agent.reasoning_effort import clamp_effort as clamp, codex_supported_efforts

    return clamp(effort, codex_supported_efforts(model))


def context_window(model: str) -> int:
    from agent.model_metadata import get_model_context_length

    return get_model_context_length(model, provider="openai-codex")


def decisions_tier(history: Any, user_message: Any, session_id: str) -> Optional[tuple[str, float]]:
    """Decisions API tier with the profile's ``OPENAI_API_KEY``; None when no key is set."""
    from agent.secret_scope import get_secret
    from .decisions import classify

    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return None
    return classify(history, user_message, api_key=api_key, session_id=session_id, timeout=DECISIONS_TIMEOUT_S)
