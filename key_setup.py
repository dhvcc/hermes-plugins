"""`hermes smart-router setup`: pick and check the OpenAI key used for the Decisions API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

OPENAI_KEY = "OPENAI_API_KEY"
VOICE_KEY = "VOICE_TOOLS_OPENAI_KEY"


@dataclass
class Io:
    say: Callable[[str], None]
    confirm: Callable[[str], bool]
    ask_secret: Callable[[str], str]


def run(io: Io, *, secret: Callable[[str], Optional[str]], check: Callable[[str], bool],
        save_key: Callable[[str, str], None], choose: Callable[[str], None]) -> int:
    """Use a working OPENAI_API_KEY, else the voice key if the user agrees, else ask for a key. 0 when ready."""
    current = secret(OPENAI_KEY)
    if current:
        if _works(io, check, current):
            choose(OPENAI_KEY)
            return _ready(io)
        io.say("OPENAI_API_KEY is set, but OpenAI rejected it.")
    voice = secret(VOICE_KEY)
    if voice and io.confirm("Use the OpenAI key you set for voice (VOICE_TOOLS_OPENAI_KEY)? [Y/n] "):
        if _works(io, check, voice):
            choose(VOICE_KEY)
            return _ready(io)
        io.say("OpenAI rejected the voice key.")
    key = io.ask_secret("Paste an OpenAI API key (https://platform.openai.com/api-keys), or press Enter to skip: ").strip()
    if not key:
        io.say("Skipped. The router stays off until a key is set; run `hermes smart-router setup` again.")
        return 1
    if not _works(io, check, key):
        io.say("OpenAI rejected this key. Nothing was saved.")
        return 1
    save_key(OPENAI_KEY, key)
    choose(OPENAI_KEY)
    return _ready(io)


def _works(io: Io, check: Callable[[str], bool], key: str) -> bool:
    io.say("Checking the key with OpenAI...")
    try:
        return check(key)
    except Exception as exc:
        io.say(f"Could not reach OpenAI ({type(exc).__name__}).")
        return False


def _ready(io: Io) -> int:
    io.say("Ready. Restart Hermes, and the gateway if you use one, to apply.")
    return 0
