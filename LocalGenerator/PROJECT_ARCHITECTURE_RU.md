# LocalGenerator v0.4.239 — Python authoring/validation architecture

LocalGenerator — Python-сторона InfiniCrafterLocal. Она принимает HTTP `/combine` от C# мода, собирает факты о родителях/мире, вызывает authoring/repair пайплайны, валидирует runtime contract, готовит финальные ассеты и возвращает `GeneratedItemData`. Terraria runtime остаётся в C#.

## Основной поток

```text
/combine request
  -> web/server.py HTTP entrypoint
  -> services/combine_endpoint.py request/concurrency boundary
  -> pipelines/combine_pipeline.py orchestration
  -> core/runtime_authoring package validates runtimePlan.engineCalls
  -> visual/VFX/sprite pipelines produce final filenames/manifests
  -> world-scoped storage/cache
  -> GeneratedItemData response for C# executor
```

## Инварианты

- `runtimePlan.engineCalls` становится executable intent только после нормализации, structural repair, semantic lowering и compile в `core/runtime_authoring/`.
- Gameplay не выводится из name/tooltip/flavor/prompt/debug prose.
- Python может чинить форму JSON, bounds и support surface; изменение identity/fantasy должно быть видно в trace/provenance.
- C# исполняет только явные bounded поля: `Gameplay`, `Attack`, `Accessory`, `Armor`, `VfxManifest`, `Visual`, exact sound catalog ids/volume/pitch/pitch variance, sprite paths, movement/effect/onHit codes.
- Asset sync отдаёт только финальные `.png/.json` через `/get_asset`; raw/intermediate generation files не являются runtime API.
- World recipe cache scoped by world id; generated parents/items/assets не смешиваются между мирами.
- LLM V3.1 stages используют self-contained authoritative dossiers: `system` задаёт stage authority, последний validator/director packet содержит достаточную current truth, `name` служит trace/provider hint, а `agentHandoff` несёт source/cause/next-stage provenance. `_llmHistory` остаётся transient integrity/replay-fixture provenance и не сериализуется в downstream requests.
- Один cache-miss item получает `LlmItemLease` и profile round-robin на весь normal multipass. `/responses`/`previous_response_id` — optional per-lease optimization; Chat fallback не меняет correctness. При provider/auth/quota/invalid-envelope failure тот же self-contained stage повторяется на следующем profile, response state сбрасывается, replacement profile закрепляется до конца item, а failed profile уходит на cooldown. Standalone разрешён только для explicit legacy/no-history data; malformed live provenance не маскируется standalone. Failed VFX repair уходит в procedural VFX recipe safety net, не меняя gameplay ownership.

## Maintainability rule for new runtime capabilities

Do not extend the project through a universal semantic graph or shared action state-machine. Follow `../docs/RUNTIME_VERTICAL_SLICES_RU.md`:

```text
one exact authored field/enum
→ one small Python policy/compiler owner
→ explicit result-model projection
→ one isolated C# executor owner
→ one end-to-end contract test
```

Derived reports are read-only diagnostics, not a second authoring surface. Explicit authored defaults/zeroes keep provenance; sparse-output behavior is unchanged.

## Canonical source layout

