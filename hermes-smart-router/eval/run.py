"""Run the agentic scenarios through a real Hermes agent on the Codex subscription.

    HERMES_HOME=~/.hermes PYTHONPATH=<hermes-agent> <hermes-venv>/bin/python eval/run.py --mode smart --out eval/results/smart-1.json

Modes: ``luna`` and ``sol`` are plain Hermes on one model; ``smart`` is Hermes on Sol with this plugin routing (needs
the plugin enabled in the profile and an OpenAI API key). Each scenario runs in a fresh copy of its workspace with the
terminal and file tools; follow-up turns continue the same session. Costs are API-equivalent USD from Hermes's
official price snapshot, Decisions API calls included.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

EVAL = Path(__file__).resolve().parent
SCENARIOS = EVAL / "agentic"
MODELS = {"luna": "gpt-6-luna", "sol": "gpt-6.1-sol", "smart": "gpt-6.1-sol"}
DECISIONS_USD_PER_INPUT_TOKEN = 0.10 / 1e6


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODELS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ids", default="", help="comma-separated scenario ids (default: all)")
    parser.add_argument("--effort", default="xhigh")
    args = parser.parse_args()
    args.out = args.out.resolve()

    sys.path.insert(0, str(SCENARIOS))
    from grade import grade

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
    calls: list[dict] = []
    decision_tokens: list[int] = []
    manager._hooks.setdefault("post_api_request", []).append(
        lambda **kw: calls.append({"model": kw.get("response_model") or "", "usage": kw.get("usage") or {}}))

    if args.mode == "smart":
        if router is None:
            raise SystemExit("hermes-smart-router is not loaded in this profile")
        from hermes_plugins.hermes_smart_router import decisions, hermes_api
        from agent.secret_scope import get_secret

        @contextmanager
        def recording_open(request, timeout):
            with decisions._open(request, timeout=timeout) as response:
                payload = response.read()
            decision_tokens.append(int(json.loads(payload).get("usage", {}).get("input_tokens") or 0))
            yield io.BytesIO(payload)

        def classify(history, message, session_id):
            key = get_secret(router.settings.api_key_env)
            if not key:
                raise SystemExit("no OpenAI API key for the Decisions API")
            return decisions.classify(history, message, api_key=key, session_id=session_id,
                                      timeout=hermes_api.DECISIONS_TIMEOUT_S, open_url=recording_open)

        router._classify = classify
    else:
        register_transport("codex_responses", ResponsesApiTransport)

    def cost(model: str, usage: dict) -> float:
        canonical = CanonicalUsage(**{k: int(usage.get(k) or 0) for k in
                                      ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")})
        result = estimate_usage_cost(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model), canonical, provider="openai")
        return float(result.amount_usd or 0)

    runtime = resolve_runtime_provider(requested="openai-codex", target_model=MODELS[args.mode])
    scenarios = json.loads((SCENARIOS / "scenarios.json").read_text())
    if args.ids:
        scenarios = [s for s in scenarios if s["id"] in args.ids.split(",")]
    rows = []
    for scenario in scenarios:
        calls.clear()
        decision_tokens.clear()
        workspace = Path(tempfile.mkdtemp(prefix=f"eval-{scenario['id']}-"))
        shutil.copytree(SCENARIOS / scenario["id"] / "workspace", workspace, dirs_exist_ok=True)
        os.chdir(workspace)
        agent = AIAgent(model=MODELS[args.mode], provider=runtime["provider"], api_mode=runtime["api_mode"],
                        base_url=runtime["base_url"], api_key=runtime["api_key"], enabled_toolsets=["terminal", "file"],
                        cwd=str(workspace), session_id=f"eval-{args.mode}-{uuid.uuid4().hex[:8]}", platform="cli",
                        quiet_mode=True, skip_memory=True, skip_context_files=True, skip_background_review=True,
                        load_soul_identity=False, reasoning_config={"effort": args.effort}, max_iterations=60)
        started, history, responses, turn_models, error = time.monotonic(), None, [], [], None
        try:
            for prompt in scenario["turns"]:
                before = len(calls)
                result = agent.run_conversation(prompt, conversation_history=history)
                history = result.get("messages", [])
                responses.append(str(result.get("final_response") or ""))
                turn_models.append(sorted({c["model"] for c in calls[before:]}))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            agent.close()
        seconds = time.monotonic() - started
        responses += [""] * (len(scenario["turns"]) - len(responses))
        os.chdir(EVAL)
        parts = grade(scenario["id"], workspace, responses)
        shutil.rmtree(workspace, ignore_errors=True)
        rows.append({
            "id": scenario["id"], "mode": args.mode, "score": round(sum(parts.values()) / len(parts), 4),
            "parts": parts, "seconds": round(seconds, 1), "turn_models": turn_models, "api_calls": len(calls),
            "llm_usd": round(sum(cost(c["model"], c["usage"]) for c in calls), 6),
            "decisions_usd": round(sum(decision_tokens) * DECISIONS_USD_PER_INPUT_TOKEN, 6), "error": error,
            "answers": [response.strip()[-400:] for response in responses],
        })
        print(json.dumps(rows[-1]), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"mode": args.mode, "effort": args.effort, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
