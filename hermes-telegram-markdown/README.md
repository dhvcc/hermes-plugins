# hermes-telegram-markdown

Fixes LLM Markdown before Hermes sends it to Telegram as a rich message. It runs as plain code (no LLM call, no prompt rules) and takes about 0.03 ms per reply.

Telegram's rich-message parser is not plain GFM. Every rule below was checked against Telegram itself: the original shape parses wrong, and the fixed shape parses right.

| What the model writes | What Telegram does | Fix |
|---|---|---|
| A table right under a text line | Glues everything into one paragraph | Blank line before the table |
| A delimiter row whose column count differs from the header | Drops the table | Rebuild the delimiter row |
| `text` followed by `---` on the next line | Turns the text into a heading | Blank lines around the divider |
| `2.` / `3.` list right under a text line | Leaves it as plain text | Blank line before the list |
| A plain line after a list or quote | Pulls it into the last item or the quote | Blank line after the block |
| `<pod>`, `List<String>`, `<id>` | Deletes them silently | `&lt;pod&gt;` |
| `#89 closed` at the start of a line | Makes it a heading | `\#89` |
| `__init__` | Shows it as bold `init` | `` `__init__` `` |
| `5 * 3 * 2` | Italicises ` 3 ` | `\*` |
| Unclosed ```` ``` ````, `~~~` fences | Breaks the code block | Close it, use ```` ``` ```` |

Code spans, fenced code and URLs are never touched. The output is idempotent.

## Install

```sh
hermes plugins install dhvcc/hermes-plugins/hermes-telegram-markdown
hermes plugins enable hermes-telegram-markdown
```

Restart the gateway. It applies only to `platform: telegram`. You can change that with `plugins.entries.hermes-telegram-markdown.settings.platforms: [telegram, ...]`.

## Tests

- `python tests/test_tgmd.py` is the offline golden test over 77 cases.
- `TELEGRAM_BOT_TOKEN=... CHAT_ID=... python tests/live_check.py` re-checks every case against Telegram's parser. It sends each message silently and deletes it immediately.
