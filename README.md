# hermes-plugins

Plugins for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Each folder is one plugin, installed on its own:

```sh
hermes plugins install dhvcc/hermes-plugins/<plugin>
hermes plugins enable <plugin>
```

| Plugin | What it does |
|---|---|
| [hermes-smart-router](hermes-smart-router) | Per-turn routing between Luna and Sol on the ChatGPT/Codex subscription. Price- and cache-aware, 30–40% cheaper than Sol-only. |
| [hermes-subagent-supervisor](hermes-subagent-supervisor) | Time awareness and ownership of background subagents: deadlines, silent wake-ups, last-resort stop. |
| [hermes-subagent-widget](hermes-subagent-widget) | A pinned Telegram widget with your last subagents: progress, duration, and whether the answer reached the chat. |
| [hermes-telegram-markdown-preprocessor](hermes-telegram-markdown-preprocessor) | Deterministic Markdown cleanup for Telegram rich messages: tables, dividers, lists and `<placeholders>` that Telegram would otherwise mangle. |

Each plugin's folder has its own setup and settings.

## Moved from hermes-smart-router

This repo used to be `dhvcc/hermes-smart-router`. If you installed the router from the old path, reinstall it once:

```sh
hermes plugins install --force dhvcc/hermes-plugins/hermes-smart-router
```

## License

MIT
