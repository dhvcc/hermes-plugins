# hermes-smart-router

A Hermes plugin that picks between GPT-6 Luna and GPT-6.1 Sol on every turn when you run on a ChatGPT/Codex subscription.

Hard work goes to Sol. Everything else goes to Luna, which costs about 20x less per output token and answers faster. In our runs that came out 30–40% cheaper and somewhat faster than Sol-only, with the same answers.

## Setup

```sh
hermes plugins install dhvcc/hermes-smart-router
```

The installer asks for an OpenAI API key and saves it to the profile's `.env` as `OPENAI_API_KEY`. If that isn't set, the plugin uses `VOICE_TOOLS_OPENAI_KEY`, which Hermes already uses for voice. Without a working key the plugin does nothing. Your Codex login stays with Hermes; the plugin never touches it.

Then use `openai-codex` with Luna or Sol as your model.

The key pays for one [Decisions API](https://developers.openai.com/api/docs/guides/decisions) call per turn: $0.10 per 1M input tokens with output free, so a fraction of a cent. ChatGPT Pro and Business plans include monthly API credits that cover it.

## How it works

1. **Classify the turn.** The Decisions API reads the new message and the last few messages and labels the turn light, standard or heavy. "Continue" after a debugging session counts as heavy. Any 30% chance of heavy counts as heavy, because a wrong "heavy" costs a bit of money and a wrong "light" costs answer quality.
2. **Heavy goes to Sol**, at your reasoning effort.
3. **Light and standard go to Luna**, at `medium` and `high` effort, never above yours. The exception is when leaving Sol would let a large prompt cache expire right before you probably need Sol again. The router prices both options with Hermes's official rates, the real cache state of each model and your pace, and keeps Sol only if that is cheaper.
4. **One model per turn.** Tool loops never switch mid-turn.

The model is chosen inside Hermes's Responses transport, before Hermes builds the request. Hermes's own history conversion, reasoning replay, streaming, retries and fallbacks stay unchanged.

If anything goes wrong, Hermes behaves as if the plugin weren't installed. The plugin never retries on its own:
- A failed routed call hands the rest of the turn back to Hermes.
- A rate-limited or missing model is skipped for a while.
- If the Decisions API fails, routing pauses for 5 minutes. A rejected key turns routing off until restart.

## Settings

All optional, in `config.yaml`:

```yaml
plugins:
  entries:
    hermes-smart-router:
      settings:
        mode: route            # or shadow: log decisions without changing anything
        light_model: gpt-6-luna
        heavy_model: gpt-6.1-sol
        light_effort: medium
        standard_effort: high
        skip_platforms: [cron]
        cache_ttl_seconds: 300
```

Each decision is logged to `logs/agent.log`:

```
smart-router: session=… tier=light (p_heavy=0.02) -> gpt-6-luna/medium, prompt~10k tokens, cheaper by $0.0136
```

## Tests

```sh
python3 -m unittest discover -s tests
```

With the Hermes runtime on `PYTHONPATH`, the same command also runs contract tests against the real Hermes transport.

## License

MIT