| Area | Canonical modules | Responsibility |
|---|---|---|
| HTTP entrypoint | `web/server.py`, `web/server_handler.py` | compose owner modules/routes, start `ThreadingHTTPServer`, map request errors to JSON |
| HTTP dependencies | `services/combine_endpoint.py`, `pipelines/pipeline_visual_config.py`, `pipelines/image_backend_pipeline.py` | request boundary and the single image/sd.cpp config + lifecycle state used by HTTP wiring |
| Utility/debug routes | `web/server_utility_routes.py`, `web/vfx_debug_routes.py`, `web/server_trace_snapshot.py`, `web/trace_dashboard.py` | route-level request handling, trace/debug payloads, asset inspection |
| Combine orchestration | `pipelines/combine_pipeline.py` | cache lookup, parent context, authoring, validation, gameplay, visual delivery, final response |
| Combine subdomains | `combine_balance.py`, `combine_genome.py`, `combine_genome_contract.py`, `combine_validation.py`, `combine_gameplay.py` | balance envelope, genome shaping/repair, planner policy, validation, gameplay attachment |
| Balance mode policy | `core/balance_mode.py` | exact `report/safety/normalize` selection only; no formulas |
| Small runtime policies | `core/runtime_secondary_policy.py`, `core/runtime_overhead_barrage_policy.py`, `core/runtime_charge_release_policy.py`, `core/runtime_sentry_policy.py` | exact vocabulary/defaults/limits for their own vertical slices |
| Secondary lowering | `core/runtime_authoring/secondary.py` | sole Python compile owner for `spawn_secondary_projectiles`, including exact `on_expire` |
| LLM authoring | `core/llm_stage_messages.py`, `llm_authoring_pipeline.py`, `llm_authoring_prompt.py`, `llm_transport.py` | initial author/VFX transport orchestration, transient Planner provenance gates, stage dossiers, item leases/pool/failover and prompt/response/auth ownership |
| Same-author repair | `author_item_repair_scope.py`, `author_item_repair_delta.py`, `author_item_repair.py` | `delta` and request assembly import `scope`; reverse imports are forbidden. Scope owns rejection evidence/provider grammar, delta owns atomic mutation/preservation, request module owns the bounded repair dossier. No helper re-exports through `llm_authoring_pipeline.py` |
| Runtime executor vocabulary | `core/runtime_executor_vocabulary.py` | единственный owner canonical movement/effect/onHit names и их C# opcodes; name-sets выводятся из keys |
| Runtime family policy | `core/runtime_family_policy.py` | strict canonical executor-family enum и одна per-family profile-table для capability/presentation metadata; no natural-language aliases |
| Sound catalog | `core/sound_catalog.py` | exact 92-role LLM vocabulary, Python/C# parity contract, bounded volume/pitch/variance controls and tiny compiled-mechanic fallbacks; no item-name/prose aliases |
| Runtime authoring | `core/runtime_authoring/__init__.py`, `vocabulary.py`, `schema.py`, `common.py`, `semantics.py`, `normalize.py`, `structural.py`, `equipment.py`, `secondary.py`, `compiler.py`, `result_identity.py`, `final_projection.py`, `reports.py` | узкий public API; authoring terminology/schema; normalization and semantic lowering; equipment/secondary lowerers; canonical result identity; single final DTO projection; validation/provenance reports |
| Runtime API version | `core/runtime_authoring/common.py` | single source of truth for `ENGINE_RUNTIME_API_VERSION` |
| Parent context | `parent_context_pipeline.py`, `parent_context_cards.py`, `pipeline_runtime_dumps.py` | compact factual parent/projectile/ammo cards and runtime dump lookup |
| Visual assets | `visual_generation_pipeline.py`, `visual_prompt_contracts.py`, `visual_asset_plan.py`, `visual_asset_manifest.py`, `visual_sprite_generation.py`, `visual_delivery_gate.py`, `visual_soul.py` | role-separated prompts, asset plan/manifest, generation, delivery gate, sprite-derived visual soul |
| Sprite processing | `sprite_contracts.py`, `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` | role contracts, geometry/keying/postprocess/validation; callers import owners directly |
| Image backends | `image_backend_pipeline.py`, `pipeline_visual_config.py`, `services/sdcpp_backend.py`, `services/sdcpp_service.py` | sd.cpp/A1111/ComfyUI/OpenAI-compatible request shaping, isolated child-process environment and service lifecycle |
| VFX | `core/vfx_manifest.py`, `vfx_manifest_config.py`, `vfx_recipe_library.py`, `vfx_director_*`, `vfx_composition_*`, `vfx_runtime_slots.py` | VFX recipes, director contract/prompt/context, composition primitives/parent/runtime slots, manifest assembly; callers import concrete owners directly |
| Storage/traces | `storage/world_storage.py`, `storage/world_recipe_runtime.py`, `storage/trace_runtime.py`, `storage/trace_tools.py`, `storage/failure_state.py`, `pipelines/generation_debug.py` | world cache, recipe serialization/delivery shape, trace events; storage shapes/persists failures while generation_debug owns the live last-combine diagnostic state |
| Desktop settings | `desktop/settings_gui.py`, `settings_gui_theme.py`, `settings_gui_ui.py`, `settings_gui_image_args.py`, `settings_gui_server_controls.py`, `settings_gui_trace_state.py`, `settings_schema.py`, `settings_env.py` | GUI shell, themed widgets, env schema, sd.cpp args, server lifecycle, trace/radmin panels |

## Production image profile

- Default local preset is FLUX.2 Klein 4B on the RX 6800 XT hybrid build: diffusion and text-encoder compute use `rocm0`, VAE compute uses `vulkan0`, and text-encoder parameters stay in CPU RAM (`--params-backend te=cpu`).
- `INFINI_SDCPP_ROCM_COMPAT_ROOT` points to the isolated HIP6-compatible sd.cpp runtime. `sdcpp_backend.build_server_process_env()` applies ROCm/HIP/rocBLAS variables only to the child `sd-server.exe`; the parent LocalGenerator process is not mutated.
- The measured idle soak20 baseline is mean 3.408 s and p95 3.441 s at 512×512, 4 steps. Game-load validation remains a separate manual check and is not a compile gate.
- Z-Image remains an explicit optional preset. Model-specific prompt contracts are selected by configuration, never by item prose.

## Runtime authoring package

`core/runtime_authoring/__init__.py` is the public package API. Он экспортирует только 14 stable compile/validate/report operations и не экспортирует schema constants или private helpers. Production-модули внутри `infini_local` импортируют конкретных owners напрямую.

