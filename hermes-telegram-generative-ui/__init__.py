"""Hermes Telegram Generative UI: the agent draws charts, tables and cards as Telegram widgets."""
from __future__ import annotations

import base64
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

PREVIEW_SCHEMA = {
    "name": "ui_preview",
    "description": ("Check a widget page before ui_render. Returns a phone-width PNG, content height, size against "
                    "the 4096-byte limit, script errors and unsupported features. Fix what it reports, then "
                    "ui_render. " + RULES),
    "parameters": {"type": "object", "properties": {
        "html": {"type": "string", "description": "Body HTML"},
        "width": {"type": "integer", "description": "CSS pixels, default 380"},
        "appearance": {"type": "string", "enum": ["dark", "light"], "description": "Default dark"},
    }, "required": ["html"]},
}

RENDER_SCHEMA = {
    "name": "ui_render",
    "description": ("Show a finished page (chart, table, status card, small dashboard, mockup) in this Telegram "
                    "chat as a live widget, above your final reply. Answer data with a trend or comparison with a "
                    "chart. Do not announce or restate what it shows. Check it with ui_preview first. If it does "
                    "not fit, cut it down: fewer points, rows and styles. " + RULES + " "
                    + THEME),
    "parameters": {"type": "object", "properties": {
        "html": {"type": "string", "description": "Body HTML, the same you previewed"},
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
    cfg = {}
    try:
        cfg = (ctx.get_config() or {}).get("settings") or {}
    except Exception:
        pass
    exe_cfg = cfg.get("chrome_path")

    def report(doc: str) -> dict:
        raw, zipped = render.sizes(doc)
        return {"bytes_zlib": zipped, "limit_zlib": render.MAX_ZIP, "bytes_raw": raw,
                "fits": raw <= render.MAX_RAW and zipped <= render.MAX_ZIP, "issues": render.lint(doc)}

    def preview(args: dict, **_) -> object:
        body = str(args.get("html") or "")
        doc = render.page(body)
        info = report(doc)
        exe = render.chrome(exe_cfg)
        if not exe:
            info["note"] = "No Chrome/Chromium found, so no screenshot. Set chrome_path in the plugin settings."
            return json.dumps(info)
        try:
            shot = render.shoot(doc, int(args.get("width") or 380), args.get("appearance") or "dark", exe)
        except Exception as exc:
            info["note"] = f"screenshot failed: {exc}"
            return json.dumps(info)
        info.update(content_height=shot["height"], nodes=shot["nodes"], script_errors=shot["errors"])
        if shot["height"] > render.MAX_H:
            info["issues"].append(f"{shot['height']}px tall, everything past {render.MAX_H}px is clipped")
        if shot["nodes"] > render.MAX_NODES:
            info["issues"].append(f"{shot['nodes']} nodes, limit {render.MAX_NODES}")
        if not info["fits"]:
            info["issues"].append(f"{info['bytes_zlib']} bytes after zlib, limit {render.MAX_ZIP}: shrink it")
        text = json.dumps(info)
        if not shot["png"]:
            return text
        url = "data:image/png;base64," + base64.b64encode(shot["png"]).decode()
        return {"_multimodal": True,
                "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}],
                "text_summary": text}

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
        info = report(doc)
        if not info["fits"]:
            return json.dumps({"ok": False, "error": f"{info['bytes_zlib']} bytes after zlib, limit "
                               f"{render.MAX_ZIP}. Shrink it: fewer points, rows and styles."})
        res = _api("sendWidget", {**base, "html": doc, **({"caption": title} if title else {})})
        if res.get("ok"):
            return json.dumps({"ok": True, "message_id": res["result"]["message_id"],
                               "note": "Shown above your reply. Do not restate it."})
        log.warning("sendWidget failed: %s", res.get("description"))
        return json.dumps({"ok": False, "error": res.get("description") or "sendWidget failed"})

    ctx.register_tool(name="ui_preview", toolset="ui", schema=PREVIEW_SCHEMA, handler=preview,
                      description=PREVIEW_SCHEMA["description"], emoji="🖼")
    ctx.register_tool(name="ui_render", toolset="ui", schema=RENDER_SCHEMA, handler=show,
                      description=RENDER_SCHEMA["description"], emoji="🖼")
