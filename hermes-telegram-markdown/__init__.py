"""Hermes Telegram Markdown: make LLM Markdown parse the way it reads in Telegram rich messages."""
import logging

from .tgmd import normalize

log = logging.getLogger("hermes_telegram_markdown")


def register(ctx):
    platforms = None

    def platforms_cfg():
        nonlocal platforms
        if platforms is None:
            try:
                value = ctx.get_config("platforms", ["telegram"])
            except Exception:
                value = None
            platforms = {str(p).lower() for p in (value or ["telegram"])}
        return platforms

    def transform(response_text: str = "", platform: str = "", **_):
        if not response_text or str(platform or "").lower() not in platforms_cfg():
            return None
        try:
            fixed = normalize(response_text)
        except Exception:
            log.exception("telegram-markdown: normalize failed, sending original")
            return None
        return fixed if fixed != response_text else None

    ctx.register_hook("transform_llm_output", transform)
