"""Build docs/eval.md, docs/eval.png and docs/eval-sets.png from eval/results/<set>/<mode>*.json.

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
        "name": "routerarena", "tasks": "tasks.json", "title": "Mixed: {n} RouterArena tasks",
        "about": "Ten tasks from [RouterArena](https://github.com/RouteWorks/RouterArena) `sub_10`: 3 easy, 3 medium, "
                 "4 hard, the first auto-gradable task of each dataset/difficulty pair.",
        "notes": {"MMLUPro_engineering_10199": "the benchmark label is G (1/2), but a Wien bridge oscillator's "
                  "feedback factor is 1/3 (E). Every mode answered E, so this miss says nothing about routing."},
    },
    {
        "name": "math2026", "tasks": "tasks_hard.json", "title": "Hard: {n} olympiad problems, 2026",
        "about": "The ten last (hardest) AIME 2026 problems and every integer-answer HMMT February 2026 problem, "
                 "from [MathArena](https://huggingface.co/MathArena).",
        "notes": {},
    },
    {
        "name": "assistant", "tasks": "tasks_assistant.json", "title": "Agent: {n} assistant tasks",
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
    "math2026": "Luna missed four of 26 and took almost twice as long as Sol. The router sent all 26 to Sol and solved "
                "every one. A turn routed to Sol sends a request byte-identical to plain Sol, which a host test checks, so "
                "the router's higher cost and time here are run-to-run variance in reasoning length. The Decisions calls "
                "cost under $0.0001 per task.",
    "assistant": "All modes solved all six. The router kept the two lookup-style tasks on Luna and sent the four that "
                 "need calculation or code changes to Sol: 41% cheaper than Sol only and the fastest. Luna alone was "
                 "cheapest and slowest.",
}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "solved": sum(r["correct"] for r in rows), "n": n,
        "usd": sum(r["llm_usd"] + r["decisions_usd"] for r in rows) / n,
        "seconds": sum(r["seconds"] for r in rows) / n,
        "on_sol": sum(any("sol" in m for m in r["models"]) for r in rows),
    }


def load(spec: dict) -> dict | None:
    folder = ROOT / "eval" / "results" / spec["name"]
    tasks = json.loads((ROOT / "eval" / spec["tasks"]).read_text())["tasks"]
    ids = [task["id"] for task in tasks]
    rows, effort = {}, None
    for mode, _, _ in MODES:
        merged = {}
        for path in sorted(folder.glob(f"{mode}*.json")):
            data = json.loads(path.read_text())
            effort = data["effort"]
            merged.update({row["id"]: row for row in data["rows"]})
        if set(ids) - set(merged):
            return None
        rows[mode] = [merged[i] for i in ids]
    return {"spec": spec, "rows": rows, "effort": effort, "tasks": tasks,
            "stats": {mode: summarize(rows[mode]) for mode in rows}}


INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e6e5e0", "#fcfcfb"
AXES = {"usd": ("Cost per task, US cents (API-equivalent)", lambda s: s["usd"] * 100, "{:.2f}¢"),
        "seconds": ("Time per task, seconds", lambda s: s["seconds"], "{:.0f} s")}


def panel(ax, stats: dict, metric: str, title: str) -> None:
    label_x, value, fmt = AXES[metric]
    ax.set_facecolor(SURFACE)
    ordered = sorted(MODES, key=lambda m: value(stats[m[0]]))
    for rank, (mode, label, color) in enumerate(ordered):
        s = stats[mode]
        x, y = value(s), 100 * s["solved"] / s["n"]
        ax.scatter(x, y, s=110, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.annotate(f"{label}\n{s['solved']}/{s['n']} · {fmt.format(x)}", (x, y), xytext=(8, 16 if rank % 2 else -18),
                    textcoords="offset points", fontsize=9, color=INK, va="center")
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=10)
    ax.set_xlabel(label_x, color=MUTED, fontsize=9)
    ax.set_ylabel("Tasks solved, %", color=MUTED, fontsize=9)
    ax.set_ylim(0, 118)
    ax.set_yticks(range(0, 101, 20))
    ax.set_xlim(0, max(value(s) for s in stats.values()) * 1.5)
    ax.grid(color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    for side in ax.spines.values():
        side.set_visible(False)


def chart(rows_of_panels: list[tuple[str, dict]], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(rows_of_panels), 2, figsize=(12, 3.8 * len(rows_of_panels)), dpi=170,
                             facecolor=SURFACE, squeeze=False)
    for (title, stats), (cost_ax, time_ax) in zip(rows_of_panels, axes):
        panel(cost_ax, stats, "usd", f"{title}: accuracy vs cost")
        panel(time_ax, stats, "seconds", f"{title}: accuracy vs time")
    fig.text(0.01, 0.01, "Higher and further left is better.", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=SURFACE)


def expected(task: dict) -> str:
    check = task.get("check")
    if check is None:
        return task["answer"]
    return {"number": lambda: f"{check['value']:,}", "contains": lambda: ", ".join(check["values"]),
            "report": lambda: "report.md totals", "unittest": lambda: "tests pass",
            "script": lambda: "hidden input output"}[check["type"]]()


def section(ev: dict) -> list[str]:
    spec, stats = ev["spec"], ev["stats"]
    lines = [f"## {title(ev)}", "", spec["about"] + f" Tasks: [`eval/{spec['tasks']}`](../eval/{spec['tasks']}).", ""]
    if spec["name"] in TAKEAWAYS:
        lines += [TAKEAWAYS[spec["name"]], ""]
    lines += ["| Mode | Solved | Cost per task | Time per task | Tasks on Sol |", "|---|---|---|---|---|"]
    for mode, label, _ in MODES:
        s = stats[mode]
        lines.append(f"| {label} | {s['solved']}/{s['n']} | ${s['usd']:.4f} | {s['seconds']:.0f} s | {s['on_sol']}/{s['n']} |")
    lines += ["", "| Task | Difficulty | Answer | Luna | Sol | Smart (model) |", "|---|---|---|---|---|---|"]
    by_id = {mode: {r["id"]: r for r in ev["rows"][mode]} for mode, _, _ in MODES}
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


def title(ev: dict) -> str:
    return ev["spec"]["title"].format(n=len(ev["tasks"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    evals = [ev for ev in map(load, SETS) if ev]
    overall = {mode: summarize([row for ev in evals for row in ev["rows"][mode]]) for mode, _, _ in MODES}
    total = overall["sol"]["n"]
    lines = [
        "# Eval", "",
        f"Run on {args.date}. Each task is one turn of a real Hermes agent on the ChatGPT/Codex subscription, "
        f"reasoning effort `{evals[0]['effort']}`. **Luna only** and **Sol only** are plain Hermes. **Smart router** "
        "is Hermes on Sol with this plugin. Cost is API-equivalent USD from Hermes's official price snapshot, "
        "Decisions API calls included. Time is wall-clock per task. One run per task.", "",
        f"![All {total} tasks](eval.png)", "",
        f"## All {total} tasks", "", "| Mode | Solved | Cost per task | Time per task | Tasks on Sol |", "|---|---|---|---|---|",
    ]
    for mode, label, _ in MODES:
        o = overall[mode]
        lines.append(f"| {label} | {o['solved']}/{o['n']} | ${o['usd']:.4f} | {o['seconds']:.0f} s | {o['on_sol']}/{o['n']} |")
    lines += ["", "![Per set](eval-sets.png)", ""]
    for ev in evals:
        lines += section(ev)
    lines += ["Reproduce: `eval/run.py --mode luna|sol|smart --tasks eval/<tasks>.json --out eval/results/<set>/<mode>.json`, "
              "then `eval/report.py`.", ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    chart([(f"All {total} tasks", overall)], ROOT / "docs" / "eval.png")
    chart([(title(ev), ev["stats"]) for ev in evals], ROOT / "docs" / "eval-sets.png")
    (ROOT / "docs" / "eval.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
