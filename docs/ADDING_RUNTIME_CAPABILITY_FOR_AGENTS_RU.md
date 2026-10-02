# Добавление runtime capability — vertical slice

[Owner map](../PROJECT_MAP_RU.md) · [Author contract](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Lowering proof](TECHNICAL_LOWERING_POLICY_RU.md) · [Terraria boundary](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md)

<a id="vertical-slice"></a>
## Порядок реализации

Capability существует только после полного `registry → provider schema/prompt → validator → compiler receipts → strict wire → C# DTO/executor → tests → docs`.

1. В `capability_registry.py` объяви exact meaning, target kinds, typed params с **units/neutral/Author range/one-to-one wire projection/execution phase**, component slot/exclusivity, dependencies/events, authority/budget, finite wire paths и Python callable/C# method symbols. Percent, percentage points и multiplier различны. Runtime envelope ради исторических DTO может быть шире Author, но не уже.
2. Используй registry-generated schemas/cards. Shape owner — `program_schema.py`, model prose — `author_item_contract.py`; ручной alias/shadow registry не создавай.
3. Validator rule — metadata или общий exact rule, не выбор design default. Event producer alternatives выводи из canonical event/entity metadata; model выбирает полный вариант. Для нового error code добавь machine Repair policy и blocker closure parity, без event-name repair router.
4. Compiler пишет declared paths и receipts; [classification](TECHNICAL_LOWERING_POLICY_RU.md#transformations) и lossless proof обязательны. [Новые omission permissions](DECLARED_NEUTRAL_OMISSIONS_RU.md#dependencies) требуют совместных комбинаций, provenance и C# consumer проверки, не только optional flag.
5. Расширь strict final wire, C# DTO validation/normalize и bounded consumer; unknown opcode/reference остаётся fail closed. Authority/net sync добавь лишь для нужного instance state; owner trust нельзя выдавать за server collision proof.
6. Добавь vertical witness и acceptance fixture для нового композиционного класса; RED→GREEN regression должен ловить executable C# field без Author primitive. Deliberately internal field требует проверяемой причины в `qa/primitive_loss_audit.py`; wire-only audit полноту C# не доказывает.
7. Обнови generated outputs штатными owners, затем проверь source/generated parity, mutations, full tests и доступные C#/game seams. `notRun` фиксируется отдельно, не маскируется green static tests.

<a id="generation"></a>
## Генераторы и проверки

Из корня, Python проекта и `PYTHONPATH=LocalGenerator`:

```bash
python tools/export_contract_schemas.py
python tools/generate_lowery.py
python tools/generate_low_level_runtime_docs.py
python tools/generate_equipment_bounds.py
python tools/generate_primitive_parity.py
python -m infini_local.qa.primitive_loss_audit
```

После генерации применяй `--check`, где поддерживается; остальные parity/mutation/build commands — [AGENTS](../AGENTS.md#обязательный-vertical-slice) и [test owners](TEST_CONTRACT_OWNERS_RU.md). Это authoring workflow, **не** разрешение редактировать generated файлы вручную или менять runtime в docs-only задаче.

<a id="shortcuts"></a>
## Запрещённый shortcut

`create_<weapon>` с выбором entity/movement/delivery/lifecycle внутри — whole-weapon macro. Один exact API adapter может писать несколько обязательных technical fields лишь при declared finite outputs и доказанной эквивалентности. Facade constants, prose/name/category routers, legacy importer, arbitrary VM/generated C#, hidden repair API и mandatory classifier/judge не заменяют vertical slice.
