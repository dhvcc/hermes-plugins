"""Subagent board: one pinned Telegram widget per chat, edited in place."""
from __future__ import annotations

import json
import time
from typing import Optional
from urllib.request import Request, urlopen

from .i18n import strings

WIDGET_HTML: dict = {}
CODES = {"running": "r", "attention": "a", "done": "d", "error": "e", "stopped": "s"}


def widget_html(lang: str = "en") -> str:
    if lang not in WIDGET_HTML:
        from pathlib import Path
        from .i18n import strings
        keys = ("min", "left", "since", "of", "done", "error", "stopped", "no_reply", "reply", "empty")
        t = {k: v for k, v in strings(lang).items() if k in keys}
        WIDGET_HTML[lang] = (Path(__file__).parent / "widget.html").read_text().replace(
            "__STRINGS__", json.dumps(t, ensure_ascii=False))
    return WIDGET_HTML[lang]


def widget_data(rows: list[dict], now: float) -> str:
    """Rows: [title, status, started HH:MM, elapsed s, eta s, warning, ended HH:MM, answered HH:MM | "" | "!"]."""
    hm = lambda ts: time.strftime("%H:%M", time.localtime(ts))
    out = []
    for r in rows:
        reply = r.get("reply")
        out.append([r["label"][:40], CODES.get(r["status"], "r"), hm(r["start"]), int(r["elapsed"]), int(r["eta"]),
                    r.get("warn") or "", hm(r["end"]) if r.get("end") else "",
                    hm(reply) if reply else "!" if reply == 0 else ""])
    while True:
        data = json.dumps({"r": out}, ensure_ascii=False, separators=(",", ":"))
        if len(data.encode()) <= 1024 or not out:
            return data
        out.pop()


class Telegram:
    def __init__(self, token: str, lang: str = "en"):
        self.token, self.lang = token, lang

    def _call(self, method: str, fields: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        req = Request(url, data=json.dumps(fields).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            body = getattr(exc, "read", lambda: b"")()
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "description": str(exc)}

    def send_widget(self, chat_id: str, data: str, pin: bool) -> Optional[int]:
        res = self._call("sendWidget", {"chat_id": chat_id, "html": widget_html(self.lang), "chat_data": data,
                                        "caption": strings(self.lang)["caption"], "disable_notification": True})
        if not res.get("ok"):
            raise RuntimeError(res.get("description") or "sendWidget failed")
        mid = res["result"]["message_id"]
        if pin:
            self._call("pinChatMessage", {"chat_id": chat_id, "message_id": mid, "disable_notification": True})
        return mid

    def edit_widget(self, chat_id: str, message_id: int, data: str) -> bool:
        res = self._call("editMessageWidgetData", {"chat_id": chat_id, "message_id": message_id, "chat_data": data})
        return bool(res.get("ok")) or "not modified" in str(res.get("description", ""))

    def remove(self, chat_id: str, message_id: int) -> None:
        self._call("unpinChatMessage", {"chat_id": chat_id, "message_id": message_id})
        self._call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    def text(self, chat_id: str, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}})
