"""Widget page assembly, Telegram limits and a static check for what the widget sandbox drops."""
from __future__ import annotations

import re
import zlib

MAX_RAW, MAX_ZIP, MAX_NODES, MAX_RULES = 32768, 4096, 2000, 400

BASE = ("<style>:root{--foreground:var(--tg-theme-text-color);--muted-foreground:var(--tg-theme-hint-color);"
        "--card:var(--tg-theme-secondary-bg-color);--border:var(--tg-theme-section-separator-color);"
        "--primary:var(--tg-theme-button-color);--primary-foreground:var(--tg-theme-button-text-color);"
        "--accent:var(--tg-theme-accent-text-color);--link:var(--tg-theme-link-color);"
        "--destructive:var(--tg-theme-destructive-text-color);--success:#3fb950;--warning:#d29922;"
        "--chart-1:#3d8bfd;--chart-2:#3fb950;--chart-3:#d29922;--chart-4:#db61a2;--chart-5:#a371f7;--chart-6:#2fb8b8;"
        "--radius:10px;--font-sans:system-ui,sans-serif;--font-mono:ui-monospace,monospace}"
        "body{margin:0;padding:8px 12px calc(8px + env(safe-area-inset-bottom,0px));"
        "font:var(--tg-text-font-size,15px)/var(--tg-text-line-height,1.35) var(--font-sans);color:var(--foreground)}"
        "</style>")

LINT = [
    (r"\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(|new\s+(XMLHttpRequest|WebSocket)", "no network: fetch/XHR/WebSocket throw"),
    (r"<script[^>]+\bsrc=|<link[^>]+stylesheet|@import", "external scripts/stylesheets are never loaded"),
    (r"<(img|image|source)[^>]+(src|href)=[\"']?https?:", "remote images are never loaded; use data: PNG/JPEG or inline SVG"),
    (r"data:image/svg", "data: SVG images are removed; inline the <svg>"),
    (r"<(input|select|textarea|form|iframe)\b", "input/select/textarea/form/iframe are removed; only <button> works"),
    (r"\d\s*(vh|dvh|svh|lvh)\b", "vh units are unsupported"),
    (r"@font-face", "@font-face is removed; use system-ui/monospace"),
    (r"overflow(-[xy])?\s*:\s*(auto|scroll)", "overflow auto/scroll becomes hidden; nothing scrolls"),
    (r"\b(alert|confirm|prompt)\s*\(|window\.open\s*\(|\blocation\.(href|assign|replace|reload)",
     "alert/confirm/window.open/location are unavailable; use TelegramWidget.openLink"),
]


def page(body: str) -> str:
    return BASE + body


def check(doc: str) -> list[str]:
    """Everything that would fail or silently break; empty when the page is fine to send."""
    raw = doc.encode()
    zipped = len(zlib.compress(raw, 9))
    out = [msg for pat, msg in LINT if re.search(pat, doc, re.I)]
    if len(raw) > MAX_RAW:
        out.append(f"{len(raw)} bytes of HTML, limit {MAX_RAW}")
    if zipped > MAX_ZIP:
        out.append(f"{zipped} bytes after zlib, limit {MAX_ZIP}: fewer points, rows and styles")
    rules = len(re.findall(r"\{", "".join(re.findall(r"<style[^>]*>(.*?)</style>", doc, re.S | re.I))))
    if rules > MAX_RULES:
        out.append(f"{rules} CSS rules, limit {MAX_RULES}")
    nodes = len(re.findall(r"<[a-zA-Z]", doc))
    if nodes > MAX_NODES:
        out.append(f"about {nodes} elements, limit {MAX_NODES}")
    if "\x00" in doc:
        out.append("NUL characters are rejected")
    return out
