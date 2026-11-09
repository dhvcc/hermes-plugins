# hermes-smart-router

A Hermes plugin that picks between GPT-6 Luna and GPT-6.1 Sol on every turn when you run on a ChatGPT/Codex subscription.

Hard work goes to Sol. Everything else goes to Luna, which costs about 20x less per output token and answers faster. In our runs that came out 30–40% cheaper and somewhat faster than Sol-only, with the same answers.

## Setup

```sh
hermes plugins install dhvcc/hermes-smart-router
```

Then use `openai-codex` with Luna or Sol as your model. That's it.

For better routing, add an OpenAI API key to your profile's `.env`:

```sh
OPENAI_API_KEY=sk-...
```

The key is used for one call per turn to the [Decisions API](https://developers.openai.com/api/docs/guides/decisions). That costs $0.10 per 1M input tokens with output free, so a fraction of a cent per turn. ChatGPT Pro and Business plans include monthly API credits that cover it. Without a key, a local keyword classifier is used.

## How it works

1. **Classify the turn** as light, standard or heavy. A local classifier looks for code, stack traces, debugging, architecture, proofs and the like. With a key, the Decisions API also reads the last few messages, so "continue" after a debugging session counts as heavy. It can only raise the tier: any 30% chance of heavy counts as heavy. A wrong "heavy" costs a bit of money. A wrong "light" costs answer quality.
2. **Heavy goes to Sol**, at your reasoning effort.
3. **Light and standard go to Luna**, at `medium` and `high` effort, never above yours. The exception is when leaving Sol would let a large prompt cache expire right before you probably need Sol again. The router prices both options with Hermes's official rates, the real cache state of each model and your pace, and keeps Sol only if that is cheaper.
4. **One model per turn.** Tool loops never switch mid-turn.

The model is chosen inside Hermes's Responses transport, before Hermes builds the request. Hermes's own history conversion, reasoning replay, streaming, retries and fallbacks stay unchanged.

If anything goes wrong, Hermes behaves as if the plugin weren't installed. The plugin never retries on its own:
- A failed routed call hands the rest of the turn back to Hermes.
- A rate-limited or missing model is skipped for a while.
- A failing Decisions API falls back to the local classifier.

## Settings

All optional, in `config.yaml`:

```yaml
plugins:
  entries:
    hermes-smart-router:
      settings:
        mode: route            # or shadow: log decisions without changing anything
        classifier: auto       # or local: never call the Decisions API
        light_model: gpt-6-luna
        heavy_model: gpt-6.1-sol
        light_effort: medium
        standard_effort: high
        skip_platforms: [cron]
        cache_ttl_seconds: 300
```

Each decision is logged to `logs/agent.log`:

```
smart-router: session=… tier=light [local light, decisions light p_heavy=0.02] -> gpt-6-luna/medium, prompt~10k tokens, cheaper by $0.0136
```

## Tests

```sh
python3 -m unittest discover -s tests
```

With the Hermes runtime on `PYTHONPATH`, the same command also runs contract tests against the real Hermes transport.

## License

MIT
