# AGENT_INDEX_RU — InfiniCrafterLocal v0.4.239 / contract safety v18

Этот индекс нужен агенту для быстрого выбора canonical source-of-truth. Перед изменениями смотри активные файлы, а не старые отчёты.

## Главные правила

- Python/LLM авторит данные; Python валидирует и компилирует contract; C# исполняет только поддержанные explicit fields.
- Не выводить gameplay из prose/name/tooltip/prompt/debug strings.
- `runtimePlan.engineCalls` проходит через `LocalGenerator/infini_local/core/runtime_authoring/`.
- `ENGINE_RUNTIME_API_VERSION` находится в `core/runtime_authoring/common.py`.
- HTTP entrypoint — `web/server.py`; diagnostics/tests/tools import their pipeline/service/config owners directly.
- В source-коде нет wildcard imports; публичные поверхности импортируют явные имена.

## Куда идти по задаче

| Задача | Читать/менять |
|---|---|
| Запуск HTTP генератора | `LocalGenerator/server.py`, `infini_local/web/server.py`, `web/server_handler.py` |
| `/combine` request/response/failure status | `services/combine_endpoint.py`, `web/http_response_helpers.py`, `pipelines/combine_pipeline.py` |
| Runtime engine calls | `core/runtime_authoring/schema.py`, `engine_call_contracts.py`, `common.py`, `normalize.py`, `structural.py`, `semantics.py`, `compiler.py`, `reports.py` |
| LLM payload/auth/repair | `pipelines/llm_authoring_prompt.py`, `llm_authoring_pipeline.py`, `llm_transport.py` |
| Parent facts/cards | `pipelines/parent_context_pipeline.py`, `parent_context_cards.py`, `pipeline_runtime_dumps.py` |
| Runtime taxonomy/authoring | `core/runtime_executor_vocabulary.py`, `core/runtime_family_policy.py`, `core/runtime_authoring/vocabulary.py`, `schema.py`, `compiler.py` |
| Overhead projectile delivery | `core/runtime_overhead_barrage_policy.py`, `core/runtime_authoring/semantics.py`, `GeneratedOverheadBarragePolicy.cs`, `GeneratedProjectile.OverheadBarrage.cs`; theme remains in authored projectile/effect fields |
| Balance/genome/gameplay | `combine_balance.py`, `combine_genome.py`, `combine_genome_contract.py`, `combine_validation.py`, `combine_gameplay.py`, `runtime_presentation_policy.py` |
| Visual Director/prompts/assets | `visual_director_contract.py`, `visual_generation_pipeline.py`, `visual_prompt_contracts.py`, `visual_asset_plan.py`, `visual_sprite_generation.py`, `visual_asset_manifest.py`, `visual_delivery_gate.py` |
| Sprite postprocess | `sprite_contracts.py`, `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` |
| Image backend | `image_backend_pipeline.py`, `pipeline_visual_config.py`, `services/sdcpp_backend.py`, `services/sdcpp_service.py` |
| VFX manifest/director | `core/vfx_manifest.py`, `vfx_manifest_config.py`, `vfx_recipe_library.py`, `vfx_director_context.py`, `vfx_director_prompt.py`, `vfx_director_contract.py`, `vfx_composition_primitives.py`, `vfx_composition_parent.py`, `vfx_runtime_slots.py` |
| Storage/tracing | `storage/world_recipe_runtime.py`, `storage/world_storage.py`, `storage/trace_runtime.py`, `storage/failure_state.py` |
| Settings GUI | `desktop/settings_gui.py`, `settings_gui_theme.py`, `settings_gui_ui.py`, `settings_gui_image_args.py`, `settings_gui_server_controls.py`, `settings_gui_trace_state.py`, `settings_schema.py` |
| C# runtime execution | `ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData*.cs`, `Content/Projectiles/GeneratedProjectile*.cs`, `Content/Projectiles/GeneratedChildSpecPolicy.cs`, `Common/InfiniRuntimeLimits.cs` |
| Multiplayer craft | `Common/Players/InfiniCraftPlayer.Multiplayer.cs`, `Common/Services/GeneratorClient.cs`, `InfiniNetPacketIds.cs` |

## Verification commands

```bash
python tools/agentctl.py verify --changed
PYTHONPATH=LocalGenerator python -m compileall -q LocalGenerator/infini_local tools
cd LocalGenerator && PYTHONPATH=. python -m pytest -q
cd .. && PYTHONPATH=LocalGenerator python tools/contract_parity.py --quiet
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
PYTHONPATH=LocalGenerator python tools/semantic_runtime_diff.py
PYTHONPATH=LocalGenerator python tools/runtime_impact_report.py
PYTHONPATH=LocalGenerator python tools/config_registry.py --check
PYTHONPATH=LocalGenerator python tools/check_project_hygiene.py
PYTHONPATH=LocalGenerator python tools/check_csharp_contracts.py
PYTHONPATH=LocalGenerator python tools/check_planner_prompt_usability.py
```
