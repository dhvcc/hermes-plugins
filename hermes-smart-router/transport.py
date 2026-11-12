"""Swap the model before Hermes's native Responses transport converts history.

Hermes then filters replayed reasoning, stamps provenance and normalizes the response for
the model actually sent. Selecting the model after ``build_kwargs`` (request middleware)
would leave the reasoning stamped with the wrong model.
"""
from __future__ import annotations

import logging
import os

from . import hermes_api

log = logging.getLogger("hermes_smart_router")
API_MODE = "codex_responses"


def install_transport(ctx, router) -> type:
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        raise RuntimeError("needs plugins.isolation: in_process; a plugin host cannot reach Hermes's transport")
    from agent.transports import get_transport, register_transport
    from agent.transports.codex import ResponsesApiTransport
    from hermes_constants import get_hermes_home

    router.pairs = [pair for pair in router.pairs if len({hermes_api.context_window(m) for m in pair}) == 1]
    if not router.pairs:
        raise RuntimeError("routed models have different context windows")
    native = type(get_transport(API_MODE))
    if native is not ResponsesApiTransport:
        raise RuntimeError(f"{API_MODE} transport is already replaced by {native.__module__}")
    home = get_hermes_home().resolve()
    active = True

    class RoutingTransport(native):
        def build_kwargs(self, model, messages, tools=None, **params):
            plan = None
            if active and get_hermes_home().resolve() == home:
                try:
                    plan = router.plan(model, messages, tools, params)
                except Exception:
                    log.debug("smart-router: planning failed; native request", exc_info=True)
            if plan is None:
                return super().build_kwargs(model, messages, tools, **params)
            routed_model, reasoning = plan
            try:
                return super().build_kwargs(routed_model, messages, tools, **dict(params, reasoning_config=reasoning))
            except Exception:
                log.debug("smart-router: routed build failed; native request", exc_info=True)
                router.abandon_turn(params.get("session_id"))
                return super().build_kwargs(model, messages, tools, **params)

    def uninstall() -> None:
        nonlocal active
        active = False
        if type(get_transport(API_MODE)) is RoutingTransport:
            register_transport(API_MODE, native)

    ctx.on_unload(uninstall)
    register_transport(API_MODE, RoutingTransport)
    return RoutingTransport
