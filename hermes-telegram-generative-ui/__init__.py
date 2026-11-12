"""Hermes Telegram Generative UI: the agent draws charts, tables and cards as Telegram widgets."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.request import Request, urlopen

from . import render

log = logging.getLogger("hermes_telegram_generative_ui")

RULES = ("Write only body content: inline <style>, <script>, inline <svg>. It runs in a sandbox, not a browser. "
         "Hard limits: 4096 bytes after zlib (roughly 12-20 KB of HTML), 600px tall (more is clipped, nothing "
         "scrolls), 2000 nodes, 400 CSS rules. No network, no external scripts, fonts or images (data: PNG/JPEG "
         "or inline SVG only), no input/select/textarea (only <button>), no vh units, no overflow scroll, no "
         "alert or window.open. Open links with TelegramWidget.openLink(url) from a click handler. Width is "
         "about 320-430px on phones: use fluid widths, give charts a fixed pixel height. Stay compact: short "
         "class names, no comments, only the data points that matter.")
THEME = ("Use CSS variables, not fixed colors: --foreground, --muted-foreground, --card, --border, --primary, "
         "--primary-foreground, --accent, --link, --destructive, --success, --warning, --chart-1 to --chart-6, "
         "--radius, --font-sans, --font-mono. The base sheet sets text color, font and padding; give body and "
         "the outer element no background, border, outer card or banner title.")

RENDER_SCHEMA = {
    "name": "ui_render",
    "description": ("Show a finished page (chart, table, status card, small dashboard, mockup) in this Telegram "
                    "chat as a live widget, above your final reply. Answer data with a trend or comparison with a "
                    "chart. Do not announce or restate what it shows. Anything the widget would break is refused "
                    "with the reason; fix it and call again. " + RULES + " "
                    + THEME),
    "parameters": {"type": "object", "properties": {
        "html": {"type": "string", "description": "Body HTML"},
        "title": {"type": "string", "description": "Short caption under it, optional"},
    }, "required": ["html"]},
}


def _secret(name: str):
    try:
        from agent.secret_scope import get_secret
        if v := get_secret(name):
            return v
    except Exception:
        pass
    if v := os.environ.get(name):
        return v
    try:
        from hermes_constants import get_hermes_home
        for line in (Path(get_hermes_home()) / ".env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except Exception:
        pass
    return None


def _session(name: str) -> str:
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, "")
    except Exception:
        return os.environ.get(name, "")


def _api(method: str, fields: dict) -> dict:
    url = f"https://api.telegram.org/bot{_secret('TELEGRAM_BOT_TOKEN')}/{method}"
    req = Request(url, data=json.dumps(fields).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as exc:
        try:
            return json.loads(getattr(exc, "read", lambda: b"")())
        except Exception:
            return {"ok": False, "description": str(exc)}


def register(ctx):
    def show(args: dict, **_) -> str:
        if _session("HERMES_SESSION_PLATFORM") != "telegram":
            return json.dumps({"ok": False, "error": "ui_render works only in a Telegram chat"})
        chat = _session("HERMES_SESSION_CHAT_ID")
        if not chat or not _secret("TELEGRAM_BOT_TOKEN"):
            return json.dumps({"ok": False, "error": "no Telegram chat or bot token"})
        doc = render.page(str(args.get("html") or ""))
        title = str(args.get("title") or "")[:1024]
        thread = _session("HERMES_SESSION_THREAD_ID")
        base = {"chat_id": chat, "disable_notification": True}
        if thread:
            base["message_thread_id"] = thread
        if _session("HERMES_SESSION_CHAT_TYPE") not in ("", "dm", "private"):
            return json.dumps({"ok": False, "error": "Telegram widgets work only in the private chat with the bot"})
        issues = render.check(doc)
        if issues:
            return json.dumps({"ok": False, "error": "Not sent, fix and retry: " + "; ".join(issues)})
        res = _api("sendWidget", {**base, "html": doc, **({"caption": title} if title else {})})
        if res.get("ok"):
            return json.dumps({"ok": True, "message_id": res["result"]["message_id"],
                               "note": "Shown above your reply. Do not restate it."})
        log.warning("sendWidget failed: %s", res.get("description"))
        return json.dumps({"ok": False, "error": res.get("description") or "sendWidget failed"})

    ctx.register_tool(name="ui_render", toolset="ui", schema=RENDER_SCHEMA, handler=show,
                      description=RENDER_SCHEMA["description"], emoji="🖼")
