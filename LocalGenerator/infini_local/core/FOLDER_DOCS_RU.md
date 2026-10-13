# infini_local/core

Active runtime-related owners:

- `runtime_authoring/` — v5 grammar/schema/validator/compiler/wire;
- `vfx_manifest.py` — exact entity/event VFX contract;
- `strict_json.py` / `json_debug.py` — bounded JSON boundaries;
- `llm_stage_messages.py` — attributed stage messages;
- balance modules — broad numeric corridor/advice only; never movement/family selection;
- config/path/transport modules — infrastructure.
- `generation_defaults.py` — общий согласованный набор рекомендаций LLM для runtime и Studio, не gameplay defaults и не provider routing; explicit process/config overrides сохраняются.

Deleted legacy runtime-family/root-lowering/VFX macro modules must not be restored through aliases.
