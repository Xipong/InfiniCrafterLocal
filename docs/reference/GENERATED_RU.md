# Generated canonical contracts — 0.5.00

**Полные generated projections сохранены на исходных путях.** Они читают canonical source, не заменяют его и не копируются в краткие руководства. Ручная правка каталога запрещена: меняй source/producer у его владельца.

| Полный output | Producer | Запись без `--check` |
|---|---|---|
| [lowery.md](../../lowery.md) | [generate_lowery.py](../../tools/generate_lowery.py) | Только root `lowery.md` |
| [Capability inventory](../LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [machine-readability audit](../CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md), [lowering audit](../../TECHNICAL_LOWERING_AUDIT_RU.md) | [generate_low_level_runtime_docs.py](../../tools/generate_low_level_runtime_docs.py) | Ровно три Markdown projections |
| [Primitive parity](../PRIMITIVE_PARITY_RU.md) | [generate_primitive_parity.py](../../tools/generate_primitive_parity.py) | Только `docs/PRIMITIVE_PARITY_RU.md` |

Из корня в подготовленном dev-окружении:

```bash
PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py --check
```

Для согласованного обновления Markdown убери `--check` у нужного producer, затем проверь freshness и affected regression. [export_contract_schemas.py](../../tools/export_contract_schemas.py) обслуживает отдельные JSON/schema exports; это **не** Markdown-only команда. `contracts/schemas/`/C# bounds не обновляются при переносе документации.

Canonical owners: [registry](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — факты/params; [program_schema](../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py) — authored shape; [technical_lowering](../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py) — projections/receipts; [author_item_contract](../../LocalGenerator/infini_local/pipelines/author_item_contract.py) — model-facing prose. [Vertical slice](../development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md).

Freshness означает совпадение с renderer, **не** свежий benchmark/100% acceptance. Исторические hardcoded числа читаются в рамках своего снимка; live/game/MP проверяются отдельно. Совместимые old-path entrypoints сохраняют anchors для producer/AGENTS/tool consumers.
