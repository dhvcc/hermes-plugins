"""Contract tests against the installed Hermes runtime; no provider requests. Skipped without Hermes."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from support import LUNA, SOL, fake_classify
import hermes_smart_router
from hermes_smart_router import hermes_api
from hermes_smart_router.router import Router
from hermes_smart_router.settings import Settings
from hermes_smart_router.transport import install_transport

try:
    from agent.transports import get_transport
    from agent.transports.codex import ResponsesApiTransport
except ImportError:
    ResponsesApiTransport = None


class Context:
    def __init__(self, config=None):
        self.config = config or {}
        self.hooks = {}
        self.unloads = []

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def on_unload(self, callback):
        self.unloads.append(callback)

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def unload(self):
        for callback in self.unloads:
            callback()


@unittest.skipIf(ResponsesApiTransport is None, "Hermes runtime not available")
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.router = Router(Settings(), classify=fake_classify,
                             catalog=lambda: frozenset({LUNA, SOL, LUNA + "-900k", SOL + "-900k"}))
        self.ctx = Context()
        install_transport(self.ctx, self.router)
        self.addCleanup(self.ctx.unload)
        self.transport = get_transport("codex_responses")

    def turn(self, prompt="What is 2+2?", turn_id="t1"):
        self.router.on_turn(session_id="a", turn_id=turn_id, user_message=prompt, model=SOL, platform="cli")

    def build(self, messages=None, **params):
        base = dict(provider="openai-codex", is_codex_backend=True, base_url="https://chatgpt.com/backend-api/codex",
                    session_id="a", reasoning_config={"effort": "xhigh"})
        return self.transport.build_kwargs(SOL, messages or [{"role": "user", "content": "hi"}], **dict(base, **params))

    def response(self):
        return SimpleNamespace(status="completed", usage=None, output=[
            SimpleNamespace(type="reasoning", id="rs_test", encrypted_content="synthetic", summary=[]),
            SimpleNamespace(type="message", id="msg_test", role="assistant", status="completed",
                            content=[SimpleNamespace(type="output_text", text="ok")]),
        ])

    def test_native_normalizer_stamps_the_routed_model(self):
        self.turn()
        request = self.build()
        self.assertEqual((request["model"], request["reasoning"]["effort"]), (LUNA, "medium"))
        normalized = self.transport.normalize_response(self.response())
        self.assertEqual(normalized.provider_data["codex_reasoning_items"][0]["_issuer_model"], LUNA)

    def test_reasoning_replayed_on_same_model_and_dropped_on_switch(self):
        self.turn()
        self.build()
        normalized = self.transport.normalize_response(self.response())
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok", **normalized.provider_data},
                   {"role": "user", "content": "thanks"}]
        self.turn("thanks", turn_id="t2")
        self.assertTrue(any(item.get("encrypted_content") for item in self.build(history)["input"]))
        self.turn("Run a security audit of this design", turn_id="t3")
        switched = self.build(history)
        self.assertEqual(switched["model"], SOL)
        self.assertFalse(any(item.get("encrypted_content") for item in switched["input"]))

    def test_unload_restores_registry_and_cached_instances(self):
        self.turn()
        self.assertEqual(self.build()["model"], LUNA)
        self.ctx.unload()
        self.assertIs(type(get_transport("codex_responses")), ResponsesApiTransport)
        self.assertEqual(self.build()["model"], SOL)

    def test_other_profile_is_not_routed(self):
        self.turn()
        with patch.dict(os.environ, HERMES_HOME="/tmp/other-hermes-profile"):
            self.assertEqual(self.build()["model"], SOL)

    def test_unsupported_requests_stay_native(self):
        self.turn()
        for params in [{"context_management": [{"type": "compaction"}]}, {"request_overrides": {"service_tier": "x"}}]:
            self.assertEqual(self.build(**params)["model"], SOL)
        image = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/x.png"}}]}]
        self.assertEqual(self.build(image)["model"], SOL)

    def test_long_context_variant_is_routed_and_stripped_on_the_wire(self):
        self.router.on_turn(session_id="a", turn_id="t1", user_message="What is 2+2?", model=SOL + "-900k",
                            platform="cli")
        request = self.transport.build_kwargs(SOL + "-900k", [{"role": "user", "content": "hi"}], provider="openai-codex",
                                              is_codex_backend=True, base_url="https://chatgpt.com/backend-api/codex",
                                              session_id="a", reasoning_config={"effort": "xhigh"})
        self.assertEqual(request["model"], LUNA)
        normalized = self.transport.normalize_response(self.response())
        self.assertEqual(normalized.provider_data["codex_reasoning_items"][0]["_issuer_model"], LUNA)

    def test_large_context_is_routed(self):
        self.turn()
        self.assertEqual(self.build([{"role": "user", "content": "x" * 400_000}])["model"], LUNA)

    def test_planning_failure_builds_native_request_and_stamp(self):
        self.turn()
        with patch.object(self.router, "plan", side_effect=RuntimeError("boom")):
            self.assertEqual(self.build()["model"], SOL)
        self.assertEqual(self.transport._last_issuer_model, SOL)

    def test_shadow_leaves_transport_native(self):
        self.router.settings = Settings(mode="shadow")
        self.turn()
        self.assertEqual(self.build()["model"], SOL)

    def test_refuses_to_run_in_a_plugin_host(self):
        with patch.dict(os.environ, {"HERMES_PLUGIN_HOST_PROCESS": "1"}), self.assertRaises(RuntimeError):
            install_transport(Context(), Router(Settings(), classify=fake_classify))

    def test_refuses_mismatched_context_windows_and_foreign_transport(self):
        current = type(get_transport("codex_responses"))
        with patch.object(hermes_api, "context_window", side_effect=lambda model: 900_000 if "sol" in model else 272_000):
            with self.assertRaises(RuntimeError):
                install_transport(Context(), Router(Settings(), classify=fake_classify))
        with self.assertRaises(RuntimeError):
            install_transport(Context(), self.router)
        self.assertIs(type(get_transport("codex_responses")), current)


@unittest.skipIf(ResponsesApiTransport is None, "Hermes runtime not available")
class HermesApiTests(unittest.TestCase):
    def test_official_prices_exist_and_cache_reads_are_cheaper(self):
        for model in (LUNA, SOL):
            cold, warm = hermes_api.price(model, 100_000, 0, 0), hermes_api.price(model, 100_000, 100_000, 0)
            self.assertIsNotNone(cold)
            self.assertLess(warm, cold)
        self.assertLess(hermes_api.price(LUNA, 100_000, 0, 1000), hermes_api.price(SOL, 100_000, 100_000, 1000))

    def test_long_context_tier_is_priced(self):
        self.assertGreater(hermes_api.price(SOL, 300_000, 0, 0), 2 * hermes_api.price(SOL, 150_000, 0, 0))

    def test_efforts_and_estimates(self):
        self.assertEqual(hermes_api.clamp_effort(LUNA, "low"), "low")
        self.assertEqual(hermes_api.clamp_effort(SOL, "none"), "low")
        self.assertGreater(hermes_api.estimate_tokens([{"role": "user", "content": "hello " * 100}], None), 50)
        self.assertEqual(hermes_api.context_window(LUNA), hermes_api.context_window(SOL))

    def test_decisions_without_key_is_skipped(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "VOICE_TOOLS_OPENAI_KEY": ""}):
            self.assertIsNone(hermes_api.decisions_tier([], "hi", "s"))

    def test_decisions_falls_back_to_voice_key(self):
        seen = []
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "VOICE_TOOLS_OPENAI_KEY": "sk-voice"}), \
                patch("hermes_smart_router.decisions.classify", lambda *a, api_key, **k: seen.append(api_key)):
            hermes_api.decisions_tier([], "hi", "s")
        self.assertEqual(seen, ["sk-voice"])


@unittest.skipIf(ResponsesApiTransport is None, "Hermes runtime not available")
class RegisterTests(unittest.TestCase):
    def test_invalid_settings_leave_hermes_native(self):
        ctx = Context({"mode": "balanced"})
        with self.assertLogs("hermes_smart_router", "WARNING"):
            hermes_smart_router.register(ctx)
        self.assertEqual(ctx.hooks, {})
        self.assertIs(type(get_transport("codex_responses")), ResponsesApiTransport)

    def test_register_installs_transport_and_hooks(self):
        ctx = Context()
        hermes_smart_router.register(ctx)
        self.addCleanup(ctx.unload)
        self.assertEqual(set(ctx.hooks), {"pre_llm_call", "post_api_request", "api_request_error"})
        self.assertIsNot(type(get_transport("codex_responses")), ResponsesApiTransport)


if __name__ == "__main__":
    unittest.main()
