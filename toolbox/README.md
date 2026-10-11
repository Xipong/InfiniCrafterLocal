# No-image Live20 harness

[`live-generation/generate_20_items_without_images.py`](live-generation/generate_20_items_without_images.py) runs the frozen 20-case campaign against a **real configured text provider**. It hard-blocks image backends and substitutes a deterministic test PNG only for delivery checks; it does not accept generated sprites, Terraria gameplay or MP. The fixture belongs to the isolated campaign's canonical `SPRITE_DIR` (`OUT/cache/sprites`), so basename delivery uses the same serving-root admission as production. An existing PNG outside those roots is not delivery proof. Parent rows default to [`fixtures/items.jsonl`](fixtures/items.jsonl); `--runtime-dump` selects another dump, whose SHA-256 is recorded in the manifest.

## Offline checks / preflight

From the repository root, in the prepared [project environment](../LocalGenerator/QUICK_START_RU.md):

```bash
PYTHONPATH=LocalGenerator python -m pytest toolbox/tests -q
PYTHONPATH=LocalGenerator python toolbox/live-generation/generate_20_items_without_images.py --help
PYTHONPATH=LocalGenerator python toolbox/live-generation/generate_20_items_without_images.py \
  --project "$PWD" --output artifacts/tool-runs/live20-preflight \
  --expected-provider openai_compat --expected-model gemini-3.5-flash-lite \
  --expected-api-mode chat_completions --expected-response-format json_object \
  --expected-case-count 20 --parallel-crafts 3 --min-first-author 10 \
  --transport-retries 10 --transport-retry-delay-seconds 60 --require-no-fallback \
  --preflight-only
```

Provider/model above are **examples**, not availability claims. Configure the exact route/API mode/response format outside Git first; matching `--expected-*` validates, not configures, the effective requests. `--preflight-only` makes no network calls. Temperature, stage token limits and reasoning expectation flags are in `--help`; add them to freeze effective requests. For a clean released checkout also use `--expected-head "$(git rev-parse HEAD)"` (rejects dirty/wrong HEAD).

## Authorized live campaign

Only after approval for text calls/cost, rerun the same frozen arguments **without `--preflight-only`**, with a **new output directory**. Never commit provider config, credentials or raw traces. No login/install/model/game/publish step is implicit.

The example allows ten **case-level** repeats after confirmed network failures, at least 60 seconds apart. It does not retry malformed JSON/gameplay/domain failure at case level. This mode forces the low-level attempt budget to one; `--require-zero-transport-retries` can explicitly reject hidden logical-call retries, not the separately ledgered case repeats. Every attempt/error/scheduled and completed wait stays in the ledger.

Acceptance requires `summary.json` `ok=true`, 20 distinct successful rows, at least 10 first-Author successes, complete image-boundary coverage, no unaccounted transport errors/hidden fast HTTP retries. Report `caseTransportRetryCount` separately, not a blanket “zero infrastructure retries”. Replay all 20 recipes through the [headless C# contract](../docs/TEST_CONTRACT_OWNERS_RU.md#запуск-и-сила-доказательства); neither result replaces in-game acceptance.
