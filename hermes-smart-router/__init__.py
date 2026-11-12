"""Hermes Smart Router: per-turn Luna/Sol routing on the Hermes Codex subscription."""
import logging

from .router import Router
from .settings import Settings

log = logging.getLogger("hermes_smart_router")


def register(ctx):
    ctx.register_cli_command(name="smart-router", help="Set up the Luna/Sol router",
                             setup_fn=_cli_parser, handler_fn=lambda args: _cli_setup(ctx))
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


def _cli_parser(parser):
    parser.add_subparsers(dest="smart_router_command").add_parser("setup", help="Choose and check the OpenAI API key")


def _cli_setup(ctx) -> int:
    import getpass
    import sys

    from . import hermes_api, key_setup

    if not sys.stdin.isatty():
        print("Run `hermes smart-router setup` in a terminal.")
        return 1
    io = key_setup.Io(say=print, ask_secret=getpass.getpass,
                      confirm=lambda prompt: input(prompt).strip().lower() in ("", "y", "yes"))
    try:
        return key_setup.run(io, secret=hermes_api.secret, check=hermes_api.key_works, save_key=hermes_api.save_env,
                             choose=lambda name: ctx.set_config("api_key_env", name))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Nothing was changed.")
        return 1
