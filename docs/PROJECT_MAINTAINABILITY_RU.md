# Поддерживаемость low-level runtime

## Один механический registry

`LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py` является единственным writable catalog. Schema, prompt, manifest, docs inventory и parity строятся из него.

## Узкие owners

| область | owners |
|---|---|
| Grammar/catalog | `capability_registry.py` |
| Author/Repair schema | `program_schema.py`, `pipelines/author_item_contract.py` |
| Validation | `validator.py`, `wire_validator.py` |
| Compile/lowering | `compiler.py`, `technical_lowering.py` |
| Visual | `pipelines/visual_*` |
| VFX | `core/vfx_manifest.py` |
| Storage | `storage/world_recipe_runtime.py`, `world_storage.py` |
| C# DTO | `Common/Models/RuntimeProgramSpec.cs` |
| C# execution | `Common/Runtime/RuntimeProgramExecutor.cs`, `GeneratedItem*.cs`, `GeneratedProjectile*.cs` |

## Locality rule

Изменение capability обязано менять только её declaration/vertical slice и общие generated projections. Если требуется поиск по множеству family tables, архитектура снова дрейфует.

## Gates

- machine readability audit;
- registry/schema/prompt/C# owner parity;
- strict delivery + mutation;
- non-archetypal fixtures;
- stage accounting;
- full Python suite;
- C# build/runtime smoke, когда environment доступен.
