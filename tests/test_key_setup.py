import unittest

import support  # noqa: F401
from hermes_smart_router import key_setup


class Harness:
    def __init__(self, secrets, working=(), answers=(), pasted="", check=None):
        self.secrets, self.working, self.answers, self.pasted = dict(secrets), set(working), list(answers), pasted
        self.check = check or (lambda key: key in self.working)
        self.saved, self.chosen, self.lines, self.questions = {}, None, [], []

    def run(self):
        io = key_setup.Io(say=self.lines.append, confirm=self.confirm, ask_secret=lambda prompt: self.pasted)
        return key_setup.run(io, secret=self.secrets.get, check=self.check, save_key=self.saved.__setitem__,
                             choose=self.choose)

    def confirm(self, prompt):
        self.questions.append(prompt)
        return self.answers.pop(0)

    def choose(self, name):
        self.chosen = name


def unreachable(key):
    raise OSError


class KeySetupTests(unittest.TestCase):
    def test_working_openai_key_needs_no_questions(self):
        h = Harness({"OPENAI_API_KEY": "sk-a", "VOICE_TOOLS_OPENAI_KEY": "sk-v"}, working={"sk-a"})
        self.assertEqual(h.run(), 0)
        self.assertEqual((h.chosen, h.questions, h.saved), ("OPENAI_API_KEY", [], {}))

    def test_voice_key_is_used_only_after_yes(self):
        h = Harness({"VOICE_TOOLS_OPENAI_KEY": "sk-v"}, working={"sk-v"}, answers=[True])
        self.assertEqual(h.run(), 0)
        self.assertEqual((h.chosen, h.saved), ("VOICE_TOOLS_OPENAI_KEY", {}))
        self.assertIn("voice", h.questions[0])

    def test_declining_voice_asks_for_a_key(self):
        h = Harness({"VOICE_TOOLS_OPENAI_KEY": "sk-v"}, working={"sk-v", "sk-new"}, answers=[False], pasted="sk-new")
        self.assertEqual(h.run(), 0)
        self.assertEqual((h.chosen, h.saved), ("OPENAI_API_KEY", {"OPENAI_API_KEY": "sk-new"}))

    def test_rejected_voice_key_falls_through_to_paste(self):
        h = Harness({"VOICE_TOOLS_OPENAI_KEY": "sk-proxy"}, working={"sk-new"}, answers=[True], pasted="sk-new")
        self.assertEqual(h.run(), 0)
        self.assertIn("OpenAI rejected the voice key.", h.lines)
        self.assertEqual(h.saved, {"OPENAI_API_KEY": "sk-new"})

    def test_no_keys_and_skip(self):
        h = Harness({})
        self.assertEqual(h.run(), 1)
        self.assertEqual((h.chosen, h.saved, h.questions), (None, {}, []))

    def test_bad_pasted_key_is_not_saved(self):
        h = Harness({}, pasted="sk-bad")
        self.assertEqual(h.run(), 1)
        self.assertEqual((h.chosen, h.saved), (None, {}))

    def test_network_error_counts_as_not_working(self):
        h = Harness({"OPENAI_API_KEY": "sk-a"}, check=unreachable)
        self.assertEqual(h.run(), 1)
        self.assertIn("Could not reach OpenAI (OSError).", h.lines)


if __name__ == "__main__":
    unittest.main()