- `core/runtime_executor_vocabulary.py` owns canonical movement/effect/onHit names and numeric opcodes. `dust` and `heal` exist only as authoring aliases to `smoke` and `lifesteal`.
- `core/runtime_family_policy.py` owns the strict cross-language `runtimeFamily` vocabulary and one profile row per family. Downstream consumers must not repair aliases.
- `beam` is a canonical finite family: exact `channelled_beam`/`runtimeArchetype.channel_beam` lowering only; range/homing/width/charge/cadence cross Python -> DTO -> net -> held C# executor.
- `runtime_authoring/vocabulary.py` owns only permissive movement/effect/onHit/delivery terminology accepted from the LLM boundary. It does not re-export canonical executor enums.
- `schema.py` owns the engine function catalog, Terraria-family grouping, affordance projection and numeric limits; executable enums come directly from their canonical owners.
- `common.py` owns shared authoring normalization helpers and `ENGINE_RUNTIME_API_VERSION`.

`pipelines/pipeline_support.py` удалён. Внутренние consumers импортируют symbols из реальных domain owners; compatibility facade запрещён hygiene scanner'ом.
- `semantics.py` lowers finite parent-backed/runtime-family hints into engine-call parameters.
- `normalize.py` canonicalizes `runtimePlan.engineCalls` and rejects unsupported world-entity authoring.
- `structural.py` repairs malformed plan shape without authoring new gameplay identity.
- `compiler.py` compiles accepted engine calls into explicit attack/gameplay genome patches.
- `result_identity.py` is the only runtime result-kind/category/ammo identity owner; prompt and combine layers do not re-route it.
- `final_projection.py` is the single owner of final `gameplay/attack/accessory/armor/runtimeContract` projection and its compile cache/receipts.
- `reports.py` owns quality/validation/provenance reports and typed compile result wrapping; duplicate stat owners and invalid final-wire semantics fail before composition.

## HTTP/public API shape

- `web/server.py` is the executable HTTP composition root, not a cross-domain import API.
- Root `LocalGenerator/server.py` is launcher-only and calls `web.server.main()`.
- Tests/tools import functions and state from their real owner modules (`combine_pipeline`, `llm_authoring_pipeline`, `pipeline_visual_config`, sprite/visual/service modules).
- Do not add `server_services.py`, a web API barrel, wildcard imports or `sys.modules` launcher substitution.

## Change routing

| If changing | Inspect/update |
|---|---|
| New engine call | `core/runtime_authoring/schema.py`, `normalize.py`, `compiler.py`, `reports.py`, C# `GeneratedItemData`/runtime executor, contract tests |
| Runtime family/movement/effect/onHit | Runtime authoring package, `InfiniRuntimeLimits.cs`, `GeneratedProjectile*.cs`, visual/VFX tests if presentation changes |
| LLM payload/repair | `llm_authoring_prompt.py`, `llm_authoring_pipeline.py`, `llm_transport.py`, planner prompt usability tests |
| Combine balance/gameplay | `combine_balance.py`, `combine_genome.py`, `combine_validation.py`, `combine_gameplay.py`, balance/report tests |
| Visual/sprite delivery | visual asset modules, image backend config, sprite modules, C# asset sync if filenames/status semantics change |
| Web/MP/cache boundary | `services/combine_endpoint.py`, `web/server.py`, storage modules, C# `GeneratorClient` and MP craft flow |

## Verification checklist

- `PYTHONPATH=LocalGenerator python -m compileall -q LocalGenerator/infini_local tools`
- `cd LocalGenerator && PYTHONPATH=. python -m pytest -q`
- `PYTHONPATH=LocalGenerator python tools/check_project_hygiene.py`
- `PYTHONPATH=LocalGenerator python tools/check_csharp_contracts.py`
- `PYTHONPATH=LocalGenerator python tools/check_planner_prompt_usability.py`

## Pre-livetest author/image boundary v12

- `pipelines/llm_authoring_prompt.py` advertises only executable finite calls. `spawn_temporary_helper_projectile` is temporary projectile behavior; removed function names are rejected, not migrated.
- `pipelines/visual_asset_plan.py` and `pipelines/visual_generation_pipeline.py` canonicalize visual decisions into `visualKit.bakedAssets`; old aliases are read and removed at the boundary.
- `pipelines/visual_prompt_contracts.py` owns final role framing. Exact resultKind may shape inventory-icon composition but never selects gameplay.
- `core/vfx_director_prompt.py` passes a self-contained clean accepted product dossier to the VFX+Sound Director: concept/gameplay/attack/audio facts, full canonical `VisualAssetKit`, clean parent facts, and the bounded VFX/sound-slot surface. It does not pass classifier/tag/provenance/debug packets or raw stage transcripts.
- `../docs/PRE_LIVETEST_MANUAL_TRACES_V12_RU.md` is the required negative-example map before extending these contracts.

## Charge-release + sentry v15

- `runtime_charge_release_policy.py` owns exact charge limits/conflicts; `runtime_sentry_policy.py` owns placement/interval/range/lifetime/budget and recursive-effect rejection.
- `deploy_sentry` is the only true sentry authoring call. `spawn_temporary_helper_projectile` remains a temporary helper and does not imply sentry lifecycle.
- `normalize_runtime_plan_inplace()` preserves `_rawFn` across repeated passes so provenance identifies the authored family call.
- Final fields must survive `combine_genome.py` and `combine_gameplay.py`; compiler-only GREEN is insufficient.
- Full projection proof lives in `tests/test_v15_charge_release_sentry_contract.py`.
