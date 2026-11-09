"""Price- and cache-aware choice between the light and heavy model for a non-heavy turn.

Costs are API-equivalent USD from Hermes's official price snapshot, used as a proxy for
subscription quota. The horizon is this turn plus the next one:

    cost(X) = turn(X now) + p_heavy * turn(heavy next | X) + (1 - p_heavy) * turn(light next | X)

A model's prompt cache counts as warm while its last call is younger than the TTL. Leaving
the heavy model lets its cache age; coming back after the TTL pays the whole prefix again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# price(model, prompt_tokens, cached_tokens, output_tokens) -> USD or None when unknown
Price = Callable[[str, int, int, int], Optional[float]]

ALPHA = 0.4
DEFAULT_OUTPUT_TOKENS = 1500.0


def ewma(current: float, sample: float) -> float:
    return (1 - ALPHA) * current + ALPHA * sample


@dataclass(frozen=True)
class CacheMark:
    prefix_tokens: int
    at: float


@dataclass
class Stats:
    p_heavy: float = 0.3
    gap_s: float = 60.0
    turn_s: float = 20.0
    calls_per_turn: float = 1.0
    output_tokens: dict[str, float] = field(default_factory=dict)

    def observe_tier(self, heavy: bool) -> None:
        self.p_heavy = ewma(self.p_heavy, 1.0 if heavy else 0.0)

    def close_turn(self, *, turn_s: float, gap_s: float, calls: int) -> None:
        self.turn_s = ewma(self.turn_s, max(0.0, turn_s))
        self.gap_s = ewma(self.gap_s, max(0.0, gap_s))
        if calls:
            self.calls_per_turn = ewma(self.calls_per_turn, float(calls))

    def observe_output(self, model: str, tokens: int) -> None:
        self.output_tokens[model] = ewma(self.output_tokens.get(model, DEFAULT_OUTPUT_TOKENS), float(tokens))

    def expected_output(self, model: str) -> int:
        return round(self.output_tokens.get(model, DEFAULT_OUTPUT_TOKENS))


@dataclass(frozen=True)
class Choice:
    model: str
    reason: str
    costs: dict[str, float] = field(default_factory=dict)


def choose(light: str, heavy: str, *, prompt_tokens: int, now: float, cache: dict[str, CacheMark],
           stats: Stats, ttl: float, price: Price) -> Choice:
    """Cheapest expected model for a turn the light model can handle. Ties go to the light model."""
    p = max(0, prompt_tokens)
    continuous = stats.turn_s + stats.gap_s < ttl
    next_at = now + stats.turn_s + stats.gap_s

    def warm(model: str, at: float) -> int:
        mark = cache.get(model)
        return min(mark.prefix_tokens, p) if mark and at - mark.at < ttl else 0

    def turn(model: str, cached: int) -> Optional[float]:
        output = stats.expected_output(model)
        first, rest = price(model, p, cached, output), price(model, p, p, output)
        if first is None or rest is None:
            return None
        return first + max(0.0, stats.calls_per_turn - 1) * rest

    def expected(option: str) -> Optional[float]:
        now_cost = turn(option, warm(option, now))
        heavy_next = turn(heavy, p if option == heavy and continuous else warm(heavy, next_at))
        light_next = turn(light, p if option == light and continuous else warm(light, next_at))
        if now_cost is None or heavy_next is None or light_next is None:
            return None
        return now_cost + stats.p_heavy * heavy_next + (1 - stats.p_heavy) * light_next

    light_cost, heavy_cost = expected(light), expected(heavy)
    if light_cost is None or heavy_cost is None:
        return Choice(light, "pricing unavailable")
    costs = {light: light_cost, heavy: heavy_cost}
    if heavy_cost < light_cost:
        return Choice(heavy, f"keeps {heavy} cache warm, saves ${light_cost - heavy_cost:.4f}", costs)
    return Choice(light, f"cheaper by ${heavy_cost - light_cost:.4f}", costs)
