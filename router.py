"""Session state, Hermes hook handlers and the per-turn routing plan.

One decision per user turn, pinned for every API call of that turn (tool loops never switch
model mid-turn). Any error on a routed call returns the rest of the turn to native Hermes;
Hermes alone retries, backs off and falls back.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import functools
import logging
import threading
import time
from typing import Any, Callable, Optional

RemoteTier = Callable[[Any, Any, str], Optional[tuple[str, float]]]

from . import hermes_api
from .classifier import HEAVY, LIGHT, TIERS, classify, message_text
from .policy import CacheMark, Price, Stats, choose
from .settings import EFFORTS, Settings

log = logging.getLogger("hermes_smart_router")

MAX_SESSIONS = 256
SESSION_IDLE_S = 24 * 3600.0
CATALOG_TTL_S = 600.0
UNAVAILABLE_BLOCK_S = 3600.0
EXHAUSTED_BLOCK_S = 900.0
REMOTE_COOLDOWN_S = 300.0
_UNAVAILABLE = ("model not found", "model_not_found", "unknown model", "unsupported model", "does not exist",
                "model is not supported", "model is not available", "model unavailable", "do not have access")
_EXHAUSTED = ("exhausted", "usage limit", "quota", "rate limit", "too many requests")
_TEXT_PARTS = frozenset({"text", "input_text", "output_text"})


def never_raise(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.debug("smart-router: %s failed; Hermes stays native", fn.__name__, exc_info=True)
            return None
    return wrapper


@dataclass
class Pin:
    turn_id: str
    model: str
    effort: Optional[str]
    applied: bool
    suspended: bool = False


@dataclass
class Session:
    touched: float = 0.0
    turn_id: str = ""
    tier: Optional[str] = None
    tier_source: str = "local"
    turn_started: float = 0.0
    last_api_end: float = 0.0
    calls: int = 0
    pin: Optional[Pin] = None
    stats: Stats = field(default_factory=Stats)
    cache: dict[str, CacheMark] = field(default_factory=dict)


class Router:
    def __init__(self, settings: Settings, *, price: Price = hermes_api.price,
                 catalog: Callable[[], frozenset[str]] = hermes_api.catalog,
                 estimate_tokens: Callable[[list, Optional[list]], int] = hermes_api.estimate_tokens,
                 clamp_effort: Callable[[str, str], Optional[str]] = hermes_api.clamp_effort,
                 remote_tier: Optional[RemoteTier] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self._price = price
        self._catalog = catalog
        self._estimate_tokens = estimate_tokens
        self._clamp_effort = clamp_effort
        self._remote_tier = remote_tier
        self._remote_down_until = float("-inf")
        self._clock = clock
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._blocked: dict[str, float] = {}
        self._known_models: tuple[float, frozenset[str]] = (float("-inf"), frozenset())
        self._lock = threading.RLock()

    # Hermes hooks -------------------------------------------------------------------------

    @never_raise
    def on_turn(self, *, session_id: str = "", turn_id: str = "", user_message: Any = None, model: str = "",
                platform: str = "", parent_session_id: str = "", conversation_history: Any = None,
                **_: Any) -> None:
        """``pre_llm_call``: classify once per user turn. Never injects context."""
        if not (session_id and turn_id) or parent_session_id or model not in self.settings.models:
            return None
        if platform in self.settings.skip_platforms:
            return None
        with self._lock:
            session = self._session(session_id, self._clock())
            if session.turn_id == turn_id:
                return None
            previous = session.tier
        tier, source = classify(message_text(user_message), previous), "local"
        remote = self._classify_remotely(conversation_history, user_message, session_id)
        if remote:
            source = f"local {tier}, decisions {remote[0]} p_heavy={remote[1]:.2f}"
            tier = max(tier, remote[0], key=TIERS.index)
        now = self._clock()
        with self._lock:
            session = self._session(session_id, now)
            if session.turn_id == turn_id:
                return None
            if session.turn_started and session.last_api_end >= session.turn_started:
                session.stats.close_turn(turn_s=session.last_api_end - session.turn_started,
                                         gap_s=now - session.last_api_end, calls=session.calls)
            session.stats.observe_tier(tier == HEAVY)
            session.turn_id, session.tier, session.tier_source, session.turn_started = turn_id, tier, source, now
            session.calls, session.pin = 0, None
        return None

    @never_raise
    def on_api_success(self, *, session_id: str = "", turn_id: str = "", model: str = "",
                       response_model: Any = None, usage: Any = None, **_: Any) -> None:
        """``post_api_request``: record which model's cache now holds the prompt."""
        now = self._clock()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            served = self._served_model(session, model, response_model)
            if served is None:
                return
            usage = usage if isinstance(usage, dict) else {}
            prompt, output = int(usage.get("prompt_tokens") or 0), int(usage.get("output_tokens") or 0)
            if prompt:
                session.cache[served] = CacheMark(prompt, now)
            if output:
                session.stats.observe_output(served, output)
            if turn_id == session.turn_id:
                session.calls += 1
                session.last_api_end = now

    @never_raise
    def on_api_error(self, *, session_id: str = "", model: str = "", status_code: Any = None,
                     error: Any = None, request: Any = None, **_: Any) -> None:
        """``api_request_error``: hand the turn back to Hermes; park a model that is gone or exhausted."""
        with self._lock:
            session = self._sessions.get(session_id)
            pin = session.pin if session else None
            if pin is None or not pin.applied or pin.suspended or pin.turn_id != session.turn_id:
                return
            wire_model = request.get("model") if isinstance(request, dict) else None
            if wire_model and wire_model != pin.model:
                return
            pin.suspended = True
            if pin.model == model:
                return
            message = str(error.get("message") or "") if isinstance(error, dict) else ""
            block = _block_seconds(status_code, message)
            if block:
                self._blocked[pin.model] = self._clock() + block
                log.warning("smart-router: %s unavailable (HTTP %s); not routing to it for %d min",
                            pin.model, status_code, block // 60)

    # Transport ----------------------------------------------------------------------------

    def plan(self, model: str, messages: list, tools: Optional[list], params: dict) -> Optional[tuple[str, dict]]:
        """(model, reasoning_config) for this request, or None for the native request."""
        if not self._eligible(model, messages, params):
            return None
        session_id = str(params.get("session_id") or "")
        requested = dict(params.get("reasoning_config") or {})
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.turn_id:
                return None
            pin = session.pin if session.pin and session.pin.turn_id == session.turn_id else None
        if pin is None:
            prompt_tokens = self._estimate_tokens(messages, tools)
            with self._lock:
                pin = session.pin = self._decide(session_id, session, model, requested, prompt_tokens)
        if not pin.applied or pin.suspended:
            return None
        if pin.model == model and pin.effort == requested.get("effort"):
            return None
        reasoning = dict(requested, effort=pin.effort, enabled=True) if pin.effort else requested
        return pin.model, reasoning

    def abandon_turn(self, session_id: Any) -> None:
        with self._lock:
            session = self._sessions.get(str(session_id or ""))
            if session and session.pin:
                session.pin.suspended = True

    # Internals ----------------------------------------------------------------------------

    def _decide(self, session_id: str, session: Session, model: str, requested: dict, prompt_tokens: int) -> Pin:
        native = Pin(session.turn_id, model, requested.get("effort"), applied=False)
        light, heavy = self.settings.models
        tier = session.tier
        usable = [m for m in (light, heavy) if m == model or self._available(m)]
        if tier == HEAVY or light not in usable:
            target, reason = heavy, "heavy task" if tier == HEAVY else f"{light} unavailable"
        elif heavy not in usable:
            target, reason = light, f"{heavy} unavailable"
        else:
            choice = choose(light, heavy, prompt_tokens=prompt_tokens, now=self._clock(), cache=session.cache,
                            stats=session.stats, ttl=self.settings.cache_ttl_seconds, price=self._price)
            target, reason = choice.model, choice.reason
        effort = self._effort(target, tier, requested.get("effort"))
        if target not in usable or (effort is None and tier != HEAVY):
            return native
        pin = Pin(session.turn_id, target, effort, applied=self.settings.mode == "route")
        log.info("smart-router%s: session=%s tier=%s [%s] -> %s/%s, prompt~%dk tokens, %s",
                 "" if pin.applied else " [shadow]", session_id[:12], tier, session.tier_source, target,
                 effort or "default", prompt_tokens // 1000, reason)
        return pin

    def _classify_remotely(self, history: Any, user_message: Any, session_id: str) -> Optional[tuple[str, float]]:
        if self._remote_tier is None or self._clock() < self._remote_down_until:
            return None
        try:
            result = self._remote_tier(history, user_message, session_id)
        except Exception as exc:
            self._remote_down_until = self._clock() + REMOTE_COOLDOWN_S
            log.warning("smart-router: Decisions API failed (%s); local classifier for %d min",
                        type(exc).__name__, REMOTE_COOLDOWN_S // 60)
            return None
        return result if result and result[0] in TIERS else None

    def _effort(self, model: str, tier: Optional[str], requested: Any) -> Optional[str]:
        """Heavy turns keep the user's effort; lighter turns use the tier effort, never above the user's."""
        if tier == HEAVY:
            return self._clamp_effort(model, requested) if isinstance(requested, str) and requested else None
        wanted = self.settings.light_effort if tier == LIGHT else self.settings.standard_effort
        if requested in EFFORTS and EFFORTS.index(requested) < EFFORTS.index(wanted):
            wanted = requested
        return self._clamp_effort(model, wanted)

    def _eligible(self, model: str, messages: list, params: dict) -> bool:
        if model not in self.settings.models:
            return False
        if params.get("provider") != "openai-codex" or params.get("is_codex_backend") is not True:
            return False
        if params.get("context_management") or params.get("request_overrides"):
            return False
        if (params.get("reasoning_config") or {}).get("enabled") is False:
            return False
        return all(_plain_message(message) for message in messages)

    def _available(self, model: str) -> bool:
        now = self._clock()
        with self._lock:
            if self._blocked.get(model, float("-inf")) > now:
                return False
            fetched_at, known = self._known_models
        if now - fetched_at > CATALOG_TTL_S or not known:
            known = self._catalog()
            with self._lock:
                self._known_models = (now, known)
        return model in known

    def _served_model(self, session: Session, model: str, response_model: Any) -> Optional[str]:
        served = str(response_model or "")
        for candidate in self.settings.models:
            if served == candidate or served.startswith(candidate + "-"):
                return candidate
        if served:
            return None
        pin = session.pin
        if pin and pin.applied and not pin.suspended and pin.turn_id == session.turn_id:
            return pin.model
        return model if model in self.settings.models else None

    def _session(self, session_id: str, now: float) -> Session:
        """Hermes fires ``on_session_end`` after every turn, so state is evicted by idleness and count instead."""
        session = self._sessions.pop(session_id, None) or Session()
        session.touched = now
        while self._sessions and (len(self._sessions) >= MAX_SESSIONS
                                  or next(iter(self._sessions.values())).touched < now - SESSION_IDLE_S):
            self._sessions.popitem(last=False)
        self._sessions[session_id] = session
        return session


def _plain_message(message: Any) -> bool:
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, list) and any(
            not isinstance(part, dict) or part.get("type") not in _TEXT_PARTS for part in content):
        return False
    return not any(isinstance(item, dict) and item.get("type") == "compaction"
                   for item in message.get("codex_reasoning_items") or ())


def _block_seconds(status_code: Any, message: str) -> float:
    text = message.lower()
    if status_code == 404 or (status_code == 400 and any(marker in text for marker in _UNAVAILABLE)):
        return UNAVAILABLE_BLOCK_S
    if status_code == 429 or any(marker in text for marker in _EXHAUSTED):
        return EXHAUSTED_BLOCK_S
    return 0.0
