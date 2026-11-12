"""Live view of background subagents: one pinned Telegram widget per chat, edited in place.

Reads the native async-delegation registry, keeps the last finished subagents (persisted, so the widget
survives restarts), checks in state.db whether each answer reached the chat, and takes ETA and the
"needs attention" flag from hermes-subagent-supervisor when that plugin is installed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import telegram
from .i18n import strings

log = logging.getLogger("hermes_subagent_widget")

SAMPLE_S = 5
FINAL = {"completed": "done", "error": "error", "failed": "error", "stalled": "error",
         "interrupted": "stopped", "cancelled": "stopped", "timeout": "error"}
LIVE = ("running", "stalling", "finalizing")


@dataclass
class Child:
    label: str
    tool: Optional[str] = None
    tool_since: float = 0.0


@dataclass
class Unit:
    did: str
    parent: str
    chat: str
    key: str
    goals: list
    start: float
    children: list = field(default_factory=list)


class Widget:
    def __init__(self, get: Callable[[str, Any], Any], secret: Callable[[str], Optional[str]]):
        self.get, self.secret = get, secret
        self.lock = threading.Lock()
        self.units: dict[str, Unit] = {}
        self.boards: dict[str, dict] = {}
        self.history: dict[str, list] = {}
        self.sent: dict[str, str] = {}
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.load()

    def cfg(self, key: str, default: Any) -> Any:
        try:
            value = self.get(key, default)
        except Exception:
            value = default
        return default if value is None else value

    # ---- persistence -----------------------------------------------------------------------------
    def _path(self, name: str):
        from hermes_constants import get_hermes_home
        return get_hermes_home() / "logs" / name

    def load(self) -> None:
        try:
            data = json.loads(self._path("subagent-widget.json").read_text())
        except Exception:
            return
        self.boards, self.history = data.get("boards") or {}, data.get("history") or {}

    def save(self) -> None:
        try:
            with self.lock:
                data = json.dumps({"boards": self.boards, "history": self.history}, ensure_ascii=False)
            self._path("subagent-widget.json").write_text(data)
        except Exception:
            log.exception("subagent-widget: save failed")

    # ---- loop ------------------------------------------------------------------------------------
    def ensure_thread(self) -> None:
        if not self.cfg("gateway_only", True) or "gateway" in " ".join(sys.argv):
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.loop, name="subagent-widget", daemon=True)
                self.thread.start()
                log.info("widget thread started")

    def loop(self) -> None:
        last = 0.0
        while not self.stop.wait(SAMPLE_S):
            try:
                self.tick(time.time())
                if time.time() - last >= float(self.cfg("refresh_s", 30)):
                    last = time.time()
                    self.refresh(last)
            except Exception:
                log.exception("subagent-widget tick failed")

    def tick(self, now: float) -> None:
        from tools.async_delegation import list_async_delegations
        items = {i.get("delegation_id"): i for i in list_async_delegations() if i.get("delegation_id")}
        new = []
        with self.lock:
            for did, item in items.items():
                u = self.units.get(did)
                if u is None:
                    key = str(item.get("session_key") or "")
                    if item.get("status") not in LIVE or ":telegram:" not in key:
                        continue
                    goals = list(item.get("goals") or [item.get("goal") or ""])
                    u = Unit(did, str(item.get("parent_session_id") or ""), key.rsplit(":", 1)[-1], key, goals,
                             float(item.get("dispatched_at") or now), [Child(_short(g, 40)) for g in goals])
                    self.units[did] = u
                    new.append(u)
                status = item.get("status")
                if status in FINAL:
                    self.finish(u, FINAL[status], now)
                    continue
                acts = item.get("children_activity") or []
                while len(u.children) < len(acts):
                    u.children.append(Child(f"subagent {len(u.children) + 1}"))
                for c, a in zip(u.children, acts):
                    tool = a.get("current_tool") if isinstance(a, dict) else None
                    if tool != c.tool:
                        c.tool, c.tool_since = tool, now
            for did in [d for d in self.units if d not in items]:
                self.finish(self.units[did], "done", now)
        for u in new:
            threading.Thread(target=self.titles, args=(u,), daemon=True).start()

    def finish(self, u: Unit, status: str, now: float) -> None:
        """Caller holds the lock."""
        self.units.pop(u.did, None)
        eta = self.supervisor().get(u.did, {}).get("eta", 0)
        rows = self.history.setdefault(u.chat, [])
        for i, c in enumerate(u.children):
            rows.append({"id": f"{u.did}:{i}", "label": c.label, "start": u.start, "end": now, "eta": eta,
                         "status": status, "key": u.key, "parent": u.parent, "reply": None})
        del rows[:-int(self.cfg("rows", 6)) * 2]

    def titles(self, u: Unit) -> None:
        """Short names through Hermes's own title generator (auxiliary.title_generation)."""
        try:
            from agent.title_generator import generate_title
        except Exception:
            return
        for i, goal in enumerate(u.goals):
            try:
                title = generate_title(goal, timeout=15)
            except Exception as exc:
                log.info("subagent-widget: title failed: %s", exc)
                continue
            if not title:
                continue
            label = _short(title.strip().strip('"«»'), 40)
            with self.lock:
                if i < len(u.children):
                    u.children[i].label = label
                for r in self.history.get(u.chat, []):
                    if r["id"] == f"{u.did}:{i}":
                        r["label"] = label

    # ---- data from other places ------------------------------------------------------------------
    def supervisor(self) -> dict:
        """ETA and status per delegation from hermes-subagent-supervisor, if it runs in this profile."""
        try:
            data = json.loads(self._path("subagent-supervisor-state.json").read_text())
            if time.time() - float(data.get("at") or 0) > 120:
                return {}
            return {t["id"]: {"eta": float(t.get("eta_min") or 0) * 60, "status": t.get("status")}
                    for t in data.get("tracks") or []}
        except Exception:
            return {}

    def replies(self, now: float) -> bool:
        """When did the answer for a finished subagent actually reach the chat (delivery_obligations)."""
        from hermes_constants import get_hermes_home
        window = float(self.cfg("reply_window_min", 15)) * 60
        with self.lock:
            pending = [r for rows in self.history.values() for r in rows if r.get("reply") is None and r.get("key")]
        if not pending:
            return False
        changed = False
        try:
            db = sqlite3.connect(f"file:{get_hermes_home() / 'state.db'}?mode=ro", uri=True, timeout=2)
            try:
                for r in pending:
                    row = db.execute("select min(ts) from (select created_at ts from delivery_obligations where "
                                     "session_key=? and state='delivered' and created_at between ? and ? union all "
                                     "select timestamp from messages where session_id=? and role='assistant' and "
                                     "content like 'MEDIA:%' and timestamp between ? and ?)",
                                     (r["key"], r["end"] - 15, r["end"] + window,
                                      r.get("parent") or "", r["end"] - 15, r["end"] + window)).fetchone()
                    if row and row[0]:
                        r["reply"], changed = float(row[0]), True
                    elif now - r["end"] > window:
                        r["reply"], changed = 0, True
            finally:
                db.close()
        except Exception:
            log.exception("subagent-widget: reply lookup failed")
        return changed

    # ---- render ----------------------------------------------------------------------------------
    def refresh(self, now: float) -> None:
        token = self.secret("TELEGRAM_BOT_TOKEN")
        if not token:
            return
        lang = str(self.cfg("language", "en"))
        tg = telegram.Telegram(token, lang)
        dirty = self.replies(now)
        sup = self.supervisor()
        hang = float(self.cfg("hang_alert_min", 10)) * 60
        with self.lock:
            rows_by: dict[str, list] = {}
            for u in sorted(self.units.values(), key=lambda x: x.start, reverse=True):
                info = sup.get(u.did, {})
                for c in u.children:
                    stuck = c.tool and now - c.tool_since > hang
                    rows_by.setdefault(u.chat, []).append({
                        "label": c.label, "start": u.start, "end": None, "reply": None,
                        "status": "attention" if info.get("status") == "attention" else "running",
                        "elapsed": now - u.start, "eta": info.get("eta", 0),
                        "warn": strings(lang)["hang"].format(tool=c.tool, n=round((now - c.tool_since) / 60)) if stuck else ""})
            for chat, rows in self.history.items():
                for r in sorted(rows, key=lambda x: x["end"], reverse=True):
                    rows_by.setdefault(chat, []).append({**r, "elapsed": r["end"] - r["start"], "warn": ""})
        limit, pin = int(self.cfg("rows", 6)), bool(self.cfg("pin", True))
        html = hashlib.sha1(telegram.widget_html(lang).encode()).hexdigest()[:12]
        for chat, rows in rows_by.items():
            data = telegram.widget_data(rows[:limit], now)
            entry = self.boards.get(chat)
            if entry and entry.get("html") != html:  # the page changed (update, language): re-send it
                tg.remove(chat, entry["mid"])
                self.boards.pop(chat, None)
                entry, dirty = None, True
            if entry and self.sent.get(chat) == data:
                continue
            try:
                if entry is None:
                    self.boards[chat] = {"mid": tg.send_widget(chat, data, pin), "html": html}
                    dirty = True
                elif not tg.edit_widget(chat, entry["mid"], data):
                    self.boards.pop(chat, None)
                    dirty = True
                    continue
                self.sent[chat] = data
            except Exception:
                log.exception("subagent-widget: widget failed")
        if dirty:
            self.save()


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"
