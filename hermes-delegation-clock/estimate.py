"""Expected duration of a subagent task: explicit 'ETA: 25m' in the goal wins, else one Decisions API call."""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.request import Request, urlopen

BUCKETS = ((5, "up to 5 minutes"), (15, "5 to 15 minutes"), (30, "15 to 30 minutes"),
           (60, "30 to 60 minutes"), (120, "more than an hour"))
_ETA = re.compile(r"\b(?:ETA|срок)\s*[:=~≈]?\s*~?\s*(\d+(?:\.\d+)?)\s*(m|min|мин|h|ч|hours?|час)", re.I)


def explicit_minutes(text: str) -> Optional[float]:
    m = _ETA.search(text or "")
    if not m:
        return None
    value = float(m.group(1))
    return value * 60 if m.group(2).lower().startswith(("h", "ч")) else value


def decisions_minutes(text: str, *, url: str, api_key: str, model: str, timeout: float, quantile: float = 0.5) -> Optional[float]:
    """Smallest bucket whose cumulative probability reaches `quantile` (median by default)."""
    body = {
        "model": model,
        "input": [{"role": "user", "content": text[-6000:] or "(empty)"}],
        "questions": [{
            "type": "choice", "name": "duration",
            "instructions": ("This is a task handed to an autonomous subagent with shell, cloud CLI, repo and "
                             "web access. Estimate the wall-clock time until it can report back, including "
                             "waiting for external jobs (CI runs, deploys, applies) it has to watch."),
            "choices": [{"value": str(m), "description": d} for m, d in BUCKETS],
        }],
    }
    req = Request(url, data=json.dumps(body, ensure_ascii=False).encode(), method="POST",
                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        answers = json.loads(resp.read(65536)).get("answers") or []
    probs = {p.get("value"): float(p.get("probability") or 0) for p in (answers[0].get("probabilities") or [])} \
        if answers and isinstance(answers[0], dict) else {}
    if not probs:
        return None
    total = 0.0
    for minutes, _ in BUCKETS:
        total += probs.get(str(minutes), 0.0)
        if total >= quantile:
            return float(minutes)
    return float(BUCKETS[-1][0])
