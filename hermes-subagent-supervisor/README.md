# hermes-subagent-supervisor

Hermes can run subagents in the background, then forget about them. Nobody notices when one hangs, and the answer you were promised never comes. This plugin makes the agent keep track of them.

- Every turn, the agent sees the current time and its running subagents: how long each has run, its deadline, and the command it is stuck in.
- Each subagent gets a deadline: `ETA: 25m` in the task, otherwise an estimate (one cheap OpenAI Decisions API call), otherwise 15 min.
- When a subagent runs past its deadline or hangs in one command for 10+ min, the agent is woken up quietly. It gives the subagent more time, corrects it, or stops it. You see nothing unless it stopped one or your answer will be late.
- A subagent at 3× its deadline with no progress gets stopped, and you get one line about it.

Pair it with [hermes-subagent-widget](../hermes-subagent-widget) to see all of this in Telegram.

## Install

```sh
hermes plugins install dhvcc/hermes-plugins/hermes-subagent-supervisor
hermes plugins enable hermes-subagent-supervisor
```

It wakes the agent by injecting a message, so allow that in `config.yaml`, then restart the gateway:

```yaml
plugins:
  entries:
    hermes-subagent-supervisor:
      allow_gateway_injection: true
```

## Settings

Put these under `plugins.entries.hermes-subagent-supervisor.settings`. The defaults are fine.

| Key | Default | |
|---|---|---|
| `default_eta_min` | `15` | Deadline when there is no ETA and no estimate |
| `hang_alert_min` | `10` | Minutes in one command before it counts as stuck |
| `kill_factor` | `3` | Stop a silent subagent at this many times its deadline |
| `decisions_url` | OpenAI | `""` turns estimates off |
| `api_key_env` | `OPENAI_API_KEY` | Key for the estimate |
| `language` | `en` | `en` or `ru`, for the "stopped" message |
