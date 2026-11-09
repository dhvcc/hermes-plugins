"""Deterministic graders for eval tasks."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Optional

ASSISTANT = Path(__file__).resolve().parent / "assistant"
_ANSWER = re.compile(r"ANSWER:\s*(.+)")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def final_answer(response: str) -> Optional[str]:
    found = _ANSWER.findall(response or "")
    return found[-1].strip().strip("`*").strip() if found else None


def _number(text: str) -> Optional[float]:
    match = _NUMBER.search(text or "")
    return float(match.group().replace(",", "")) if match else None


def _close(value: Optional[float], expected: float, relative: float) -> bool:
    return value is not None and abs(value - expected) <= abs(expected) * relative


def _tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(folder)).encode() + path.read_bytes())
    return digest.hexdigest()


def grade(task: dict, response: str, workspace: Optional[Path] = None) -> bool:
    if "check" not in task:
        answer = final_answer(response)
        if answer is None:
            return False
        if task["options"]:
            return answer[:1].upper() == task["answer"]
        return _number(answer) == float(task["answer"])

    check, answer = task["check"], final_answer(response) or ""
    kind = check["type"]
    if kind == "number":
        return _close(_number(answer), check["value"], check["tolerance"])
    if kind == "contains":
        return all(value.lower() in answer.lower() for value in check["values"])
    if kind == "report":
        report = workspace / check["file"]
        if not report.is_file():
            return False
        rows = [line for line in report.read_text().splitlines() if "|" in line]
        return all(any(region.lower() in row.lower() and any(
            _close(float(n.replace(",", "")), amount, check["tolerance"]) for n in _NUMBER.findall(row.replace(region, "")))
            for row in rows) for region, amount in check["values"].items())
    if kind == "unittest":
        original = ASSISTANT / task["workspace"] / "workspace" / "tests"
        if _tree_hash(workspace / "tests") != _tree_hash(original):
            return False
        run = subprocess.run(["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=workspace,
                             capture_output=True, timeout=120)
        return run.returncode == 0
    if kind == "script":
        hidden = ASSISTANT / task["workspace"] / "hidden"
        command = [part.replace("{hidden}", str(hidden)) for part in check["command"]]
        run = subprocess.run(command, cwd=workspace, capture_output=True, text=True, timeout=120)
        expected = Path(check["expected"].replace("{hidden}", str(hidden))).read_text()
        return run.returncode == 0 and run.stdout.strip() == expected.strip()
    raise ValueError(f"unknown check {kind}")
