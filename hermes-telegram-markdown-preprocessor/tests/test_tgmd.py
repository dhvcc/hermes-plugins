"""Offline golden test. expected.json was verified against Telegram with live_check.py; regenerate it
only after a live check passes."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import tgmd  # noqa: E402

cases = json.loads((HERE / "cases.json").read_text())
expected = json.loads((HERE / "expected.json").read_text())


def test_golden():
    for name, md in cases.items():
        assert tgmd.normalize(md) == expected[name], name


def test_idempotent():
    for name, md in cases.items():
        once = tgmd.normalize(md)
        assert tgmd.normalize(once) == once, name


if __name__ == "__main__":
    test_golden()
    test_idempotent()
    print(f"ok, {len(cases)} cases")
