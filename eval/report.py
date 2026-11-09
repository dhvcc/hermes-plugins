"""Build docs/eval.md and docs/eval.png from eval/results/<mode>-<run>.json.

    uv run --with matplotlib python eval/report.py --date 2026-11-09
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
MODES = [("luna", "Luna only", "#2a78d6"), ("sol", "Sol only", "#eb6834"), ("smart", "Smart router", "#1baf7a")]
SCENARIOS = {
    "expense_audit": "Audit 36 expense receipts against a policy, then a follow-up question",
    "reconciliation": "Match bank transactions to 25 invoices, then list top debtors",
    "incident": "Find the bad deploy and error rate in ~3,700 log lines",
    "bugfix": "Fix four bugs so hidden tests pass",
    "scheduling": "Find a meeting slot across four calendars and time zones, then the next one",
    "kpi_report": "Monthly MRR and churn report from subscription data",
    "handbook": "Answer six questions from a company handbook",
    "triage": "Triage 24 emails by written rules, then a follow-up count",
}
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e6e5e0", "#fcfcfb"


def load() -> dict:
    runs = defaultdict(list)
    for path in sorted((ROOT / "eval" / "results").glob("*-*.json")):
        data = json.loads(path.read_text())
        runs[data["mode"]].append(data["rows"])
    return runs


def run_totals(rows: list[dict]) -> dict:
    return {"score": mean(r["score"] for r in rows), "usd": mean(r["llm_usd"] + r["decisions_usd"] for r in rows),
            "seconds": mean(r["seconds"] for r in rows)}


def chart(summary: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = [("score", "Quality (avg score)", lambda v: v * 100, "{:.0f}%"),
               ("usd", "Cost per session", lambda v: v * 100, "{:.1f}¢"),
               ("seconds", "Time per session", lambda v: v, "{:.0f} s")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.2), dpi=180, facecolor=SURFACE)
    labels = [label for _, label, _ in MODES][::-1]
    for ax, (key, title, scale, fmt) in zip(axes, metrics):
        ax.set_facecolor(SURFACE)
        for y, (mode, _, color) in enumerate(MODES[::-1]):
            values = [scale(run[key]) for run in summary[mode]["runs"]]
            value = mean(values)
            ax.barh(y, value, height=0.6, color=color, zorder=2)
            if len(values) > 1:
                ax.plot([min(values), max(values)], [y, y], color=INK, linewidth=1.2, zorder=3)
            ax.text(value, y + 0.42, fmt.format(value), color=INK, fontsize=9, ha="right", va="center")
        ax.set_yticks(range(len(labels)), labels, fontsize=9, color=INK)
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xlim(0, max(scale(run[key]) for m, _, _ in MODES for run in summary[m]["runs"]) * 1.12)
        ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
        ax.tick_params(axis="x", colors=MUTED, labelsize=8, length=0)
        ax.tick_params(axis="y", length=0)
        for side in ax.spines.values():
            side.set_visible(False)
    fig.text(0.01, 0.01, "Bars: mean of runs. Black line: range between runs. Higher quality, lower cost and time are better.",
             color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, facecolor=SURFACE)


def pct(new: float, base: float) -> str:
    return f"{(new - base) / base * 100:+.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    runs = load()
    summary = {}
    for mode, _, _ in MODES:
        totals = [run_totals(rows) for rows in runs[mode]]
        summary[mode] = {"runs": totals, **{k: mean(t[k] for t in totals) for k in ("score", "usd", "seconds")}}
    smart, sol, luna = summary["smart"], summary["sol"], summary["luna"]
    n_runs = min(len(runs[m]) for m, _, _ in MODES)

    lines = [
        "# Eval", "",
        f"**Smart router: {smart['score']:.0%} quality vs {sol['score']:.0%} for Sol only and {luna['score']:.0%} for "
        f"Luna only, at {pct(smart['usd'], sol['usd'])} cost and {pct(smart['seconds'], sol['seconds'])} time "
        "compared with Sol only.**", "",
        "![Quality, cost and time per session](eval.png)", "",
        "| Mode | Quality | Cost per session | Time per session |", "|---|---|---|---|",
    ]
    for mode, label, _ in MODES:
        s = summary[mode]
        lines.append(f"| {label} | {s['score']:.0%} | ${s['usd']:.3f} | {s['seconds']:.0f} s |")
    lines += [
        "", "## Setup", "",
        f"Run on {args.date}, {len(SCENARIOS)} scenarios × {n_runs} runs per mode. Every scenario is a real Hermes agent "
        "session on the ChatGPT/Codex subscription with the terminal and file tools, in a fresh copy of a workspace. "
        "Some scenarios have a follow-up turn in the same session. Reasoning effort is `xhigh`. **Luna only** and "
        "**Sol only** are plain Hermes. **Smart router** is Hermes on Sol with this plugin.", "",
        "The data is synthetic and generated from a seed by [`eval/agentic/build.py`](../eval/agentic/build.py), so it "
        "is not in any training set. The same script computes the expected results. "
        "[`eval/agentic/grade.py`](../eval/agentic/grade.py) checks every output row and value, so a scenario scores "
        "the share it got right, from 0 to 1, instead of pass or fail. Cost is API-equivalent USD from Hermes's "
        "official price snapshot, Decisions API calls included. Time is wall-clock per session.", "",
        "## Per scenario", "",
        "| Scenario | Luna | Sol | Smart | Smart used |", "|---|---|---|---|---|",
    ]
    by = {mode: defaultdict(list) for mode, _, _ in MODES}
    for mode, _, _ in MODES:
        for rows in runs[mode]:
            for row in rows:
                by[mode][row["id"]].append(row)
    for scenario, description in SCENARIOS.items():
        cells = []
        for mode, _, _ in MODES:
            rows = by[mode][scenario]
            cells.append(f"{mean(r['score'] for r in rows):.0%} · ${mean(r['llm_usd'] + r['decisions_usd'] for r in rows):.3f}"
                         f" · {mean(r['seconds'] for r in rows):.0f} s")
        used = " / ".join(sorted({" → ".join("+".join(m.split("-2026")[0].replace("gpt-", "") for m in turn) or "?"
                                             for turn in r["turn_models"]) for r in by["smart"][scenario]}))
        lines.append(f"| {description} | " + " | ".join(cells) + f" | {used} |")
    lines += ["", "Cells: quality · cost · time, averaged over runs. *Smart used* lists the model per turn.", "",
              "Reproduce: `python3 eval/agentic/build.py`, then `eval/run.py --mode luna|sol|smart --out "
              "eval/results/<mode>-<run>.json` for each run, then `eval/report.py`.", ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    chart(summary, ROOT / "docs" / "eval.png")
    (ROOT / "docs" / "eval.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
