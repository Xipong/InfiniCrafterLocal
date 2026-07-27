# AGENTS.md — InfiniCrafterLocal v0.4.241

## Архитектурный инвариант

Gameplay Author непосредственно составляет bounded `runtimeProgram` из низкоуровневых capabilities. Код не классифицирует предмет по оружейному архетипу и не достраивает композицию поведения. Lowering разрешён только для семантически без потерь технического дублирования движка. Baseline успешного craft — Gameplay Author, Visual Director, VFX Director; Repair условен для каждой стадии. Repair всегда leaf-local и frozen-first: передавай только invalid fragments, exact missing dependencies и валидный read-only context; применяй только `fieldPermissions`/create-policy, а любые попытки изменить уже валидные значения игнорируй с audit вместо отмены полезного исправления.

## Перед изменением runtime

Прочитай:

1. корневой `lowery.md` — generated canonical boundary и owner routing;
2. `PROJECT_ARCHITECTURE_RU.md` и `PROJECT_MAP_RU.md`;
3. `docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md` и generated `docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md`;
4. `docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md`;
5. generated `TECHNICAL_LOWERING_AUDIT_RU.md`;
6. `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md`.

Owners: authored shape — `program_schema.py`; mechanical/event facts — `capability_registry.py`; lossless projections/receipts/repetition threshold — `technical_lowering.py`; model-facing prose — `author_item_contract.py`. Нельзя создавать facade/shadow contract или вручную добавлять capability только в prompt/schema/compiler/C#: требуется полный vertical slice.

## Запрещено

- whole-weapon macros и family/profile routers;
- `AttackSpec`, `weaponFamily`, `runtimeFamily` как gameplay authority;
- выбор movement/attachment/delivery/input/lifecycle из name/category/prose;
- параллельная legacy schema, migration/cache importer, hidden repair API;
- facade/shadow constants и event-name repair routers рядом с canonical owners;
- обязательный classifier/judge/critic LLM-pass;
- arbitrary VM, generated C#, reflection dispatch;
- placeholder PNG вместо обязательного asset.

## Обязательный vertical slice

`registry -> provider schema/prompt -> validator -> compiler receipts -> strict wire -> C# DTO -> C# executor -> tests -> docs`.

Команды перед упаковкой:

```bash
PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/audit_targeted_repair.py --check
PYTHONPATH=LocalGenerator python tools/audit_terraria_standardization.py --check
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
PYTHONPATH=LocalGenerator python tools/contract_parity.py
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
PYTHONPATH=LocalGenerator pytest -q
python tools/check_csharp_contracts.py
python tools/check_project_hygiene.py
python tools/validate_sandbox.py
```

Если доступны .NET 8, stable tModLoader и `ParticleLibrary.dll`/`Luminance.dll`, также выполнить C# build и игровые smoke. Отсутствие среды записывается как `notRun`, а не как успех.
