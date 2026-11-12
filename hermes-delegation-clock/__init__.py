"""Hermes Delegation Clock: time awareness and delegation accountability on native Hermes pieces."""
import logging
import os
from pathlib import Path

from .clock import Clock

log = logging.getLogger("hermes_delegation_clock")

DEADLINE_SCHEMA = {
    "name": "subagent_deadline",
    "description": ("Re-plan the expected finish time of one of your running background subagents after you "
                    "checked it and decided to let it continue. The clock wakes you again when the new "
                    "deadline passes. Tip: when you know the wall-clock time of a task (a CI run, a deploy), "
                    "write `ETA: <N>m` in the delegate_task goal; otherwise the clock estimates it."),
    "parameters": {
        "type": "object",
        "properties": {
            "delegation_id": {"type": "string", "description": "deleg_… id from the Active subagents block"},
            "minutes": {"type": "number", "description": "Minutes from now until you expect the result (1-240)"},
            "reason": {"type": "string", "description": "Why it needs this long, in a few words"},
        },
        "required": ["delegation_id", "minutes", "reason"],
    },
}


def _secret(name: str):
    try:
        from agent.secret_scope import get_secret
        value = get_secret(name)
        if value:
            return value
    except Exception:
        pass
    value = os.environ.get(name)
    if value:
        return value
    try:
        from hermes_constants import get_hermes_home
        for line in (Path(get_hermes_home()) / ".env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except Exception:
        pass
    return None


def _file_log():
    try:
        from hermes_constants import get_hermes_home
        path = Path(get_hermes_home()) / "logs" / "delegation-clock.log"
        if not any(getattr(h, "baseFilename", "") == str(path) for h in log.handlers):
            h = logging.FileHandler(path)
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
            log.setLevel(logging.INFO)
    except Exception:
        pass


def register(ctx):
    _file_log()
    log.info("registered in pid %s", os.getpid())
    clock = Clock(ctx.get_config, _secret)
    clock.inject = lambda text, key: ctx.inject_message(text, session_key=key)
    ctx.register_hook("pre_llm_call", clock.on_turn)
    ctx.register_tool(name="subagent_deadline", toolset="delegation", schema=DEADLINE_SCHEMA,
                      handler=clock.deadline, description=DEADLINE_SCHEMA["description"], emoji="⏰")
    ctx.on_unload(clock.stop.set)
    clock.ensure_thread()
