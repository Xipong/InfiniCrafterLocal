# LocalGenerator 0.4.246 — low-level runtime architecture

LocalGenerator авторит и валидирует данные; Terraria исполняет typed v5 wire.

## Gameplay

`pipelines/llm_authoring_prompt.py` строит один self-contained Author payload из parent packets, balance corridor, grammar и всех 52 capabilities. `llm_authoring_pipeline.py` делает один baseline вызов. `combine_pipeline.py` после детерминированного отказа может вызвать ровно один leaf-local Gameplay Repair. `core/runtime_authoring/repair_scope.py` выводит exact field permissions, blocker/support closure и frozen read-only context; full valid item и прежняя planner history в Repair не отправляются. Лишние правки модели игнорируются с audit, а не отменяют полезное исправление.

`core/runtime_authoring/validator.py` использует registry metadata для target kinds, references, requirements, component slots, event producers, cycles и budgets. Он не выбирает замену за модель.

## Visual/VFX

Visual получает `runtime_visual_roles()` из принятых entities. VFX получает `runtime_event_inventory()`, точный read-only runtimeProgram без entity visual payload и может создать слот только для существующей пары entity/event. Optional asset declarations нового VFX-контракта проходят тот же последующий image pass; одна декларация/ID может обслуживать несколько элементов без нескольких image jobs. Missing required PNG остаётся ошибкой. См. `../docs/VFX_MATERIAL_ELEMENTS_RU.md`; четвёртая текстовая LLM-стадия не добавляется.

## Storage

`storage/world_recipe_runtime.py` принимает только strict v5 recipe. Старый `AttackSpec`/family/cache payload не импортируется.

## Source-of-truth правило

Механические schema/prompt/docs должны быть проекциями `capability_registry.py`; ручные дубли запрещены. `tools/audit_capability_library.py` и `tools/generate_low_level_runtime_docs.py --check` являются обязательными gates.
