# hermes-delegation-clock

Gives the agent a sense of time and makes it responsible for the background subagents it starts.

Without it, an agent that runs `delegate_task` in the background forgets the task. It has no clock, nothing wakes it when a worker hangs, and nobody notices that the promised result never came.

## What it does

- **Clock in every turn.** It adds the current time and how long ago the previous turn was. If subagents are running, it lists them with elapsed time, expected time, and the command each one is stuck in. Subagents themselves are told how long they have been running.
- **A deadline for every task.** An explicit `ETA: 25m` in the goal wins. Otherwise one cheap [Decisions API](https://developers.openai.com/api/docs/guides/decisions) call estimates the time. Without a key, the default is 15 minutes.
- **Silent wake-ups.** When a worker passes its deadline, runs one command for 10+ minutes, or trips Hermes' stall monitor, the plugin wakes the parent session through Hermes' own session heartbeat. The agent then has three options:
  - give the worker more time with the `subagent_deadline` tool;
  - correct it with `delegate_task action=steer`;
  - stop it with `delegate_task action=stop`.

  The check answers `[SILENT]`, so the user sees nothing. The agent writes to the user only if it stopped a worker, needs a decision, or the result will be much later than promised.
- **Last-resort stop.** A worker at 3× its ETA with no progress is stopped, and the user gets one line about it.
- **Telegram board.** One pinned [widget](https://core.telegram.org/bots/api#sendwidget) shows the last six subagents and is edited in place, not re-sent:
  - running ones have a progress ring against their ETA, with a red ring once overdue;
  - finished ones show start–end and how long they took;
  - each finished one shows whether the answer reached the chat. If it didn't, it reads "no reply" in red.

  The board works in private chats only (a Telegram limitation). Everything else works on any platform.

Everything runs on native Hermes pieces: the async delegation registry, the session heartbeat, the title generator, plugin hooks and a tool. Nothing in Hermes is patched.

## Install

```sh
hermes plugins install dhvcc/hermes-plugins/hermes-delegation-clock
hermes plugins enable hermes-delegation-clock
```

The plugin wakes sessions by injecting a message, so allow that in `config.yaml`:

```yaml
plugins:
  entries:
    hermes-delegation-clock:
      allow_gateway_injection: true
      settings:
        language: en            # board language: en | ru
```

Restart the gateway.

## Settings

All settings go under `plugins.entries.hermes-delegation-clock.settings`.

| Key | Default | Meaning |
|---|---|---|
| `language` | `en` | Board and notice language (`en`, `ru`) |
| `default_eta_min` | `15` | ETA when none is stated and no estimate is available |
| `hang_alert_min` | `10` | Minutes in one command before it counts as stuck |
| `kill_factor` | `3` | Stop a silent worker at this multiple of its ETA |
| `decisions_url` | OpenAI Decisions API | Set to `""` to disable estimates |
| `api_key_env` | `OPENAI_API_KEY` | Env var holding the key for `decisions_url` |
| `decisions_model` | `gpt-6-luna` | Model for the estimate |
| `board` | `true` | Telegram board on/off |
| `board_rows` | `6` | Rows on the board |
| `board_every_s` | `60` | Board refresh interval |
| `pin` | `true` | Pin the board |
| `reply_window_min` | `15` | How long after a finish to wait for the answer before showing "no reply" |

Logs go to `<profile>/logs/delegation-clock.log`, and current state goes to `logs/delegation-clock-state.json`.
