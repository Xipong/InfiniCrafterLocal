# InfiniCrafterLocal v0.4.241 — карта проекта

```text
LocalGenerator/
  infini_local/core/runtime_authoring/   v5 registry/schema/Repair/validator/compiler/wire + Terraria vocabulary
  infini_local/pipelines/                Gameplay + Visual orchestration
  infini_local/core/vfx_manifest.py      VFX Director exact entity/event contract
  infini_local/storage/                  strict world-scoped v5 recipes/traces
  infini_local/qa/                       witnesses, fixtures, machine audit
  infini_local/qa/primitive_loss_audit.py AST C# DTO/executor ↔ Author coverage
  tests/                                 v5 contracts + infrastructure regression

ModSources/InfiniCrafterLocal/
  Common/Models/RuntimeProgramSpec.cs    strict C# wire DTO
  Common/Models/GeneratedEquipmentBounds.g.cs generated Author-owned numeric safety bounds
  Common/Runtime/RuntimeProgramExecutor.cs bindings/events
  Content/Items/GeneratedItem*.cs        item/use/equipment projection
  Content/Projectiles/GeneratedProjectile*.cs entity execution/net/events/visual
  Common/Models/VfxManifestSpec.cs       exact VFX slots

lowery.md                              finite alias/lowering inventory
contracts/schemas/                       generated provider contracts
docs/                                    source-facing architecture/inventory/research
tools/                                   parity, mutation, QA, packaging helpers
  generate_equipment_bounds.py / generate_primitive_parity.py  generated runtime/docs parity
```

## Главный data flow

`parents -> Gameplay Author -> strict validation -> technical compile -> v5 wire -> Visual Director -> asset delivery -> VFX Director -> strict storage -> C# registry/runtime`.

Новый pipeline не компилируется в старый weapon IR и не имеет fallback на него.

## Где добавлять механику

Начинать с `capability_registry.py`, но capability не считается существующей до появления C# executor и vertical witness. Инструкция: `docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md`.
