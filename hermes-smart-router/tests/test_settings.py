import unittest

import support  # noqa: F401
from hermes_smart_router.settings import Settings


def load(**values):
    return Settings.load(lambda key, default: values.get(key, default))


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = load()
        self.assertEqual(settings, Settings())
        self.assertEqual(settings.models, ("gpt-6-luna", "gpt-6.1-sol"))

    def test_overrides(self):
        settings = load(mode="shadow", skip_platforms=["cron", "telegram"], cache_ttl_seconds=600, light_effort="medium")
        self.assertEqual((settings.mode, settings.skip_platforms, settings.cache_ttl_seconds, settings.light_effort),
                         ("shadow", ("cron", "telegram"), 600.0, "medium"))

    def test_invalid_values_raise(self):
        cases = [dict(mode="balanced"), dict(api_key_env="ANTHROPIC_API_KEY"), dict(light_effort="ultra"), dict(skip_platforms="cron"), dict(skip_platforms=[1]),
                 dict(cache_ttl_seconds=True), dict(cache_ttl_seconds=-1), dict(heavy_model=""),
                 dict(light_model="gpt-6.1-sol")]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                load(**values)


if __name__ == "__main__":
    unittest.main()
