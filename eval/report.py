"""Build docs/eval.md and docs/eval.png from eval/results/<set>/<mode>.json.

    uv run --with matplotlib python eval/report.py --date 2026-11-09
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = [("luna", "Luna only", "#2a78d6"), ("sol", "Sol only", "#eb6834"), ("smart", "Smart router", "#1baf7a")]
SETS = [
    {
        "name": "routerarena", "tasks": "tasks.json", "title": "Mixed: 10 RouterArena tasks",
        "about": "Ten tasks from [RouterArena](https://github.com/RouteWorks/RouterArena) `sub_10`: 3 easy, 3 medium, "
                 "4 hard, the first auto-gradable task of each dataset/difficulty pair.",
        "notes": {"MMLUPro_engineering_10199": "the benchmark label is G (1/2), but a Wien bridge oscillator's "
                  "feedback factor is 1/3 (E). Every mode answered E, so this miss says nothing about routing."},
    },
    {
        "name": "math2026", "tasks": "tasks_hard.json", "title": "Hard: 10 olympiad problems, 2026",
        "about": "The six last (hardest) AIME 2026 problems and four integer-answer HMMT February 2026 problems, "
                 "from [MathArena](https://huggingface.co/MathArena).",
        "notes": {},
    },
    {
        "name": "assistant", "tasks": "tasks_assistant.json", "title": "Agent: 6 assistant tasks",
        "about": "Multi-step tool use in a throwaway folder with the terminal and file tools: totalling overdue invoices "
                 "and finding a rescheduled meeting in a 17-email mailbox with a phishing look-alike, a reimbursement "
                 "calculation across superseded, current and draft policy documents, a revenue report built from "
                 "messy CSV/JSON data, fixing three bugs behind failing unit tests, and fixing a crashing script that is "
                 "then checked on a hidden input crossing a DST change. Fixtures are in "
                 "[`eval/assistant/`](../eval/assistant).",
        "notes": {},
    },
]
TAKEAWAYS = {
    "routerarena": "All three modes solved the same nine tasks. The router sent only the two AIME problems to Sol, "
                   "cost a third less than Sol only and was the fastest. Luna alone was cheapest.",
    "math2026": "Luna missed two of ten: it gave up on AIME #15 and answered HMMT #20 wrong. The router sent all ten to "
                "Sol and matched it. Its cost above Sol here is run-to-run variance in reasoning length on the same "
                "model; the Decisions calls cost under $0.0001 per task.",
    "assistant": "All modes solved all six. The router kept the two lookup-style tasks on Luna and sent the four that "
                 "need calculation or code changes to Sol: 41% cheaper than Sol only and the fastest. Luna alone was "
                 "cheapest and slowest.",
}


def load(spec: dict) -> dict | None:
    folder = ROOT / "eval" / "results" / spec["name"]
    if not all((folder / f"{mode}.json").exists() for mode, _, _ in MODES):
        return None
    results = {mode: json.loads((folder / f"{mode}.json").read_text()) for mode, _, _ in MODES}
    stats = {}
    for mode, rows in ((mode, results[mode]["rows"]) for mode in results):
        n = len(rows)
        stats[mode] = {
            "solved": sum(r["correct"] for r in rows), "n": n,
            "usd": sum(r["llm_usd"] + r["decisions_usd"] for r in rows) / n,
            "seconds": sum(r["seconds"] for r in rows) / n,
            "on_sol": sum(any("sol" in m for m in r["models"]) for r in rows),
        }
    tasks = json.loads((ROOT / "eval" / spec["tasks"]).read_text())["tasks"]
    return {"spec": spec, "results": results, "stats": stats, "tasks": tasks}


def chart(evals: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, surface = "#1f1f1e", "#6b6a64", "#e6e5e0", "#fcfcfb"
    fig, axes = plt.subplots(len(evals), 1, figsize=(7.2, 3.6 * len(evals)), dpi=200, facecolor=surface,
                             squeeze=False)
    for ax, ev in zip(axes[:, 0], evals):
        ax.set_facecolor(surface)
        by_cost = sorted(MODES, key=lambda m: ev["stats"][m[0]]["usd"])
        for rank, (mode, label, color) in enumerate(by_cost):
            s = ev["stats"][mode]
            x, y = s["usd"] * 100, 100 * s["solved"] / s["n"]
            ax.scatter(x, y, s=110, color=color, edgecolor=surface, linewidth=2, zorder=3)
            ax.annotate(f"{label}\n{s['solved']}/{s['n']} · {x:.2f}¢", (x, y), xytext=(8, 16 if rank % 2 else -18),
                        textcoords="offset points", fontsize=9, color=ink, va="center")
        ax.set_title(ev["spec"]["title"], color=ink, fontsize=11, loc="left", pad=10)
        ax.set_xlabel("Cost per task, US cents (API-equivalent)", color=muted, fontsize=9)
        ax.set_ylabel("Tasks solved, %", color=muted, fontsize=9)
        ax.set_ylim(0, 118)
        ax.set_yticks(range(0, 101, 20))
        ax.set_xlim(0, max(s["usd"] for s in ev["stats"].values()) * 100 * 1.5)
        ax.grid(color=grid, linewidth=0.8)
        ax.tick_params(colors=muted, labelsize=8, length=0)
        for side in ax.spines.values():
            side.set_visible(False)
    fig.text(0.01, 0.01, "Higher and further left is better.", color=muted, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=surface)


def expected(task: dict) -> str:
    check = task.get("check")
    if check is None:
        return task["answer"]
    return {"number": lambda: f"{check['value']:,}", "contains": lambda: ", ".join(check["values"]),
            "report": lambda: "report.md totals", "unittest": lambda: "tests pass",
            "script": lambda: "hidden input output"}[check["type"]]()


def section(ev: dict) -> list[str]:
    spec, stats = ev["spec"], ev["stats"]
    lines = [f"## {spec['title']}", "", spec["about"] + f" Tasks: [`eval/{spec['tasks']}`](../eval/{spec['tasks']}).", ""]
    if spec["name"] in TAKEAWAYS:
        lines += [TAKEAWAYS[spec["name"]], ""]
    lines += ["| Mode | Solved | Cost per task | Time per task | Tasks on Sol |", "|---|---|---|---|---|"]
    for mode, label, _ in MODES:
        s = stats[mode]
        lines.append(f"| {label} | {s['solved']}/{s['n']} | ${s['usd']:.4f} | {s['seconds']:.0f} s | {s['on_sol']}/{s['n']} |")
    lines += ["", "| Task | Difficulty | Answer | Luna | Sol | Smart (model) |", "|---|---|---|---|---|---|"]
    by_id = {mode: {r["id"]: r for r in ev["results"][mode]["rows"]} for mode, _, _ in MODES}
    for task in ev["tasks"]:
        cells = []
        for mode, _, _ in MODES:
            row = by_id[mode][task["id"]]
            mark = "✓" if row["correct"] else "✗"
            if mode == "smart":
                mark += " (" + ", ".join(m.split("-2026")[0].replace("gpt-", "") for m in row["models"]) + ")"
            cells.append(mark)
        lines.append(f"| {task['id']} | {task['difficulty']} | {expected(task)} | " + " | ".join(cells) + " |")
    for task_id, note in spec["notes"].items():
        lines += ["", f"`{task_id}`: {note}"]
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    evals = [ev for ev in map(load, SETS) if ev]
    effort = evals[0]["results"]["sol"]["effort"]
    lines = [
        "# Eval", "",
        f"Run on {args.date}. Each task is one turn of a real Hermes agent on the ChatGPT/Codex subscription, "
        f"no tools, reasoning effort `{effort}`. **Luna only** and **Sol only** are plain Hermes. **Smart router** "
        "is Hermes on Sol with this plugin. Cost is API-equivalent USD from Hermes's official price snapshot, "
        "Decisions API calls included. One run per task, so small differences are noise.", "",
        "![Accuracy vs cost per task](eval.png)", "",
    ]
    lines += ["## All tasks", "", "| Mode | Solved | Cost per task | Time per task |", "|---|---|---|---|"]
    for mode, label, _ in MODES:
        rows = [row for ev in evals for row in ev["results"][mode]["rows"]]
        usd = sum(r["llm_usd"] + r["decisions_usd"] for r in rows) / len(rows)
        lines.append(f"| {label} | {sum(r['correct'] for r in rows)}/{len(rows)} | ${usd:.4f} | "
                     f"{sum(r['seconds'] for r in rows) / len(rows):.0f} s |")
    lines.append("")
    for ev in evals:
        lines += section(ev)
    lines += ["Reproduce: `eval/run.py --mode luna|sol|smart --tasks eval/<tasks>.json --out eval/results/<set>/<mode>.json`, "
              "then `eval/report.py`.", ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    chart(evals, ROOT / "docs" / "eval.png")
    (ROOT / "docs" / "eval.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
