"""Widget page assembly, limits, lint and headless Chrome screenshots."""
from __future__ import annotations

import html as _html
import os
import re
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Optional

MAX_RAW, MAX_ZIP, MAX_H, MAX_NODES, MAX_RULES = 32768, 4096, 600, 2000, 400

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

THEMES = {
    "dark": {"bg-color": "#212d3b", "text-color": "#ffffff", "hint-color": "#7d8b99", "link-color": "#62bcf9",
             "button-color": "#50a8eb", "button-text-color": "#ffffff", "secondary-bg-color": "#151e27",
             "accent-text-color": "#64b5ef", "destructive-text-color": "#ee686f",
             "section-separator-color": "#2c3b4b"},
    "light": {"bg-color": "#ffffff", "text-color": "#000000", "hint-color": "#8e8e93", "link-color": "#2481cc",
              "button-color": "#2481cc", "button-text-color": "#ffffff", "secondary-bg-color": "#f1f1f4",
              "accent-text-color": "#2481cc", "destructive-text-color": "#d14e4e",
              "section-separator-color": "#e3e3e6"},
}

LINT = [
    (r"\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(|new\s+(XMLHttpRequest|WebSocket)", "no network: fetch/XHR/WebSocket throw"),
    (r"<script[^>]+\bsrc=|<link[^>]+stylesheet|@import", "external scripts/stylesheets are never loaded"),
    (r"<(img|image|source)[^>]+(src|href)=[\"']?https?:", "remote images are never loaded; use data: PNG/JPEG or inline SVG"),
    (r"data:image/svg", "data: SVG images are removed; inline the <svg>"),
    (r"<(input|select|textarea|form|iframe)\b", "input/select/textarea/form/iframe are removed; only <button> works"),
    (r"\d\s*(vh|dvh|svh|lvh)\b", "vh units are unsupported"),
    (r"@font-face", "@font-face is removed; use system-ui/monospace"),
    (r"overflow(-[xy])?\s*:\s*(auto|scroll)", "overflow auto/scroll becomes hidden; nothing scrolls"),
    (r"\b(alert|confirm|prompt|print)\s*\(|window\.open\s*\(|location\s*\.", "alert/confirm/window.open/location are unavailable; use TelegramWidget.openLink"),
]

STUB = """<script>window.__e=[];onerror=function(m){__e.push(String(m))};
window.TelegramWidget={profile:1,colorScheme:'%s',themeParams:{},chatData:null,publicData:null,isActive:true,
onEvent:function(){},offEvent:function(){},openLink:function(){},openTelegramLink:function(){},copyText:function(){},
setResizeAnchor:function(){},ready:function(){},request:function(){return Promise.reject(new Error('preview'))},
HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},selectionChanged:function(){}}};
addEventListener('load',function(){setTimeout(function(){var d=document.documentElement;
d.setAttribute('data-h',Math.ceil(document.body.getBoundingClientRect().bottom));
d.setAttribute('data-n',document.getElementsByTagName('*').length);d.setAttribute('data-e',__e.join(' | '))},300)})</script>"""


def page(body: str) -> str:
    return BASE + body


def sizes(doc: str) -> tuple[int, int]:
    raw = doc.encode()
    return len(raw), len(zlib.compress(raw, 9))


def lint(doc: str) -> list[str]:
    out = [msg for pat, msg in LINT if re.search(pat, doc, re.I)]
    rules = len(re.findall(r"\{", "".join(re.findall(r"<style[^>]*>(.*?)</style>", doc, re.S | re.I))))
    if rules > MAX_RULES:
        out.append(f"{rules} CSS rules, limit {MAX_RULES}")
    if "\x00" in doc:
        out.append("NUL characters are rejected")
    return out


def chrome(explicit: Optional[str] = None) -> Optional[str]:
    if explicit and os.path.exists(explicit):
        return explicit
    try:
        from hermes_cli.browser_runtime import chromium_executable
        exe = chromium_executable()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if os.path.exists(p):
            return p
    for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        if shutil.which(n):
            return shutil.which(n)
    return None


def _preview_doc(doc: str, scheme: str, width: int) -> str:
    vars_ = ";".join(f"--tg-theme-{k}:{v}" for k, v in THEMES[scheme].items())
    head = (f"<!doctype html><html><head><meta charset=utf-8><style>:root{{{vars_};color-scheme:{scheme}}}"
            f"html{{background:var(--tg-theme-bg-color);width:{width}px;overflow:hidden}}</style>{STUB % scheme}</head><body>")
    return head + doc + "</body></html>"


def _run(exe: str, args: list[str], timeout: int = 40) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as prof:
        return subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                               "--no-default-browser-check", "--mute-audio", f"--user-data-dir={prof}",
                               "--virtual-time-budget=2000", *args],
                              capture_output=True, text=True, timeout=timeout)


def shoot(doc: str, width: int, scheme: str, exe: str, clip: bool = True) -> dict:
    """Render once to measure, once to screenshot. Returns height, nodes, errors, png bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "w.html"
        src.write_text(_preview_doc(doc, scheme, width))
        url = src.as_uri()
        dom = _run(exe, ["--window-size=600,600", "--dump-dom", url]).stdout
        attr = lambda k: (re.search(rf'data-{k}="([^"]*)"', dom) or [None, ""])[1]
        height = int(attr("h") or 0)
        nodes = int(attr("n") or 0)
        errors = [e for e in _html.unescape(attr("e")).split(" | ") if e]
        shot_h = max(50, min(height, MAX_H) if clip else min(height, 4000))
        out = Path(tmp) / "w.png"
        _run(exe, [f"--window-size={width},{shot_h}", f"--screenshot={out}", url])
        png = out.read_bytes() if out.exists() else b""
    return {"height": height, "nodes": nodes, "errors": errors, "png": png}
