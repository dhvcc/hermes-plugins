import unittest

from support import LUNA, SOL, Clock, fake_price
from hermes_smart_router import router as router_module
from hermes_smart_router.router import Router
from hermes_smart_router.settings import Settings

HELLO = [{"role": "user", "content": "hi"}]


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.models = frozenset({LUNA, SOL})
        self.tokens = 1_000
        self.router = self.make()

    def make(self, remote_tier=None, **settings):
        return Router(Settings(**settings), price=fake_price, catalog=lambda: self.models,
                      estimate_tokens=lambda messages, tools: self.tokens,
                      clamp_effort=lambda model, effort: effort, remote_tier=remote_tier, clock=self.clock)

    def turn(self, prompt="What is 2+2?", turn_id="t1", sid="s", model=SOL, **extra):
        self.router.on_turn(session_id=sid, turn_id=turn_id, user_message=prompt, model=model, platform="cli",
                            **extra)

    def plan(self, model=SOL, messages=HELLO, sid="s", effort="xhigh", **params):
        base = dict(provider="openai-codex", is_codex_backend=True, session_id=sid,
                    reasoning_config={"effort": effort, "enabled": True})
        return self.router.plan(model, messages, None, dict(base, **params))

    def succeed(self, model, prompt_tokens, sid="s", turn_id="t1", output=500):
        self.router.on_api_success(session_id=sid, turn_id=turn_id, model=SOL, response_model=model,
                                   usage={"prompt_tokens": prompt_tokens, "output_tokens": output})

    def test_light_turn_routes_to_light_model_with_light_effort(self):
        self.turn()
        self.assertEqual(self.plan(), (LUNA, {"effort": "medium", "enabled": True}))

    def test_standard_turn_uses_standard_effort_capped_by_user_effort(self):
        self.turn("Explain why the sky is blue")
        self.assertEqual(self.plan()[1]["effort"], "high")
        self.turn("Explain why grass is green", turn_id="t2")
        self.assertEqual(self.plan(effort="low")[1]["effort"], "low")

    def test_heavy_turn_on_heavy_base_is_native(self):
        self.turn("Refactor the billing module")
        self.assertIsNone(self.plan())

    def test_heavy_turn_on_light_base_escalates_with_user_effort(self):
        self.turn("Refactor the billing module", model=LUNA)
        self.assertEqual(self.plan(model=LUNA, effort="max"), (SOL, {"effort": "max", "enabled": True}))

    def test_decision_is_pinned_for_the_whole_turn(self):
        self.turn()
        first = self.plan()
        self.tokens = 500_000
        self.assertEqual(self.plan(messages=HELLO * 50), first)
        self.turn("Refactor the billing module", turn_id="t2")
        self.assertIsNone(self.plan())

    def test_repeated_pre_llm_call_for_same_turn_is_ignored(self):
        self.turn()
        self.plan()
        self.turn("Refactor everything")
        self.assertEqual(self.plan()[0], LUNA)

    def test_shadow_mode_never_changes_requests(self):
        self.router = self.make(mode="shadow")
        self.turn()
        with self.assertLogs("hermes_smart_router", "INFO") as logs:
            self.assertIsNone(self.plan())
        self.assertIn("[shadow]", logs.output[0])
        self.assertIsNone(self.plan())

    def test_untracked_sessions_stay_native(self):
        self.assertIsNone(self.plan())
        self.router.on_turn(session_id="s", turn_id="t1", user_message="hi", model=SOL, platform="cron")
        self.assertIsNone(self.plan())
        self.router.on_turn(session_id="s", turn_id="t1", user_message="hi", model=SOL, platform="cli",
                            parent_session_id="parent")
        self.assertIsNone(self.plan())
        self.router.on_turn(session_id="s", turn_id="t1", user_message="hi", model="gpt-6-astra", platform="cli")
        self.assertIsNone(self.plan())

    def test_ineligible_requests_stay_native(self):
        self.turn()
        cases = [dict(provider="openai"), dict(is_codex_backend=False), dict(request_overrides={"x": 1}),
                 dict(context_management=[{"type": "compaction"}]),
                 dict(reasoning_config={"effort": "xhigh", "enabled": False})]
        for params in cases:
            with self.subTest(params=params):
                self.assertIsNone(self.plan(**params))
        messages = [
            [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:"}}]}],
            [{"role": "assistant", "content": "x", "codex_reasoning_items": [{"type": "compaction"}]}],
            ["not a dict"],
        ]
        for history in messages:
            with self.subTest(history=history):
                self.assertIsNone(self.plan(messages=history))
        self.assertIsNone(self.plan(model="gpt-6-astra"))

    def test_error_on_routed_call_returns_rest_of_turn_to_hermes(self):
        self.turn()
        self.assertEqual(self.plan()[0], LUNA)
        self.router.on_api_error(session_id="s", model=SOL, status_code=500, error={"message": "boom"},
                                 request={"model": LUNA})
        self.assertIsNone(self.plan())
        self.turn(turn_id="t2")
        self.assertEqual(self.plan()[0], LUNA)

    def test_unavailable_model_is_parked_then_retried(self):
        self.turn()
        self.plan()
        with self.assertLogs("hermes_smart_router", "WARNING"):
            self.router.on_api_error(session_id="s", model=SOL, status_code=404,
                                     error={"message": "model not found"})
        self.turn(turn_id="t2")
        self.assertEqual(self.plan(), (SOL, {"effort": "medium", "enabled": True}))
        self.clock.now += router_module.UNAVAILABLE_BLOCK_S + 1
        self.turn(turn_id="t3")
        self.assertEqual(self.plan()[0], LUNA)

    def test_exhausted_model_is_parked(self):
        self.turn()
        self.plan()
        with self.assertLogs("hermes_smart_router", "WARNING"):
            self.router.on_api_error(session_id="s", model=SOL, status_code=429,
                                     error={"message": "model exhausted"})
        self.turn(turn_id="t2")
        self.assertEqual(self.plan()[0], SOL)
        self.clock.now += router_module.EXHAUSTED_BLOCK_S + 1
        self.turn(turn_id="t3")
        self.assertEqual(self.plan()[0], LUNA)

    def test_native_and_fallback_errors_do_not_park_models(self):
        self.turn("Refactor the billing module")
        self.plan()
        self.router.on_api_error(session_id="s", model=SOL, status_code=404, error={"message": "model not found"})
        self.turn(turn_id="t2")
        self.plan()
        self.router.on_api_error(session_id="s", model=SOL, status_code=404, error={"message": "gone"},
                                 request={"model": "deepseek/deepseek-v4.1-flash"})
        self.assertEqual(self.plan()[0], LUNA)
        self.turn(turn_id="t3")
        self.assertEqual(self.plan()[0], LUNA)

    def test_model_missing_from_catalog_is_not_used(self):
        self.models = frozenset({SOL})
        self.turn()
        self.assertEqual(self.plan(), (SOL, {"effort": "medium", "enabled": True}))
        self.router = self.make()
        self.models = frozenset({LUNA})
        self.turn("Refactor it", model=LUNA, turn_id="t2")
        self.assertIsNone(self.plan(model=LUNA))

    def test_success_records_cache_under_served_model(self):
        self.turn()
        self.plan()
        self.succeed("gpt-6-luna-2026-09-22", 12_000)
        self.succeed("deepseek-v4.1-flash", 99_000)
        session = self.router._sessions["s"]
        self.assertEqual(session.cache[LUNA].prefix_tokens, 12_000)
        self.assertNotIn(SOL, session.cache)
        self.assertEqual(session.calls, 1)

    def test_shadow_attributes_cache_to_the_native_model(self):
        self.router = self.make(mode="shadow")
        self.turn()
        self.plan()
        self.router.on_api_success(session_id="s", turn_id="t1", model=SOL, response_model=None,
                                   usage={"prompt_tokens": 7_000})
        self.assertEqual(self.router._sessions["s"].cache[SOL].prefix_tokens, 7_000)

    def test_turn_statistics_feed_the_next_decision(self):
        self.turn()
        self.plan()
        self.clock.now += 30
        self.succeed(LUNA, 2_000)
        self.clock.now += 100
        self.turn(turn_id="t2")
        stats = self.router._sessions["s"].stats
        self.assertAlmostEqual(stats.turn_s, 0.6 * 20 + 0.4 * 30)
        self.assertAlmostEqual(stats.gap_s, 0.6 * 60 + 0.4 * 100)

    def test_large_warm_heavy_cache_is_protected(self):
        self.tokens = 150_000
        for i in range(3):
            self.turn("Refactor the billing module", turn_id=f"h{i}")
            self.assertIsNone(self.plan())
            self.succeed(SOL, 150_000, turn_id=f"h{i}")
            self.clock.now += 20
        self.clock.now += 230
        self.turn("Thanks!", turn_id="light")
        self.assertEqual(self.plan(), (SOL, {"effort": "medium", "enabled": True}))

    def test_hooks_never_raise(self):
        self.turn()
        self.plan()
        self.assertIsNone(self.router.on_api_success(session_id="s", turn_id="t1", response_model=LUNA,
                                                     usage={"prompt_tokens": "lots"}))
        self.assertIsNone(self.router.on_turn(session_id="s", turn_id="t9", user_message=object(), model=SOL,
                                              platform="cli"))
        self.assertIsNone(self.router.on_api_error(session_id="s", status_code=404, error="not a dict"))

    def test_state_survives_turns_and_is_evicted_by_capacity_and_idleness(self):
        self.turn()
        self.plan()
        self.succeed(LUNA, 5_000)
        self.turn(turn_id="t2")
        self.assertIn(LUNA, self.router._sessions["s"].cache)
        for i in range(router_module.MAX_SESSIONS + 5):
            self.turn(sid=f"s{i}")
        self.assertEqual(len(self.router._sessions), router_module.MAX_SESSIONS)
        self.assertNotIn("s0", self.router._sessions)
        self.turn(sid="s5")
        self.clock.now += router_module.SESSION_IDLE_S + 1
        self.turn(sid="fresh")
        self.assertEqual(list(self.router._sessions), ["fresh"])

    def test_remote_tier_can_raise_but_not_lower_the_local_tier(self):
        seen = []

        def remote(history, message, sid):
            seen.append((history, message, sid))
            return "heavy", 0.4

        self.router = self.make(remote_tier=remote)
        self.router.on_turn(session_id="s", turn_id="t1", user_message="ok", model=SOL, platform="cli",
                            conversation_history=[{"role": "user", "content": "plan"}])
        self.assertIsNone(self.plan())
        self.assertEqual(seen, [([{"role": "user", "content": "plan"}], "ok", "s")])
        self.assertIn("decisions heavy", self.router._sessions["s"].tier_source)
        self.router = self.make(remote_tier=lambda *args: ("light", 0.01))
        self.turn("Refactor the billing module")
        self.assertIsNone(self.plan())

    def test_missing_remote_tier_falls_back_to_local(self):
        for answer in (("expert", 0.9), None):
            self.router = self.make(remote_tier=lambda *args, answer=answer: answer)
            self.turn()
            self.assertEqual(self.plan()[0], LUNA)

    def test_remote_failure_cools_down_then_retries(self):
        calls = []

        def remote(*args):
            calls.append(1)
            raise TimeoutError

        self.router = self.make(remote_tier=remote)
        with self.assertLogs("hermes_smart_router", "WARNING"):
            self.turn()
        self.assertEqual(self.plan()[0], LUNA)
        self.turn(turn_id="t2")
        self.assertEqual(len(calls), 1)
        self.clock.now += router_module.REMOTE_COOLDOWN_S + 1
        with self.assertLogs("hermes_smart_router", "WARNING"):
            self.turn(turn_id="t3")
        self.assertEqual(len(calls), 2)

    def test_rejected_key_disables_remote_until_restart(self):
        calls = []

        class Rejected(Exception):
            code = 401

        def remote(*args):
            calls.append(1)
            raise Rejected

        self.router = self.make(remote_tier=remote)
        with self.assertLogs("hermes_smart_router", "WARNING"):
            self.turn()
        self.clock.now += router_module.REMOTE_COOLDOWN_S + 1
        self.turn(turn_id="t2")
        self.assertEqual((len(calls), self.plan()[0]), (1, LUNA))

    def test_abandon_turn(self):
        self.turn()
        self.plan()
        self.router.abandon_turn("s")
        self.assertIsNone(self.plan())


if __name__ == "__main__":
    unittest.main()
