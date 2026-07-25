# AGENT_INDEX_RU — low-level runtime v5

| задача | canonical owners |
|---|---|
| Runtime grammar/catalog | `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py` |
| Author/Repair schema | `program_schema.py`, `pipelines/author_item_contract.py` |
| Deterministic validation | `runtime_authoring/validator.py`, `wire_validator.py` |
| Compiler/receipts | `runtime_authoring/compiler.py`, `technical_lowering.py` |
| Gameplay LLM | `pipelines/llm_authoring_prompt.py`, `llm_authoring_pipeline.py` |
| Three-stage orchestration | `pipelines/combine_pipeline.py` |
| Visual entities/assets | `pipelines/visual_*`, `visual_asset_manifest.py`, `visual_delivery_gate.py` |
| VFX entity/events | `core/vfx_manifest.py` |
| Storage | `storage/world_recipe_runtime.py`, `world_storage.py` |
| Machine QA | `qa/capability_library_audit.py`, `capability_witnesses.py`, `runtime_program_fixtures.py` |
| C# DTO | `Common/Models/RuntimeProgramSpec.cs` |
| C# item bindings | `Content/Items/GeneratedItem*.cs`, `Common/Runtime/RuntimeProgramExecutor.cs` |
| C# entities | `Content/Projectiles/GeneratedProjectile*.cs` |
| C# VFX | `Common/Models/VfxManifestSpec.cs`, VFX runtime services |

Нельзя искать старые `function_contract_registry`, root lowering, family policy, child spec policy или whole-weapon partials: они удалены.
