import unittest

import support  # noqa: F401
from hermes_smart_router.classifier import HEAVY, LIGHT, STANDARD, classify, message_text


class ClassifierTests(unittest.TestCase):
    def assertTier(self, tier, *prompts, previous=None):
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(classify(prompt, previous), tier)

    def test_light(self):
        self.assertTier(LIGHT, "What is 2+2? Reply with one digit only.", "привет", "Столица Австралии?",
                        "thanks!", "сколько будет 15% от 2400")

    def test_standard(self):
        self.assertTier(STANDARD, "Write a short email to the team about Friday's meeting",
                        "Объясни, почему небо голубое", "Напиши функцию на Python, которая удаляет дубликаты",
                        "Summarize the main points of this note: revenue grew, churn fell, hiring paused.",
                        "Как настроить фильтр в Gmail для писем от бухгалтерии?")

    def test_heavy(self):
        self.assertTier(HEAVY, "Refactor the billing module to remove the global state",
                        "Prove that sqrt(2) is irrational", "Проведи аудит безопасности нашего API",
                        "Спроектируй архитектуру сервиса уведомлений", "Почему тут deadlock?",
                        "```python\nprint(1)\n```", 'Traceback (most recent call last):\n  File "x.py"',
                        "word " * 300)

    def test_continuation_keeps_previous_tier(self):
        self.assertTier(HEAVY, "продолжай", "ok", "да, делай", "go ahead", "fix it", previous=HEAVY)
        self.assertTier(LIGHT, "ok", previous=LIGHT)

    def test_continuation_without_history_is_classified_normally(self):
        self.assertEqual(classify("ok"), LIGHT)

    def test_long_message_starting_with_yes_is_not_a_continuation(self):
        self.assertEqual(classify("yes, and now explain how the quarterly forecast was built", HEAVY), STANDARD)

    def test_empty_text_keeps_previous_or_standard(self):
        self.assertEqual(classify("   ", HEAVY), HEAVY)
        self.assertEqual(classify(""), STANDARD)

    def test_message_text(self):
        self.assertEqual(message_text("hi"), "hi")
        self.assertEqual(message_text([{"type": "text", "text": "a"}, {"type": "image"}, {"text": "b"}]), "a b")
        self.assertEqual(message_text({"content": "c"}), "c")
        self.assertEqual(message_text(None), "")


if __name__ == "__main__":
    unittest.main()
