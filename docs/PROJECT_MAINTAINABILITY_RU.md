# Поддерживаемость проекта / правила для AI-рефакторинга

Источник истины остаётся в активном коде, contract tests и `../AGENTS.md`; этот файл — короткая карта сопровождения для крупных изменений.

## Текущая архитектурная норма v0.4.239

- Runtime authoring живёт пакетом `LocalGenerator/infini_local/core/runtime_authoring/`.
- `runtime_authoring/__init__.py` — явный public API; sibling-модули владеют schema/common/semantics/normalize/structural/compiler/reports.
- `runtime_authoring/__init__.py` экспортирует только compile/validate/report surface; production импортирует sibling owners напрямую.
- `pipelines/pipeline_support.py` удалён; возвращать forwarding barrel запрещено hygiene scanner'ом.
- `ENGINE_RUNTIME_API_VERSION` имеет один owner: `runtime_authoring/common.py`.
- HTTP entrypoint — `infini_local/web/server.py`.
- Image/sd.cpp config и lifecycle state имеют один owner: `pipelines/pipeline_visual_config.py`.
- Tests/tools импортируют реальные owner-модули напрямую; общего `web/api.py` bucket нет.
- `combine_pipeline.py` и `llm_authoring_pipeline.py` используют только явные imports.
- Source modules не используют wildcard imports.

## Ownership map

| Boundary | Owner modules |
|---|---|
| Runtime authoring | `core/runtime_authoring/schema.py`, `common.py`, `semantics.py`, `normalize.py`, `structural.py`, `compiler.py`, `reports.py` |
| Web/HTTP | `web/server.py`, `server_handler.py`, `server_utility_routes.py`, `vfx_debug_routes.py`, `server_trace_snapshot.py` |
| Combine | `combine_pipeline.py`, `combine_balance.py`, `combine_genome.py`, `combine_genome_contract.py`, `combine_validation.py`, `combine_gameplay.py` |
| LLM authoring | `llm_authoring_pipeline.py`, `llm_authoring_prompt.py`, `llm_transport.py` |
| Parent context | `parent_context_pipeline.py`, `parent_context_cards.py`, `pipeline_runtime_dumps.py` |
| Visual/sprites | `visual_generation_pipeline.py`, `visual_*`, `sprite_contracts.py`, `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` |
| VFX | `vfx_manifest.py`, `vfx_manifest_config.py`, `vfx_recipe_library.py`, `vfx_director_*`, `vfx_composition_primitives.py`, `vfx_composition_parent.py`, `vfx_runtime_slots.py` |
| Desktop GUI | `settings_gui.py`, `settings_gui_theme.py`, `settings_gui_ui.py`, `settings_gui_image_args.py`, `settings_gui_trace_state.py`, `settings_gui_server_controls.py`, `settings_schema.py` |

## Правила контекста

AI-агент не должен читать весь проект перед каждой задачей. Минимальный набор:

1. `../AGENTS.md`.
2. `../PROJECT_ARCHITECTURE_RU.md` / `../AGENT_INDEX_RU.md` как карту.
3. Конкретные source-файлы задачи.
4. Ближайшие contract tests.
5. Таблица `If you change X, also check Y` из `../AGENTS.md`.

Не читать как архитектуру:

- `.nuget/`, `.tml-build-cache/`, `bin/`, `obj/`.
- `agent_reports/`, `build_logs/`, generated outputs.
- `.bak_*`, `Zone.Identifier`.

Важно: эти артефакты могут быть нужны для AI/debug/test/tMod окружения. Их можно игнорировать для индексации, но не удалять без явной команды.

## Правила рефакторинга

- Задача, требующая чтения больше ~800 строк source, сначала превращается в план.
- Нельзя одновременно рефакторить Python generator и C# runtime.
- Один refactor package = один ownership boundary.
- Mechanical split не должен менять поведение.
- Public API должен принадлежать своему domain owner или узкому package `__init__.py`; не создавать cross-domain barrel/facade ради тестов.
- Runtime contract changes требуют Python + C# + tests + docs вместе.
- Нельзя превращать runtime в giant name/prose/tooltip behavior map.
- Нельзя давать LLM arbitrary C# или arbitrary runtime effects.

## Проверочный минимум после каждого пакета

```bash
cd "$(git rev-parse --show-toplevel)"
PYTHONPATH=LocalGenerator python -m compileall -q LocalGenerator/infini_local tools
cd LocalGenerator && PYTHONPATH=. python -m pytest -q
cd .. && PYTHONPATH=LocalGenerator python tools/check_project_hygiene.py
PYTHONPATH=LocalGenerator python tools/check_csharp_contracts.py
PYTHONPATH=LocalGenerator python tools/check_planner_prompt_usability.py
git diff --check
```
