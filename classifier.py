"""Deterministic per-turn task tier. Local only: no network, no prompt logging."""
from __future__ import annotations

import re
from typing import Any

LIGHT, STANDARD, HEAVY = "light", "standard", "heavy"
TIERS = (LIGHT, STANDARD, HEAVY)

_HEAVY = re.compile(
    r"```|traceback \(most recent call last\)|^\s+at \S+\(\S*:\d+\)"
    r"|\b(?:debug\w*|refactor\w*|implement\w*|architect\w*|security|vulnerab\w*|audit\w*|exploit\w*"
    r"|prove|proof|derive|optimi[sz]\w*|algorithm\w*|complexity|migrat\w*|race condition|deadlock"
    r"|root cause|investigat\w*|trade-?offs?|step[- ]by[- ]step|threat model|regression|concurren\w*)\b"
    r"|отлад|дебаг|рефактор|реализ|имплемент|архитектур|спроектир|проектирова|безопасн|уязвим|аудит"
    r"|докаж|доказа|оптимиз|алгоритм|сложност|миграц|гонк[аиу] |дедлок|взаимоблок|первопричин"
    r"|разберись|исследу|исследован|стратеги|компромисс|пошагов|регресс|многопоточ",
    re.IGNORECASE | re.MULTILINE,
)
_STANDARD = re.compile(
    r"\b(?:why|how|explain|compare|write|draft|summari[sz]e|plan|review|analy[sz]e|translate|rewrite|list|code)\b"
    r"|почему|зачем|\bкак\b|объясни|сравни|напиши|составь|подготовь|резюм|суммир|\bплан|проверь|переведи"
    r"|перепиши|список|проанализ|код",
    re.IGNORECASE,
)
_CONTINUATION = re.compile(
    r"^(?:ok(?:ay)?|yes|yep|sure|go(?: on| ahead)?|continue|proceed|do it|next|again|retry|try again|fix it"
    r"|ок(?:ей)?|да|ага|давай|го|продолж\w*|дальше|делай|сделай|ещ[её]|повтори|исправь|поехали|согласен|верно)"
    r"(?:\W|$)",
    re.IGNORECASE,
)


def classify(text: str, previous: str | None = None) -> str:
    """Tier of the new user turn; short follow-ups such as "continue" keep the previous tier."""
    text = text.strip()
    words = len(text.split())
    if not text:
        return previous or STANDARD
    if previous and words <= 6 and _CONTINUATION.match(text):
        return previous
    if len(text) > 1500 or words > 250 or _HEAVY.search(text):
        return HEAVY
    if words <= 20 and len(text) <= 160 and not _STANDARD.search(text):
        return LIGHT
    return STANDARD


def message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return message_text(message.get("content"))
    if isinstance(message, list):
        return " ".join(part["text"] for part in message if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""
