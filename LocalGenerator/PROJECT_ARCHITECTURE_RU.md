# LocalGenerator v0.4.237 — Python authoring/validation architecture

LocalGenerator is the Python side of InfiniCrafterLocal. It talks to the C# mod over HTTP, authors/validates generated item data, prepares final assets, and records debug/provenance. It is not the Terraria runtime.

## READ THIS FIRST

Mental model:

```text
/combine request from C#
  -> parent/item context + world context
  -> LLM/runtimePlan authoring
  -> code validation, repair, balance clamps, provenance
  -> final GeneratedItemData + VfxManifest + final asset filenames
  -> C# applies supported explicit fields only
```

Hard rules:
- Python may author/repair/normalize data; C# remains the bounded executor.
- `runtimePlan.engineCalls` is executable intent only after `runtime_authoring.py` validates/compiles it.
- Do not add gameplay by prose/name/tooltip routes. Parent mechanics can be preserved only through explicit parent facts/contracts.
- Typed helper results exist (`RuntimeCompileResult`, `ClampRecord`, `RepairResult`, `BalanceReportModel`), but the whole pipeline is not fully typed; many stages still use dicts. Be precise with field names and debug provenance.
- Contract stamp constants in `contract_versions.py` are observability. A stamp does not mean a future feature is implemented.
- Asset sync is final-only: expose final `.png/.json` filenames for `/get_asset`, not raw generation intermediates.
- Do not claim a second model-judge/validator exists unless a source path actually calls it.

## Current source shape

Current scan for this snapshot:
- `infini_local/`: 52 Python files, about 31k lines.
- `tests/`: 72 `test*.py` files, about 8.7k lines.
- Largest active modules are still god-file sized: `core/vfx_manifest.py`, `pipelines/combine_pipeline.py`, `desktop/settings_gui.py`, `web/server.py`, `core/runtime_authoring.py`, `pipelines/visual_generation_pipeline.py`, `pipelines/pipeline_support.py`.

This means architecture is transitional: decomposition seams exist, but do not assume the old god-files are gone.

## Source-of-truth modules

| Area | Files | Role |
|---|---|---|
| HTTP/API boundary | `services/combine_endpoint.py`, `web/server.py`, `web/server_utility_routes.py`, `web/vfx_debug_routes.py` | `/combine`, utility/debug routes, asset serving hooks |
| Main combine flow | `pipelines/combine_pipeline.py`, `combine_orchestrator.py`, `pipeline_support.py` | orchestration, parent facts, runtime/visual assembly, debug wiring |
| LLM authoring/repair | `pipelines/llm_authoring_pipeline.py`, `repair_orchestrator.py` | LLM JSON authoring and targeted runtime repair boundaries |
| Runtime compiler | `core/runtime_authoring.py` | validates/normalizes `runtimePlan.engineCalls`, compiles supported calls to game-facing fields |
| Typed result helpers | `core/result_models.py` | `RuntimeCompileResult`, `ClampRecord`, `RepairResult`, `BalanceReportModel` |
| Contract stamps | `core/contract_versions.py` | semantic version/provenance constants, not feature gates by themselves |
| Balance | `core/balance_policy.py`, `core/balance_report.py`, `pipelines/stat_profile.py`, `category_policy.py` | code-owned soft balance envelopes and debug reports |
| VFX/audio contracts | `core/vfx_manifest.py`, `core/effect_catalog.py`, `core/runtime_effect_policy.py` | VFX manifest, compact enums/catalogs, sound/effect policy |
| Assets | `services/asset_sync_service.py`, `services/visual_asset_pipeline.py`, `pipelines/visual_generation_pipeline.py`, `sprite_processing_pipeline.py`, `image_backend_pipeline.py` | final asset selection/generation/processing |
| Storage/traces | `storage/world_storage.py`, `storage/trace_tools.py`, `storage/failure_state.py` | world recipe storage, traces, failure state |
| GUI/config/env | `desktop/settings_gui.py`, `core/env_utils.py`, `core/config_bootstrap.py`, `paths.py` | settings/env/path handling |

## Runtime plan boundary

`runtimePlan.engineCalls` should be treated as an intermediate instruction list, not as arbitrary JSON to pass through blindly.

Supported path:
1. LLM proposes structured engine calls.
2. `runtime_authoring.py` normalizes, validates and compiles supported calls.
3. Compile result writes explicit game-facing fields: stats, attack, movement/effect/onHit codes, VFX/audio hints, provenance and clamp records.
4. C# receives final `GeneratedItemData` and applies only supported explicit fields.

Forbidden path:
- LLM prose → C# name/prose router → gameplay.
- Unknown engine call → silent best-effort gameplay.
- Repair path becoming a second author that changes item identity without trace.

## Change routing

| If changing | Also inspect/update |
|---|---|
| New engine call | `runtime_authoring.py`, tests for validation/compile, C# `GeneratedItemData` + runtime executor |
| Balance envelope | `balance_policy.py`, `balance_report.py`, debug/applied trace, contract tests |
| Runtime family/movement/effect/onHit | Python enums/compiler, C# `InfiniRuntimeLimits`, `GeneratedProjectile*.cs`, tests/docs |
| Asset pipeline | `asset_sync_service.py`, visual pipeline, C# `GeneratedAssetSyncService.cs`, `/get_asset` behavior |
| MP/server craft assumptions | C# `InfiniCraftPlayer.Multiplayer.cs`, Python request/world context, MP tests |
| Debug/provenance | `result_models.py`, `generation_debug.py`, trace tools, docs and tests |

## Known architecture risks

- Many internal stages still pass `dict[str, Any]`; typed helper models are a start, not the final contract boundary.
- Several modules remain large. Do not pretend decomposition is complete just because seam modules exist.
- Historical docs and reports often overclaim depth or future features. Verify source before repeating claims.
- The project philosophy is strong: LLM author, Python validator/normalizer, C# executor. The risk is accidental hidden authoring in repair/debug/runtime glue.

## Agent verification checklist

- Source of truth is the active Python code in `infini_local/`, not old reports or tiny folder stubs.
- MP assumptions must match the C# **server-authoritative** craft flow; Python prepares generated data, but host/server commits it.
- World-scoped recipe/generated data matters: verify world context and storage before changing cache/registry behavior.
- If you change X, also check Y: runtime compiler changes require C# contract/runtime/tests/docs updates.
- `dict[str, Any]` is still common; typed result models are helpful but not a complete typed pipeline.
- Do not claim a second model-judge exists unless a source path actually calls it.
