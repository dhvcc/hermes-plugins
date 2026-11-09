"""Run an eval task file through a real Hermes agent on the Codex subscription.

    HERMES_HOME=~/.hermes PYTHONPATH=<hermes-agent> <hermes-venv>/bin/python eval/run.py --mode smart \
        --tasks eval/tasks.json --out eval/results/routerarena/smart.json

Modes: ``luna`` and ``sol`` run Hermes natively on one model; ``smart`` runs Sol with this plugin
routing. Needs the plugin installed and enabled in the profile, and OPENAI_API_KEY for ``smart``.
Costs are API-equivalent USD from Hermes's official price snapshot, including Decisions API calls.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYS_PATH_ROOT = str(ROOT)
MODELS = {"luna": "gpt-6-luna", "sol": "gpt-6.1-sol", "smart": "gpt-6.1-sol"}
DECISIONS_INPUT_USD_PER_TOKEN = 0.10 / 1e6


def prompt(task: dict) -> str:
    if "prompt" in task:
        return task["prompt"]
    parts = [task["context"], task["question"]] if task["context"] else [task["question"]]
    if task["options"]:
        parts.append("Options:\n" + "\n".join(f"{chr(65 + i)}. {option}" for i, option in enumerate(task["options"])))
        parts.append("Give the final answer on the last line exactly as `ANSWER: <letter>`.")
    else:
        parts.append("Give the final answer on the last line exactly as `ANSWER: <number>`.")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODELS), required=True)
    parser.add_argument("--tasks", type=Path, default=ROOT / "tasks.json")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out, args.tasks = args.out.resolve(), args.tasks.resolve()

    import sys
    sys.path.insert(0, SYS_PATH_ROOT)
    from grading import ASSISTANT, grade
    import hermes_bootstrap  # noqa: F401
    from agent.transports import register_transport
    from agent.transports.codex import ResponsesApiTransport
    from agent.usage_pricing import CanonicalUsage, estimate_usage_cost
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from run_agent import AIAgent

    manager = get_plugin_manager()
    manager.discover_and_load()
    router = next((cb.__self__ for cb in manager._hooks.get("pre_llm_call", [])
                   if type(getattr(cb, "__self__", None)).__name__ == "Router"), None)
    if args.mode == "smart":
        if router is None:
            raise SystemExit("hermes-smart-router is not loaded in this profile")
    else:
        register_transport("codex_responses", ResponsesApiTransport)

    calls: list[dict] = []
    decision_tokens: list[int] = []
    manager._hooks.setdefault("post_api_request", []).append(
        lambda **kw: calls.append({"model": kw.get("response_model") or "", "usage": kw.get("usage") or {}}))

    if router is not None and args.mode == "smart":
        from hermes_plugins.hermes_smart_router import decisions, hermes_api

        @contextmanager
        def recording_open(request, timeout):
            with decisions._open(request, timeout=timeout) as response:
                payload = response.read()
            decision_tokens.append(int(json.loads(payload).get("usage", {}).get("input_tokens") or 0))
            yield io.BytesIO(payload)

        def classify(history, message, session_id):
            from agent.secret_scope import get_secret
            key = next((k for k in map(get_secret, hermes_api.API_KEY_NAMES) if k), None)
            if not key:
                raise SystemExit("no OpenAI API key for the Decisions API")
            return decisions.classify(history, message, api_key=key, session_id=session_id,
                                      timeout=hermes_api.DECISIONS_TIMEOUT_S, open_url=recording_open)

        router._classify = classify

    def cost(model: str, usage: dict) -> float:
        canonical = CanonicalUsage(**{k: int(usage.get(k) or 0) for k in
                                      ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")})
        result = estimate_usage_cost(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model), canonical, provider="openai")
        return float(result.amount_usd or 0)

    runtime = resolve_runtime_provider(requested="openai-codex", target_model=MODELS[args.mode])
    tasks = json.loads(args.tasks.read_text())["tasks"]
    rows = []
    for task in tasks:
        calls.clear()
        decision_tokens.clear()
        workspace = None
        if "workspace" in task:
            workspace = Path(tempfile.mkdtemp(prefix=f"eval-{task['id']}-"))
            shutil.copytree(ASSISTANT / task["workspace"] / "workspace", workspace, dirs_exist_ok=True)
            os.chdir(workspace)
        agent = AIAgent(model=MODELS[args.mode], provider=runtime["provider"], api_mode=runtime["api_mode"],
                        base_url=runtime["base_url"], api_key=runtime["api_key"],
                        enabled_toolsets=["terminal", "file"] if workspace else [],
                        cwd=str(workspace) if workspace else None,
                        session_id=f"eval-{args.mode}-{uuid.uuid4().hex[:8]}", platform="cli", quiet_mode=True,
                        skip_memory=True, skip_context_files=True, skip_background_review=True,
                        load_soul_identity=False, reasoning_config={"effort": args.effort},
                        max_iterations=40 if workspace else 3)
        started = time.monotonic()
        try:
            result = agent.run_conversation(prompt(task))
            response, error = str(result.get("final_response") or ""), None
        except Exception as exc:
            response, error = "", f"{type(exc).__name__}: {exc}"[:300]
        finally:
            agent.close()
        rows.append({
            "id": task["id"], "difficulty": task["difficulty"], "mode": args.mode,
            "correct": grade(task, response, workspace), "seconds": round(time.monotonic() - started, 2),
            "models": sorted({c["model"] for c in calls}),
            "llm_usd": round(sum(cost(c["model"], c["usage"]) for c in calls), 6),
            "decisions_usd": round(sum(decision_tokens) * DECISIONS_INPUT_USD_PER_TOKEN, 6),
            "output_tokens": sum(int(c["usage"].get("output_tokens") or 0) for c in calls),
            "answer_tail": response.strip()[-120:], "error": error,
        })
        if workspace:
            os.chdir(ROOT)
            shutil.rmtree(workspace, ignore_errors=True)
        print(json.dumps(rows[-1]), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"mode": args.mode, "effort": args.effort, "tasks": args.tasks.name, "rows": rows},
                                   indent=2))


if __name__ == "__main__":
    main()
