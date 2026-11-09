import importlib.util
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def load_package():
    if "hermes_smart_router" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "hermes_smart_router", PACKAGE_DIR / "__init__.py", submodule_search_locations=[str(PACKAGE_DIR)])
        module = importlib.util.module_from_spec(spec)
        sys.modules["hermes_smart_router"] = module
        spec.loader.exec_module(module)
    return sys.modules["hermes_smart_router"]


load_package()

LUNA, SOL = "gpt-6-luna", "gpt-6.1-sol"
# (cache read, cache write, output) USD per 1M tokens, mirroring Hermes's official snapshot below 272K.
RATES = {LUNA: (0.01, 0.125, 0.50), SOL: (0.10, 2.50, 10.00)}


def fake_price(model, prompt, cached, output):
    if model not in RATES:
        return None
    read, write, out = RATES[model]
    cached = min(cached, prompt)
    return (cached * read + (prompt - cached) * write + output * out) / 1e6


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now
