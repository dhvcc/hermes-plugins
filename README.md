# hermes-plugins

Small plugins for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Each one does one thing, so take only what you need.

```sh
hermes plugins install dhvcc/hermes-plugins/<plugin>
hermes plugins enable <plugin>
```

| Plugin | What it does |
|---|---|
| [hermes-smart-router](hermes-smart-router) | Picks Luna or Sol for each turn on a ChatGPT/Codex subscription. 30–40% cheaper than Sol only. |
| [hermes-subagent-supervisor](hermes-subagent-supervisor) | The agent stops forgetting background subagents: deadlines, quiet check-ins, kills stuck ones. |
| [hermes-subagent-widget](hermes-subagent-widget) | A pinned Telegram widget with your last subagents. |
| [hermes-telegram-markdown-preprocessor](hermes-telegram-markdown-preprocessor) | Fixes Markdown that Telegram would break: tables, lists, `<placeholders>`. |
| [hermes-offline-status](hermes-offline-status) | One silent "restarting" message instead of Hermes' shutdown and online pings. |
| [hermes-telegram-generative-ui](hermes-telegram-generative-ui) | The agent draws charts, tables and cards in the chat as Telegram widgets. |

Installed the router from the old `dhvcc/hermes-smart-router` path? Reinstall it once:

```sh
hermes plugins install --force dhvcc/hermes-plugins/hermes-smart-router
```

MIT
