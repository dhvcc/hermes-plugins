"""Build docs/eval.md and docs/eval.png from eval/results/*.json.

    uv run --with matplotlib python eval/report.py --date 2026-11-09
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = [("luna", "Luna only", "#2a78d6"), ("sol", "Sol only", "#eb6834"), ("smart", "Smart router", "#1baf7a")]
DIFFICULTIES = ("easy", "medium", "hard")
LABEL_NOTES = {
    "MMLUPro_engineering_10199": "The benchmark label is G (1/2). A Wien bridge oscillator's feedback factor is 1/3 "
                                 "(E), which every mode answered, so this miss is shared and says nothing about routing.",
}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "accuracy": sum(r["correct"] for r in rows) / n,
        "usd": sum(r["llm_usd"] + r["decisions_usd"] for r in rows) / n,
        "seconds": sum(r["seconds"] for r in rows) / n,
        "sol_share": sum(any("sol" in m for m in r["models"]) for r in rows) / n,
        "by_difficulty": {d: [r["correct"] for r in rows if r["difficulty"] == d] for d in DIFFICULTIES},
    }


def chart(stats: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, surface = "#1f1f1e", "#6b6a64", "#e6e5e0", "#fcfcfb"
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200, facecolor=surface)
    ax.set_facecolor(surface)
    for mode, label, color in MODES:
        s = stats[mode]
        x, y = s["usd"] * 100, s["accuracy"] * 100
        ax.scatter(x, y, s=110, color=color, edgecolor=surface, linewidth=2, zorder=3)
        ax.annotate(f"{label}\n{y:.0f}% · {x:.2f}¢/task", (x, y), xytext=(10, -4), textcoords="offset points",
                    fontsize=9, color=ink, va="center")
    ax.set_xlabel("Cost per task, US cents (API-equivalent)", color=muted, fontsize=9)
    ax.set_ylabel("Tasks solved, %", color=muted, fontsize=9)
    ax.set_title("Accuracy vs cost per task · 10 RouterArena tasks", color=ink, fontsize=11, loc="left", pad=12)
    ax.set_ylim(0, 105)
    ax.set_xlim(0, max(s["usd"] for s in stats.values()) * 100 * 1.45)
    ax.grid(color=grid, linewidth=0.8)
    ax.tick_params(colors=muted, labelsize=8, length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    fig.text(0.01, 0.01, "Higher and further left is better.", color=muted, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, facecolor=surface)


def markdown(results: dict, stats: dict, tasks: list[dict], date: str) -> str:
    def pct(values) -> str:
        return f"{sum(values)}/{len(values)}" if values else "–"

    lines = [
        "# Eval", "",
        f"Run on {date}. Ten tasks from [RouterArena](https://github.com/RouteWorks/RouterArena) `sub_10`: 3 easy, "
        "3 medium, 4 hard, picked as the first auto-gradable task of each dataset/difficulty pair "
        "([`eval/tasks.json`](../eval/tasks.json)).", "",
        f"Each task is one turn of a real Hermes agent on the ChatGPT/Codex subscription, no tools, "
        f"reasoning effort `{results['sol']['effort']}`. **Luna only** and **Sol only** are plain Hermes. "
        "**Smart router** is Hermes on Sol with this plugin. Cost is API-equivalent USD from Hermes's official "
        "price snapshot, with Decisions API calls included. One run per task, so treat small differences as noise.", "",
        "![Accuracy vs cost per task](eval.png)", "",
        "On this set Luna at `xhigh` solved every task Sol solved, AIME included, so routing hard turns to Sol "
        "bought no extra accuracy. The router still cost a third less than Sol only and was the fastest, "
        "because light turns ran Luna at lower effort. Its value depends on tasks Luna gets wrong; "
        "a harder set is needed to measure that.", "",
        "| Mode | Solved | Cost per task | Time per task | Turns on Sol | Easy | Medium | Hard |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mode, label, _ in MODES:
        s = stats[mode]
        d = s["by_difficulty"]
        lines.append(f"| {label} | {s['accuracy']:.0%} | ${s['usd']:.4f} | {s['seconds']:.1f} s | {s['sol_share']:.0%} "
                     f"| {pct(d['easy'])} | {pct(d['medium'])} | {pct(d['hard'])} |")
    lines += ["", "## Per task", "", "| Task | Difficulty | Answer | Luna | Sol | Smart (model) |", "|---|---|---|---|---|---|"]
    by_id = {mode: {r["id"]: r for r in results[mode]["rows"]} for mode, _, _ in MODES}
    for task in tasks:
        cells = []
        for mode, _, _ in MODES:
            row = by_id[mode][task["id"]]
            mark = "✓" if row["correct"] else "✗"
            if mode == "smart":
                mark += " (" + ", ".join(m.split("-2026")[0].replace("gpt-", "") for m in row["models"]) + ")"
            cells.append(mark)
        lines.append(f"| {task['id']} | {task['difficulty']} | {task['answer']} | " + " | ".join(cells) + " |")
    for task_id, note in LABEL_NOTES.items():
        lines += ["", f"`{task_id}`: {note}"]
    lines += ["", "Reproduce: `eval/run.py --mode luna|sol|smart`, then `eval/report.py`.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    results = {mode: json.loads((ROOT / "eval" / "results" / f"{mode}.json").read_text()) for mode, _, _ in MODES}
    stats = {mode: summarize(results[mode]["rows"]) for mode in results}
    tasks = json.loads((ROOT / "eval" / "tasks.json").read_text())["tasks"]
    (ROOT / "docs").mkdir(exist_ok=True)
    chart(stats, ROOT / "docs" / "eval.png")
    (ROOT / "docs" / "eval.md").write_text(markdown(results, stats, tasks, args.date))


if __name__ == "__main__":
    main()
