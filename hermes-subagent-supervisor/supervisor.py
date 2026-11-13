"""Delegation accountability on top of native Hermes pieces.

Reads the native async-delegation registry, wakes the parent through its native session heartbeat when a
subagent is overdue or stuck, and stops a unit only as a last resort. All state is in memory: a gateway
restart interrupts background delegations anyway.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from urllib.request import Request, urlopen

from . import estimate
from .i18n import strings

log = logging.getLogger("hermes_subagent_supervisor")

SAMPLE_S = 5
HB_MARK = "[subagent-supervisor]"
HB_PROMPT = (
    HB_MARK + " Internal check, invisible to the user. Look at the Active subagents block of this turn. For each "
    "flagged one: still progressing and useful -> subagent_deadline with a realistic, generous new ETA (not a "
    "minute or two, so you are not woken again for nothing); off track -> delegate_task action=steer with a "
    "concrete correction; stuck, looping or no longer needed -> delegate_task action=stop. Then answer exactly "
    "[SILENT]. Write to the user instead only if you stopped a worker, need their decision, or the result will "
    "come much later than you told them; then one short natural sentence about the work itself, never about "
    "checks, wake-ups, deadlines or this instruction."
)
FINAL = {"completed": "done", "error": "error", "failed": "error", "stalled": "error",
         "interrupted": "stopped", "cancelled": "stopped", "timeout": "error"}


@dataclass
class Child:
    label: str
    tool: Optional[str] = None
    tool_since: float = 0.0


@dataclass
class Track:
    did: str
    parent: str
    chat: Optional[str]
    goals: list
    text: str
    start: float
    eta: float
    eta_src: str = "default"
    next_check: float = 0.0
    status: str = "running"
    flags: list = field(default_factory=list)
    flagged_at: float = 0.0
    woke_for: set = field(default_factory=set)
    stop_tried: bool = False
    ended: float = 0.0
    key: str = ""
    children: list = field(default_factory=list)


class Supervisor:
    def __init__(self, get: Callable[[str, Any], Any], secret: Callable[[str], Optional[str]]):
        self.get, self.secret = get, secret
        self.lock = threading.Lock()
        self.tracks: dict[str, Track] = {}
        self.last_turn: dict[str, float] = {}
        self.first_turn: dict[str, float] = {}
        self.wakes: dict[str, float] = {}
        self.thread: Optional[threading.Thread] = None
        self.stop = threading.Event()
        self.inject: Optional[Callable[[str, str], bool]] = None

    def finish(self, t: Track, status: str, now: float) -> None:
        t.status, t.ended = status, now

    def cfg(self, key: str, default: Any) -> Any:
        try:
            value = self.get(key, default)
        except Exception:
            value = default
        return default if value is None else value

    # ---- hook: clock and subagents in every turn -------------------------------------------------
    def on_turn(self, session_id: str = "", parent_session_id: str = "", platform: str = "", **_: Any):
        self.ensure_thread()
        now = time.time()
        lines = [f"[clock] Now {datetime.now().astimezone().strftime('%a %Y-%m-%d %H:%M %Z')}."]
        sid = session_id or ""
        prev = self.last_turn.get(sid)
        if prev:
            lines[0] += f" Previous turn of this session: {_human(now - prev)} ago."
        self.last_turn[sid] = now
        if parent_session_id:
            first = self.first_turn.setdefault(sid, now)
            lines.append(f"You are a subagent; you started {_human(now - first)} ago.")
            return {"context": "\n".join(lines)}
        with self.lock:
            mine = [t for t in self.tracks.values() if t.parent == sid and (t.status in ("running", "attention")
                                                                           or now - t.ended < 120)]
        if mine:
            lines.append("Active subagents (delegate_task action=list/steer/stop; subagent_deadline to re-plan):")
            for t in mine:
                lines.append("- " + self.describe(t, now))
        return {"context": "\n".join(lines)}

    def describe(self, t: Track, now: float) -> str:
        if t.status not in ("running", "attention"):
            return f"{t.did} \"{_short(t.goals[0] if t.goals else t.text, 60)}\": {t.status}"
        el = now - t.start
        s = (f"{t.did} \"{_short(t.goals[0] if t.goals else t.text, 60)}\": {_human(el)} of ~{_human(t.eta)} "
             f"({t.eta_src})")
        if el > t.eta:
            s += " OVERDUE"
        for c in t.children:
            if c.tool:
                who = f"{c.label}: " if len(t.children) > 1 else ""
                s += f"; {who}in {c.tool} for {_human(now - c.tool_since)}"
        if t.flags:
            s += " | flagged: " + "; ".join(t.flags)
        return s

    # ---- tool: re-plan a deadline ----------------------------------------------------------------
    def deadline(self, args: dict, **_: Any) -> str:
        did, minutes = str(args.get("delegation_id") or ""), float(args.get("minutes") or 0)
        with self.lock:
            t = self.tracks.get(did)
            if t is None or t.status not in ("running", "attention"):
                return json.dumps({"ok": False, "error": "no running delegation with that id"})
            if not 1 <= minutes <= 240:
                return json.dumps({"ok": False, "error": "minutes must be 1..240"})
            now = time.time()
            t.eta = now - t.start + minutes * 60
            t.eta_src = "re-planned: " + _short(str(args.get("reason") or ""), 80)
            t.status, t.flags, t.woke_for = "running", [], set()
            t.next_check = now + minutes * 60
        return json.dumps({"ok": True, "delegation_id": did, "eta_minutes_from_now": minutes})

    # ---- supervisor loop -------------------------------------------------------------------------
    def ensure_thread(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.loop, name="subagent-supervisor", daemon=True)
            self.thread.start()
            log.info("supervisor thread started")

    def loop(self) -> None:
        while not self.stop.wait(SAMPLE_S):
            try:
                self.manual_inject()
                self.tick(time.time())
            except Exception:
                log.exception("subagent-supervisor tick failed")

    def tick(self, now: float) -> None:
        from tools.async_delegation import list_async_delegations
        items = {i.get("delegation_id"): i for i in list_async_delegations() if i.get("delegation_id")}
        new = []
        with self.lock:
            for did, item in items.items():
                t = self.tracks.get(did)
                status = item.get("status")
                if t is None:
                    if status not in ("running", "stalling", "finalizing"):
                        continue
                    t = self.track_from(item, now)
                    self.tracks[did] = t
                    new.append(t)
                if t.status in ("running", "attention") and status in FINAL:
                    self.finish(t, FINAL[status], now)
                self.sample(t, item, now)
            for t in self.tracks.values():
                if t.status in ("running", "attention") and t.did not in items:
                    self.finish(t, "done", now)
            for t in list(self.tracks.values()):
                if t.status in ("running", "attention"):
                    self.supervise(t, items.get(t.did, {}), now)
                elif now - t.ended > 3600:
                    del self.tracks[t.did]
            parents = {t.parent for t in self.tracks.values()}
        for t in new:
            threading.Thread(target=self.estimate, args=(t,), daemon=True).start()
        for parent in parents | set(self.wakes):
            self.sync_heartbeat(parent, now)
        self.dump(now, len(items))

    def manual_inject(self) -> None:
        """Operator test hook: logs/subagent-supervisor-inject.json {session_key, text} becomes a user turn."""
        from hermes_constants import get_hermes_home
        path = get_hermes_home() / "logs" / "subagent-supervisor-inject.json"
        if not self.cfg("debug_inject", False) or not path.exists() or self.inject is None:
            return
        req = json.loads(path.read_text())
        path.unlink()
        ok = self.inject(str(req["text"]), str(req["session_key"]))
        log.info("manual inject into %s: %s", req["session_key"], ok)

    def dump(self, now: float, seen: int) -> None:
        if not seen and not self.tracks:
            return
        try:
            from hermes_constants import get_hermes_home
            with self.lock:
                data = {"at": now, "registry_items": seen, "wakes": self.wakes,
                        "tracks": [{"id": t.did, "parent": t.parent, "chat": t.chat, "status": t.status,
                                    "eta_min": round(t.eta / 60, 1), "eta_src": t.eta_src, "flags": t.flags,
                                    "elapsed_min": round((now - t.start) / 60, 1)} for t in self.tracks.values()]}
            (get_hermes_home() / "logs" / "subagent-supervisor-state.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        except Exception:
            log.exception("dump failed")

    def track_from(self, item: dict, now: float) -> Track:
        goals = list(item.get("goals") or [item.get("goal") or ""])
        text = "\n".join(filter(None, [*goals, str(item.get("context") or "")]))
        key = str(item.get("session_key") or "")
        chat = key.rsplit(":", 1)[-1] if ":telegram:" in key else None
        eta = float(self.cfg("default_eta_min", 15)) * 60
        t = Track(item["delegation_id"], str(item.get("parent_session_id") or ""), chat, goals, text,
                  float(item.get("dispatched_at") or now), eta)
        t.children = [Child(_short(g, 48)) for g in goals]
        t.key = key
        t.next_check = t.start + t.eta
        return t

    def estimate(self, t: Track) -> None:
        minutes, src = estimate.explicit_minutes(t.text), "stated by you"
        url = str(self.cfg("decisions_url", "https://api.openai.com/v1/decisions") or "")
        if minutes is None and url:
            key = self.secret(str(self.cfg("api_key_env", "OPENAI_API_KEY")))
            if key:
                try:
                    minutes = estimate.decisions_minutes(
                        t.text, url=url,
                        api_key=key, model=str(self.cfg("decisions_model", "gpt-6-luna")), timeout=8)
                    src = "estimated"
                except Exception as exc:
                    log.info("subagent-supervisor: decisions estimate failed: %s", exc)
        if minutes:
            with self.lock:
                if t.eta_src == "default":
                    t.eta, t.eta_src = minutes * 60, src
                    t.next_check = t.start + t.eta

    def sample(self, t: Track, item: dict, now: float) -> None:
        acts = item.get("children_activity") or []
        while len(t.children) < len(acts):
            t.children.append(Child(f"subagent {len(t.children) + 1}"))
        for c, a in zip(t.children, acts):
            if not isinstance(a, dict):
                continue
            tool = a.get("current_tool")
            if tool != c.tool:
                c.tool, c.tool_since = tool, now

    def supervise(self, t: Track, item: dict, now: float) -> None:
        el = now - t.start
        flags = []
        if el > t.eta:
            flags.append(f"over its ETA ({_human(el)} of ~{_human(t.eta)})")
        hang_alert = float(self.cfg("hang_alert_min", 10)) * 60
        for c in t.children:
            if c.tool and now - c.tool_since > hang_alert:
                flags.append(f"{c.label} stuck in {c.tool} for {_human(now - c.tool_since)}")
        if item.get("status") == "stalling":
            flags.append("Hermes stall monitor tripped")
        quiet = float(item.get("seconds_since_progress") or 0)
        if not t.stop_tried and el > float(self.cfg("kill_factor", 3)) * t.eta and quiet > max(300.0, t.eta / 3):
            t.stop_tried = True
            self.backstop(t, el, quiet)
            return
        kinds = {"hang" if "stuck in" in f else "stall" if "stall" in f else "eta" for f in flags}
        if flags and (now >= t.next_check or kinds - t.woke_for):
            t.woke_for |= kinds
            t.flags, t.status, t.flagged_at = flags, "attention", now
            t.next_check = now + max(60.0, min(1800.0, t.eta / 3))
            self.wakes[t.parent] = now
        elif not flags:
            t.flags, t.status = [], "running"

    def backstop(self, t: Track, el: float, quiet: float) -> None:
        try:
            from tools import async_delegation as ad
            with ad._records_lock:
                rec = ad._records.get(t.did)
            stopped = rec is not None and ad._interrupt_records([rec], "subagent-supervisor", "deadline", "Stopped %d (%s)")
        except Exception:
            log.exception("subagent-supervisor: stop failed")
            stopped = False
        if stopped:  # called from tick, which holds the lock
            self.finish(t, "stopped", time.time())
        else:
            t.status = "attention"
        tr = self.t()
        text = (tr["stopped_msg"].format(goal=_short(t.goals[0] if t.goals else t.text, 80), el=_human(el),
                                         eta=_human(t.eta), quiet=_human(quiet)) if stopped
                else tr["stop_failed"].format(id=t.did))
        threading.Thread(target=self.notify, args=(t.chat, text), daemon=True).start()

    def sync_heartbeat(self, parent: str, now: float) -> None:
        """Arm the native heartbeat while a flagged subagent waits for the parent; disarm once it fired."""
        if not parent:
            return
        try:
            from hermes_cli.heartbeat import HeartbeatManager
            mgr = HeartbeatManager(session_id=parent)
            state = mgr.state
            ours = state is not None and state.prompt.startswith(HB_MARK)
            if state is not None and not ours:
                if parent in self.wakes:  # never touch a heartbeat the user set
                    self.fallback(parent, now)
                return
            with self.lock:
                flagged = [t for t in self.tracks.values() if t.parent == parent and t.status == "attention"]
            asked = self.wakes.get(parent)
            if ours and (state.fire_count > 0 or not flagged):
                mgr.clear()
                self.wakes.pop(parent, None)
                return
            if flagged and asked and not ours:
                mgr.set(HB_PROMPT, 60)
            if asked and now - asked > 300 and ours:
                self.fallback(parent, now)
        except Exception:
            log.exception("subagent-supervisor: heartbeat sync failed")

    def fallback(self, parent: str, now: float) -> None:
        """The parent could not be woken: stay quiet in chat (hermes-subagent-widget shows it red)."""
        self.wakes.pop(parent, None)
        log.info("subagent-supervisor: could not wake %s", parent)

    def notify(self, chat: Optional[str], text: str) -> None:
        token = self.secret("TELEGRAM_BOT_TOKEN")
        if not (chat and token):
            return
        body = {"chat_id": chat, "text": text, "link_preview_options": {"is_disabled": True}}
        try:
            urlopen(Request(f"https://api.telegram.org/bot{token}/sendMessage", json.dumps(body).encode(),
                            {"Content-Type": "application/json"}), timeout=20).read()
        except Exception:
            log.exception("subagent-supervisor: notify failed")

    def t(self) -> dict:
        return strings(str(self.cfg("language", "en")))


def _human(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{round(seconds / 60)}m"
    return f"{seconds / 3600:.1f}h"


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"
