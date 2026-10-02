# Агенту: от задачи к владельцу

Сначала [AGENTS.md](AGENTS.md), затем нужный документ из [индекса](docs/README_RU.md). [PROJECT_MAP_RU.md](PROJECT_MAP_RU.md) описывает дерево, а эта таблица — **куда вносить конкретное изменение**. Source/registry/schema имеют приоритет над prose и историческими аудитами.

| Задача | Владелец и граница |
|---|---|
| Capability, entity/input/action/event grammar | [capability_registry.py](LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py); полный vertical slice по [инструкции](docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) |
| Author/Repair JSON shape | [program_schema.py](LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), [author_item_contract.py](LocalGenerator/infini_local/pipelines/author_item_contract.py); generated exports вручную не меняются |
| Semantic validation / compile / receipts | [validator.py](LocalGenerator/infini_local/core/runtime_authoring/validator.py), [compiler.py](LocalGenerator/infini_local/core/runtime_authoring/compiler.py), [technical_lowering.py](LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py), [wire_validator.py](LocalGenerator/infini_local/core/runtime_authoring/wire_validator.py) |
| Exact Repair permissions / frozen merge | [repair_scope.py](LocalGenerator/infini_local/core/runtime_authoring/repair_scope.py), [repair_merge.py](LocalGenerator/infini_local/core/repair_merge.py); корректные siblings остаются frozen |
| Структура LLM-стадий / транспорт | [combine_pipeline.py](LocalGenerator/infini_local/pipelines/combine_pipeline.py), [llm_authoring_pipeline.py](LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py), [llm_transport.py](LocalGenerator/infini_local/pipelines/llm_transport.py); provider routing не выбирает механику |
| Visual / VFX / image lifecycle | [visual_generation_pipeline.py](LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py), [vfx_manifest.py](LocalGenerator/infini_local/core/vfx_manifest.py), [visual_sprite_generation.py](LocalGenerator/infini_local/pipelines/visual_sprite_generation.py); принятые gameplay/Visual boundaries не переавторятся |
| World storage и delivery | [world_storage.py](LocalGenerator/infini_local/storage/world_storage.py), [world_recipe_runtime.py](LocalGenerator/infini_local/storage/world_recipe_runtime.py), [visual_delivery_gate.py](LocalGenerator/infini_local/pipelines/visual_delivery_gate.py) |
| C# DTO / execution / authority | [Models](ModSources/InfiniCrafterLocal/Common/Models/FOLDER_DOCS_RU.md), [Runtime](ModSources/InfiniCrafterLocal/Common/Runtime/FOLDER_DOCS_RU.md), [Items](ModSources/InfiniCrafterLocal/Content/Items/FOLDER_DOCS_RU.md), [Projectiles](ModSources/InfiniCrafterLocal/Content/Projectiles/FOLDER_DOCS_RU.md), [VFX](ModSources/InfiniCrafterLocal/Common/VFX/FOLDER_DOCS_RU.md) |
| Regression, witness, replay или audit | [QA](LocalGenerator/infini_local/qa/FOLDER_DOCS_RU.md), [контрактные тесты](docs/TEST_CONTRACT_OWNERS_RU.md), [tools](tools/FOLDER_DOCS_RU.md) |

Не восстанавливай удалённые family/root-lowering/child-spec policies через новые aliases. Если изменение требует параллельных таблиц поведения, сначала проверь canonical ownership, а не размножай prose или тестовые snapshots.
