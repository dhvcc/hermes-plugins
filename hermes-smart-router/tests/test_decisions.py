import io
import json
import unittest
from contextlib import contextmanager

import support  # noqa: F401
from hermes_smart_router import decisions


def opener(answer=None, raw=None, calls=None):
    @contextmanager
    def open_url(request, timeout):
        if calls is not None:
            calls.append((request, timeout))
        body = raw if raw is not None else json.dumps({"answers": [answer]}).encode()
        yield io.BytesIO(body)
    return open_url


def classify(**kwargs):
    return decisions.classify([], "hi", api_key="sk-test", session_id="s", timeout=2.0, **kwargs)


class DecisionsTests(unittest.TestCase):
    def test_request_shape(self):
        calls = []
        classify(open_url=opener({"type": "choice", "probabilities": []}, calls=calls))
        request, timeout = calls[0]
        body = json.loads(request.data)
        self.assertEqual((request.full_url, request.get_method(), timeout), (decisions.API_URL, "POST", 2.0))
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["questions"][0]["type"], "choice")
        self.assertEqual([c["value"] for c in body["questions"][0]["choices"]], ["light", "standard", "heavy"])
        self.assertTrue(body["prompt_cache_key"].startswith("hsr-") and len(body["prompt_cache_key"]) <= 64)

    def test_answers_lean_heavy(self):
        cases = [((0.95, 0.03, 0.02), "light"), ((0.03, 0.86, 0.11), "standard"), ((0.5, 0.3, 0.2), "standard"),
                 ((0.03, 0.44, 0.53), "heavy"), ((0.19, 0.51, 0.3), "heavy")]
        for (light, standard, heavy), tier in cases:
            answer = {"type": "choice", "choice": "light", "confidence": 0.9, "probabilities": [
                {"value": "light", "probability": light}, {"value": "standard", "probability": standard},
                {"value": "heavy", "probability": heavy}]}
            with self.subTest(tier=tier, heavy=heavy):
                self.assertEqual(classify(open_url=opener(answer)), (tier, heavy))
        for answer in ({"type": "refusal", "name": "tier"}, {"type": "choice", "choice": "light"},
                       {"type": "choice", "probabilities": [{"value": "x", "probability": 1}]}, None):
            self.assertIsNone(classify(open_url=opener(answer)))
        self.assertIsNone(classify(open_url=opener(raw=b"x" * (decisions.MAX_RESPONSE_BYTES + 1))))

    def test_input_keeps_recent_text_and_drops_tools(self):
        history = [{"role": "system", "content": "sys"}]
        history += [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(10)]
        history += [{"role": "tool", "content": "tool output"}, {"role": "assistant", "content": ""},
                    {"role": "user", "content": "now"}]
        items = decisions.build_input(history, "now")
        self.assertEqual([i["content"] for i in items], ["m4", "m5", "m6", "m7", "m8", "m9", "now"])
        self.assertEqual(items[-1]["role"], "user")
        self.assertEqual(decisions.build_input(None, [{"type": "text", "text": "x"}]), [{"role": "user", "content": "x"}])

    def test_message_text(self):
        self.assertEqual(decisions.message_text([{"type": "text", "text": "a"}, {"type": "image"}, {"text": "b"}]), "a b")
        self.assertEqual(decisions.message_text({"content": "c"}), "c")
        self.assertEqual(decisions.message_text(None), "")


if __name__ == "__main__":
    unittest.main()
