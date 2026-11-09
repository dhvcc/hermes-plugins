# Eval

Run on 2026-11-09. Ten tasks from [RouterArena](https://github.com/RouteWorks/RouterArena) `sub_10`: 3 easy, 3 medium, 4 hard, picked as the first auto-gradable task of each dataset/difficulty pair ([`eval/tasks.json`](../eval/tasks.json)).

Each task is one turn of a real Hermes agent on the ChatGPT/Codex subscription, no tools, reasoning effort `xhigh`. **Luna only** and **Sol only** are plain Hermes. **Smart router** is Hermes on Sol with this plugin. Cost is API-equivalent USD from Hermes's official price snapshot, with Decisions API calls included. One run per task, so treat small differences as noise.

![Accuracy vs cost per task](eval.png)

On this set Luna at `xhigh` solved every task Sol solved, AIME included, so routing hard turns to Sol bought no extra accuracy. The router still cost a third less than Sol only and was the fastest, because light turns ran Luna at lower effort. Its value depends on tasks Luna gets wrong; a harder set is needed to measure that.

| Mode | Solved | Cost per task | Time per task | Turns on Sol | Easy | Medium | Hard |
|---|---|---|---|---|---|---|---|
| Luna only | 90% | $0.0004 | 16.7 s | 0% | 3/3 | 2/3 | 4/4 |
| Sol only | 90% | $0.0048 | 11.3 s | 100% | 3/3 | 2/3 | 4/4 |
| Smart router | 90% | $0.0032 | 10.5 s | 20% | 3/3 | 2/3 | 4/4 |

## Per task

| Task | Difficulty | Answer | Luna | Sol | Smart (model) |
|---|---|---|---|---|---|
| OpenTDB_General Knowledge_1807 | easy | B | ✓ | ✓ | ✓ (6-luna) |
| MedMCQA_1494 | easy | A | ✓ | ✓ | ✓ (6-luna) |
| MMLUPro_business_6 | easy | D | ✓ | ✓ | ✓ (6-luna) |
| GSM8K_43 | medium | 48 | ✓ | ✓ | ✓ (6-luna) |
| MMLUPro_engineering_10199 | medium | G | ✗ | ✗ | ✗ (6-luna) |
| MMLUPro_math_7758 | medium | C | ✓ | ✓ | ✓ (6-luna) |
| AIME_58 | hard | 24 | ✓ | ✓ | ✓ (6.1-sol) |
| AIME_112 | hard | 610 | ✓ | ✓ | ✓ (6.1-sol) |
| MMLUPro_law_1242 | hard | I | ✓ | ✓ | ✓ (6-luna) |
| MMLUPro_computer science_9414 | hard | E | ✓ | ✓ | ✓ (6-luna) |

`MMLUPro_engineering_10199`: The benchmark label is G (1/2). A Wien bridge oscillator's feedback factor is 1/3 (E), which every mode answered, so this miss is shared and says nothing about routing.

Reproduce: `eval/run.py --mode luna|sol|smart`, then `eval/report.py`.
