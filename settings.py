"""Settings from ``plugins.entries.hermes-smart-router.settings`` in the profile config."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Callable

MODES = ("route", "shadow")
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Settings:
    mode: str = "route"
    light_model: str = "gpt-6-luna"
    heavy_model: str = "gpt-6.1-sol"
    light_effort: str = "medium"
    standard_effort: str = "high"
    skip_platforms: tuple[str, ...] = ("cron",)
    cache_ttl_seconds: float = 300.0

    @classmethod
    def load(cls, get: Callable[[str, Any], Any]) -> "Settings":
        """Raises ValueError on an invalid value; the caller then leaves Hermes native."""
        defaults = cls()
        raw = {f.name: get(f.name, getattr(defaults, f.name)) for f in fields(cls)}
        settings = cls(
            mode=_choice(raw["mode"], MODES, "mode"),
            light_model=_text(raw["light_model"], "light_model"),
            heavy_model=_text(raw["heavy_model"], "heavy_model"),
            light_effort=_choice(raw["light_effort"], EFFORTS, "light_effort"),
            standard_effort=_choice(raw["standard_effort"], EFFORTS, "standard_effort"),
            skip_platforms=_texts(raw["skip_platforms"], "skip_platforms"),
            cache_ttl_seconds=_number(raw["cache_ttl_seconds"], 0, 86_400, "cache_ttl_seconds"),
        )
        if settings.light_model == settings.heavy_model:
            raise ValueError("light_model and heavy_model must differ")
        return settings

    @property
    def models(self) -> tuple[str, str]:
        return self.light_model, self.heavy_model


def _choice(value: Any, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _texts(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return tuple(value)


def _number(value: Any, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{name} must be a number in [{low}, {high}]")
    return float(value)
