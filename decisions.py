"""Turn tier from the OpenAI Decisions API. One bounded call per turn, no retries."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .classifier import HEAVY, LIGHT, STANDARD, message_text

API_URL = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
CONTEXT_MESSAGES = 6
MESSAGE_CHARS = 2000
MAX_RESPONSE_BYTES = 65536
HEAVY_AT = 0.3
LIGHT_AT = 0.6

QUESTION = {
    "type": "choice",
    "name": "tier",
    "instructions": (
        "Pick the smallest model tier that will handle the LAST user message well, given the conversation. "
        "A short follow-up such as 'continue' or 'fix it' needs the tier of the work it continues."
    ),
    "choices": [
        {"value": LIGHT, "description": "Small talk, quick facts, recall from the conversation, trivial edits."},
        {"value": STANDARD, "description": "Everyday writing, summaries, explanations, simple code or tool use."},
        {"value": HEAVY, "description": "Real coding or debugging, architecture, security, math, multi-step "
                                        "planning, high-stakes or ambiguous decisions."},
    ],
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "redirect refused", headers, fp)


_open = build_opener(_NoRedirect).open


def build_input(history: Any, user_message: Any) -> list[dict]:
    """Last few plain-text user/assistant messages plus the new one; tool traffic is left out."""
    items = []
    for message in history if isinstance(history, list) else ():
        if isinstance(message, dict) and message.get("role") in ("user", "assistant"):
            text = message_text(message.get("content")).strip()
            if text:
                items.append({"role": message["role"], "content": text[-MESSAGE_CHARS:]})
    current = message_text(user_message)
    if items and items[-1] == {"role": "user", "content": current.strip()[-MESSAGE_CHARS:]}:
        items.pop()
    items = items[-CONTEXT_MESSAGES:]
    items.append({"role": "user", "content": current[-MESSAGE_CHARS * 2:] or "(empty)"})
    return items


def classify(history: Any, user_message: Any, *, api_key: str, session_id: str, timeout: float,
             open_url: Callable = _open) -> Optional[tuple[str, float]]:
    """(tier, P(heavy)), or None on a refusal or an unusable answer. Network errors propagate.

    The tier leans heavy: any real chance that the turn needs the strong model counts.
    """
    body = {
        "model": MODEL,
        "input": build_input(history, user_message),
        "questions": [QUESTION],
        "prompt_cache_key": "hsr-" + hashlib.sha256(session_id.encode()).hexdigest()[:40],
    }
    request = Request(API_URL, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with open_url(request, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        return None
    answers = json.loads(payload).get("answers")
    answer = answers[0] if isinstance(answers, list) and answers else None
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None
    probability = {item.get("value"): item.get("probability") for item in answer.get("probabilities") or ()
                   if isinstance(item, dict) and isinstance(item.get("probability"), (int, float))}
    if not probability.keys() & {LIGHT, STANDARD, HEAVY}:
        return None
    heavy = float(probability.get(HEAVY, 0.0))
    if heavy >= HEAVY_AT:
        return HEAVY, heavy
    return (LIGHT if probability.get(LIGHT, 0.0) >= LIGHT_AT else STANDARD), heavy
