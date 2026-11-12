# hermes-telegram-generative-ui

Your agent draws charts, tables and status cards right in the Telegram chat, as live [bot widgets](https://core.telegram.org/bots/widgets).

Two tools:

- `ui_preview` renders the page in headless Chrome at phone width and returns a screenshot, the content height, the size against Telegram's limit, script errors and anything the widget sandbox won't run. The agent looks at it and fixes the page.
- `ui_render` sends it to the current chat above the reply. `as_image=true` sends a screenshot instead, for reports that are too big or too tall for a widget. Group chats always get the image.

The page gets theme variables (`--foreground`, `--card`, `--chart-1`…) mapped to the user's Telegram theme, so it looks right in light and dark.

## Limits worth knowing

Widgets run in a sandbox, not a browser: 4096 bytes after zlib, 600px tall, no network, no external assets, only `<button>` as a control. The tool descriptions tell the model all of this.

Widgets work only in the private chat with the bot. Older Telegram apps show just the caption.

## Install

```sh
hermes plugins install dhvcc/hermes-plugins/hermes-telegram-generative-ui
hermes plugins enable hermes-telegram-generative-ui
```

Needs `TELEGRAM_BOT_TOKEN` and Chrome or Chromium for previews and images. Hermes' own browser is picked up if configured; otherwise set it:

```yaml
plugins:
  entries:
    hermes-telegram-generative-ui:
      settings:
        chrome_path: /usr/bin/chromium
```
