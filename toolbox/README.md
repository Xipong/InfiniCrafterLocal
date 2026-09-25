# No-image Live20 harness

`live-generation/generate_20_items_without_images.py` runs the frozen 20-case LLM campaign against a **configured** text provider. It hard-blocks image backends and uses a deterministic test PNG only to exercise delivery paths. It does not test generated sprites, Terraria gameplay, or multiplayer. Its default parent dump is the bundled `fixtures/items.jsonl` (exact Terraria runtime rows); an alternate dump must be supplied explicitly with `--runtime-dump`. The campaign manifest records the dump SHA-256.

From the repository root, use the project Python environment and `PYTHONPATH=LocalGenerator`:

```bash
PYTHONPATH=LocalGenerator python -m pytest toolbox/tests -q
PYTHONPATH=LocalGenerator python toolbox/live-generation/generate_20_items_without_images.py \
  --project "$PWD" --output artifacts/tool-runs/live20-preflight \
  --expected-provider openai_compat --expected-model gemini-3.5-flash-lite \
  --expected-api-mode chat_completions --expected-response-format json_object \
  --expected-case-count 20 --parallel-crafts 3 --min-first-author 10 \
  --transport-retries 0 --require-no-fallback --require-zero-transport-retries \
  --preflight-only
```

Configure the existing account/route outside Git before running. Explicitly set the requested API mode and response format in the environment; pass the same frozen arguments (without `--preflight-only`) and a **new output directory** for the actual campaign. To bind a released clean checkout, also pass `--expected-head "$(git rev-parse HEAD)"`. For stronger configuration checks, pass the temperature and token-budget `--expected-*` flags shown by `--help`; the runner checks stage-specific effective requests. Do not commit output traces, provider config, or credentials. Require `summary.json` `ok=true`, 20 result rows, at least 10 first-Author successes, zero retries/fallback, and complete image-boundary coverage. Replay each successful no-image recipe through the headless C# contract separately; neither check replaces in-game acceptance.
