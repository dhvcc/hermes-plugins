import unittest

from support import LUNA, SOL, fake_price
from hermes_smart_router.policy import CacheMark, Stats, choose

NOW = 10_000.0
TTL = 300.0


def decide(prompt_tokens, cache=None, **stats):
    return choose(LUNA, SOL, prompt_tokens=prompt_tokens, now=NOW, cache=cache or {},
                  stats=Stats(**stats), ttl=TTL, price=fake_price)


class PolicyTests(unittest.TestCase):
    def test_cold_start_prefers_light(self):
        choice = decide(5_000)
        self.assertEqual(choice.model, LUNA)
        self.assertLess(choice.costs[LUNA], choice.costs[SOL])

    def test_responsive_user_can_leave_warm_heavy_cache(self):
        # Sol's cache will still be warm when a heavy turn comes back, so leaving it is free.
        choice = decide(150_000, {SOL: CacheMark(150_000, NOW - 30)}, gap_s=60, turn_s=20, p_heavy=0.5)
        self.assertEqual(choice.model, LUNA)

    def test_stays_on_heavy_when_leaving_would_let_a_large_cache_expire(self):
        choice = decide(150_000, {SOL: CacheMark(150_000, NOW - 250)}, gap_s=60, turn_s=20, p_heavy=0.5)
        self.assertEqual(choice.model, SOL)
        self.assertIn("cache warm", choice.reason)

    def test_small_context_never_worth_protecting(self):
        choice = decide(3_000, {SOL: CacheMark(3_000, NOW - 250)}, gap_s=60, turn_s=20, p_heavy=0.9)
        self.assertEqual(choice.model, LUNA)

    def test_cache_that_expires_anyway_is_not_protected(self):
        choice = decide(150_000, {SOL: CacheMark(150_000, NOW - 250)}, gap_s=900, turn_s=20, p_heavy=0.5)
        self.assertEqual(choice.model, LUNA)

    def test_rarely_heavy_session_leaves_heavy_model(self):
        choice = decide(150_000, {SOL: CacheMark(150_000, NOW - 250)}, gap_s=60, turn_s=20, p_heavy=0.02)
        self.assertEqual(choice.model, LUNA)

    def test_expired_mark_is_cold(self):
        stay = decide(150_000, {SOL: CacheMark(150_000, NOW - 400)}, gap_s=60, turn_s=20, p_heavy=0.5)
        self.assertEqual(stay.model, LUNA)

    def test_unknown_pricing_falls_back_to_light(self):
        choice = choose(LUNA, "unpriced", prompt_tokens=1000, now=NOW, cache={}, stats=Stats(), ttl=TTL,
                        price=fake_price)
        self.assertEqual((choice.model, choice.reason), (LUNA, "pricing unavailable"))

    def test_tool_loops_multiply_the_per_call_price_gap(self):
        one = decide(150_000, {SOL: CacheMark(150_000, NOW - 250)}, gap_s=60, turn_s=20, p_heavy=0.5)
        many = decide(150_000, {SOL: CacheMark(150_000, NOW - 250)}, gap_s=60, turn_s=20, p_heavy=0.5,
                      calls_per_turn=30)
        self.assertEqual(one.model, SOL)
        self.assertEqual(many.model, LUNA)


class StatsTests(unittest.TestCase):
    def test_moving_averages(self):
        stats = Stats()
        stats.observe_tier(True)
        self.assertAlmostEqual(stats.p_heavy, 0.58)
        stats.close_turn(turn_s=10, gap_s=-5, calls=3)
        self.assertAlmostEqual(stats.turn_s, 16)
        self.assertAlmostEqual(stats.gap_s, 36)
        self.assertAlmostEqual(stats.calls_per_turn, 1.8)
        stats.close_turn(turn_s=10, gap_s=0, calls=0)
        self.assertAlmostEqual(stats.calls_per_turn, 1.8)
        stats.observe_output(LUNA, 500)
        self.assertEqual(stats.expected_output(LUNA), 1100)
        self.assertEqual(stats.expected_output(SOL), 1500)


if __name__ == "__main__":
    unittest.main()
