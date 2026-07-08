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
- C# исполняет только явные bounded поля: `Gameplay`, `Attack`, `Accessory`, `Armor`, `VfxManifest`, `Visual`, `SoundProfile`, sprite paths, movement/effect/onHit codes.
- Asset sync отдаёт только финальные `.png/.json` через `/get_asset`; raw/intermediate generation files не являются runtime API.
- World recipe cache scoped by world id; generated parents/items/assets не смешиваются между мирами.

## Canonical source layout

| Area | Canonical modules | Responsibility |
|---|---|---|
| HTTP entrypoint | `web/server.py`, `web/server_handler.py` | process env/config, compose routes, start `ThreadingHTTPServer`, map request errors to JSON |
| Web services/API | `web/server_services.py`, `web/api.py` | named dependency surface for HTTP wiring and diagnostic/tooling imports |
| Utility/debug routes | `web/server_utility_routes.py`, `web/vfx_debug_routes.py`, `web/server_trace_snapshot.py`, `web/trace_dashboard.py` | route-level request handling, trace/debug payloads, asset inspection |
| Combine orchestration | `pipelines/combine_pipeline.py` | cache lookup, parent context, authoring, validation, gameplay, visual delivery, final response |
| Combine subdomains | `combine_balance.py`, `combine_genome.py`, `combine_genome_contract.py`, `combine_validation.py`, `combine_gameplay.py` | balance envelope, genome shaping/repair, planner policy, validation, gameplay attachment |
| LLM authoring | `llm_authoring_pipeline.py`, `llm_authoring_prompt.py`, `llm_transport.py` | prompt payloads, response parsing, auth/transport/fallback, targeted repair |
| Runtime authoring | `core/runtime_authoring/__init__.py`, `schema.py`, `common.py`, `semantics.py`, `normalize.py`, `structural.py`, `compiler.py`, `reports.py` | public runtime API, enum/range schema, single runtime API version, semantic lowering, plan normalization, structural repair, compile, validation/provenance reports |
| Runtime API version | `core/runtime_authoring/common.py` | single source of truth for `ENGINE_RUNTIME_API_VERSION` |
| Parent context | `parent_context_pipeline.py`, `parent_context_cards.py`, `pipeline_runtime_dumps.py` | compact factual parent/projectile/ammo cards and runtime dump lookup |
| Visual assets | `visual_generation_pipeline.py`, `visual_prompt_contracts.py`, `visual_asset_plan.py`, `visual_asset_manifest.py`, `visual_sprite_generation.py`, `visual_delivery_gate.py`, `visual_soul.py` | role-separated prompts, asset plan/manifest, generation, delivery gate, sprite-derived visual soul |
| Sprite processing | `sprite_processing_pipeline.py`, `sprite_contracts.py`, `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` | public sprite processing API, role contracts, geometry/keying/postprocess/validation |
| Image backends | `image_backend_pipeline.py`, `pipeline_visual_config.py` | sd.cpp/A1111/ComfyUI/OpenAI-compatible image backend request shaping and service lifecycle |
| VFX | `core/vfx_manifest.py`, `vfx_manifest_config.py`, `vfx_recipe_library.py`, `vfx_director_*`, `vfx_composition.py`, `vfx_composition_*`, `vfx_runtime_slots.py` | VFX recipes, director contract/prompt/context, composition primitives/parent/runtime slots, manifest assembly |
| Storage/traces | `storage/world_storage.py`, `storage/world_recipe_runtime.py`, `storage/trace_runtime.py`, `storage/trace_tools.py`, `storage/failure_state.py` | world cache, recipe serialization/delivery shape, trace events, last failure state |
| Desktop settings | `desktop/settings_gui.py`, `settings_gui_theme.py`, `settings_gui_ui.py`, `settings_gui_image_args.py`, `settings_gui_server_controls.py`, `settings_gui_trace_state.py`, `settings_schema.py`, `settings_env.py` | GUI shell, themed widgets, env schema, sd.cpp args, server lifecycle, trace/radmin panels |

## Runtime authoring package

`core/runtime_authoring/__init__.py` is the public package API. It re-exports explicit names from sibling modules and contains no wildcard imports.

- `schema.py` owns finite movement/effect/onHit/delivery/runtime-family vocabularies, engine function catalog, aliases and numeric limits.
- `common.py` owns shared normalization helpers and `ENGINE_RUNTIME_API_VERSION`.
- `semantics.py` lowers finite parent-backed/runtime-family hints into engine-call parameters.
- `normalize.py` canonicalizes `runtimePlan.engineCalls` and rejects unsupported world-entity authoring.
- `structural.py` repairs malformed plan shape without authoring new gameplay identity.
- `compiler.py` compiles accepted engine calls into explicit attack/gameplay genome patches.
- `reports.py` owns quality/validation/provenance reports and typed compile result wrapping.

## HTTP/public API shape

- `web/server.py` is the executable HTTP entrypoint.
- `web/server_services.py` names the services, pipelines and helper functions consumed by the entrypoint.
- `web/api.py` is the canonical import target for tests/tools that need generator services without starting the server.
- Root `LocalGenerator/server.py` remains a launcher; when imported as `server` by local tooling it exposes `web.api`.

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
