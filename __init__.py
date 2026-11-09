"""Hermes Smart Router: per-turn Luna/Sol routing on the Hermes Codex subscription."""
import logging

from .router import Router
from .settings import Settings

log = logging.getLogger("hermes_smart_router")


def register(ctx):
    try:
        settings = Settings.load(ctx.get_config)
        router = Router(settings)
        from .transport import install_transport
        install_transport(ctx, router)
    except Exception as exc:
        log.warning("smart-router: disabled, Hermes stays native (%s)", exc)
        return
    ctx.register_hook("pre_llm_call", router.on_turn)
    ctx.register_hook("post_api_request", router.on_api_success)
    ctx.register_hook("api_request_error", router.on_api_error)
