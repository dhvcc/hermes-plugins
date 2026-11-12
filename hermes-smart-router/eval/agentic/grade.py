"""Graders for the agentic scenarios. Each returns {part: score in [0, 1]}; the scenario score is their mean."""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def answer(response: str) -> str:
    found = re.findall(r"ANSWER:\s*(.+)", response or "")
    return found[-1].strip().strip("`*").strip() if found else ""


def numbers(text: str) -> list[Decimal]:
    out = []
    for raw in _NUMBER.findall(text or ""):
        try:
            out.append(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            pass
    return out


def near(value, expected, tolerance="0.01") -> bool:
    try:
        return abs(Decimal(str(value).replace(",", "").replace("€", "").strip()) - Decimal(str(expected))) <= Decimal(tolerance)
    except (InvalidOperation, ValueError):
        return False


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def row_score(rows: list[dict], key: str, expected: dict, match) -> float:
    found = {row.get(key, "").upper(): row for row in rows}
    return sum(bool(found.get(k.upper())) and match(found[k.upper()], v) for k, v in expected.items()) / len(expected)


def expense_audit(ws: Path, responses: list[str], exp: dict) -> dict:
    rows = read_csv(ws / "audit.csv")
    worst = answer(responses[1])
    return {
        "rows": row_score(rows, "receipt_id", exp["rows"], lambda r, e: near(r.get("approved_eur"), e["approved_eur"])
                          and r.get("status", "").lower() == e["status"]),
        "total": float(any(near(n, exp["total"]) for n in numbers(answer(responses[0])))),
        "follow_up": float(exp["worst_employee"].lower() in worst.lower()
                           and any(near(n, exp["worst_lost"]) for n in numbers(worst))),
    }


def reconciliation(ws: Path, responses: list[str], exp: dict) -> dict:
    rows = read_csv(ws / "reconciliation.csv")
    text = answer(responses[1])
    parts = [p for p in re.split(r";|\n", text) if p.strip()]
    top = sum(i < len(parts) and client.split()[0].lower() in parts[i].lower()
              and any(near(n, amount) for n in numbers(parts[i])) for i, (client, amount) in enumerate(exp["top_debtors"]))
    return {
        "rows": row_score(rows, "invoice_id", exp["rows"], lambda r, e: r.get("status", "").lower() == e["status"]
                          and near(r.get("received_eur"), e["received_eur"])),
        "follow_up": top / len(exp["top_debtors"]),
    }


def incident(ws: Path, responses: list[str], exp: dict) -> dict:
    data = read_json(ws / "answer.json") or {}
    return {
        "bad_version": float(str(data.get("bad_version", "")).lstrip("v") == exp["bad_version"]),
        "endpoint": float(str(data.get("affected_endpoint", "")).strip() == exp["affected_endpoint"]),
        "first_error": float(data.get("first_error_request_id") == exp["first_error_request_id"]),
        "error_rate": float(near(data.get("error_rate_after_pct", ""), exp["error_rate_after_pct"], "0.05")),
        "root_cause": float(bool(re.search(r"payment[\s_-]*gateway", str(data.get("root_cause", "")), re.I))),
    }


def bugfix(ws: Path, responses: list[str], exp: dict) -> dict:
    original = ROOT / "bugfix" / "workspace" / "tests" / "test_visible.py"
    if (ws / "tests" / "test_visible.py").read_text() != original.read_text():
        return {"hidden_tests": 0.0}
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(ROOT / "bugfix" / "hidden" / "test_hidden.py", tmp)
        run = subprocess.run(["python3", "-m", "unittest", "-v", "test_hidden"], cwd=tmp, capture_output=True, text=True,
                             timeout=120, env={"PYTHONPATH": str(ws), "PATH": "/usr/bin:/bin"})
    passed = len(re.findall(r" \.\.\. ok$", run.stderr, re.M))
    return {"hidden_tests": passed / exp["hidden_tests"]}


def scheduling(ws: Path, responses: list[str], exp: dict) -> dict:
    def same(text, expected):
        return expected.replace("Z", "") in text.replace(" ", "T").replace("z", "Z").replace("Z", "")
    return {"first": float(same(answer(responses[0]), exp["first"])),
            "follow_up": float(any(same(answer(responses[1]), slot) for slot in exp["follow_up"]))}


MONTHS = {"2026-07": ("2026-07", "july", "jul"), "2026-08": ("2026-08", "august", "aug"),
          "2026-09": ("2026-09", "september", "sep"), "2026-10": ("2026-10", "october", "oct")}


def kpi_report(ws: Path, responses: list[str], exp: dict) -> dict:
    path = ws / "kpi.md"
    rows = [line for line in path.read_text().splitlines() if "|" in line] if path.is_file() else []
    parts = {}
    for month, want in exp["months"].items():
        row = next((r for r in rows if any(name in r.lower() for name in MONTHS[month])), "")
        cells = [c.strip().replace("$", "").replace("€", "").replace("EUR", "").strip() for c in row.split("|")]
        parts[f"{month}_mrr"] = float(any(near(c, want["mrr"]) for c in cells if c))
        parts[f"{month}_churn"] = float(str(want["churned"]) in cells)
    return parts


def handbook(ws: Path, responses: list[str], exp: dict) -> dict:
    given = read_json(ws / "answers.json") or {}
    parts = {}
    for qid, want in exp["answers"].items():
        got = str(given.get(qid, "")).lower()
        if want in ("yes", "no"):
            parts[qid] = float(got.strip().startswith(want))
        else:
            wanted = numbers(want)
            parts[qid] = float(numbers(got)[:len(wanted)] == wanted)
    return parts


def triage(ws: Path, responses: list[str], exp: dict) -> dict:
    rows = read_csv(ws / "triage.csv")
    for row in rows:
        row["file"] = Path(row.get("file", "")).name
    reports = sum(v["action"] == "report" for v in exp["rows"].values())
    return {
        "rows": row_score(rows, "file", exp["rows"], lambda r, e: r.get("action", "").lower() == e["action"]
                          and r.get("due", "") == e["due"]),
        "follow_up": float(numbers(answer(responses[1]))[:1] == [Decimal(reports)]),
    }


GRADERS = {f.__name__: f for f in (expense_audit, reconciliation, incident, bugfix, scheduling, kpi_report, handbook,
                                   triage)}


def grade(scenario: str, workspace: Path, responses: list[str]) -> dict:
    expected = json.loads((ROOT / scenario / "expected.json").read_text())
    return GRADERS[scenario](workspace, responses, expected)
