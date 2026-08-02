# ModSources/InfiniCrafterLocal — tModLoader runtime

Это конечный typed executor `runtimeProgram` v5.

## Owners

- `Common/Models/RuntimeProgramSpec.cs` — strict DTO, versions, bounds, refs, events, component dependencies.
- `Common/Runtime/RuntimeProgramExecutor.cs` — explicit item bindings and event actions.
- `Common/Models/GeneratedItemData*.cs` — v5 JSON normalize/application, без `AttackSpec`.
- `Content/Items/GeneratedItem.cs` и `.UseStyle.cs` — primary/alternate/hold/equipment binding dispatch.
- `Content/Projectiles/GeneratedProjectile.cs` — entity bootstrap.
- `.Executors.cs` — finite movement/controller opcode dispatch.
- `.RuntimeEvents.cs` — bounded event actions/authority.
- `.NetSync.cs` — compact required instance state.
- `.Visuals.cs` — entity visual role/assets, не weapon family.
- `Common/Models/VfxManifestSpec.cs` — exact `entityId + event` VFX slots.

## Правила

- Authored/generated tooltip output запрещён; gameplay не выводится из name/category/tags.
- Не добавлять sensible defaults по типу оружия.
- Unknown version/kind/opcode/reference/action/input — fail closed.
- Owner/server authority и spawn budgets обязательны.
- Новый opcode публикуется Gameplay Author только после полного Python→C# vertical slice.
- Shared projectile type не получает глобальные sentry/yoyo/flail flags; поведение задаётся instance DTO.
