"""Hermes Subagent Board: a pinned Telegram widget with your last background subagents."""
import logging
import os
from pathlib import Path

from .board import Board

log = logging.getLogger("hermes_subagent_board")


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
        path = Path(get_hermes_home()) / "logs" / "subagent-board.log"
        if not any(getattr(h, "baseFilename", "") == str(path) for h in log.handlers):
            h = logging.FileHandler(path)
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
            log.setLevel(logging.INFO)
    except Exception:
        pass


def register(ctx):
    _file_log()
    board = Board(ctx.get_config, _secret)
    ctx.on_unload(board.stop.set)
    board.ensure_thread()
