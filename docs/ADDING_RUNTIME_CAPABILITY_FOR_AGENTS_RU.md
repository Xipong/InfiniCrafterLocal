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


## Типизированные параметры и точные wire-проекции

Если Author объединяет связанные поля, описывайте форму и отображение в каноническом `ParamSpec`, а не отдельным provider/compiler словарём:

- `properties` задаёт закрытый object с вложенными `ParamSpec`; `alternatives` задаёт union, где ровно одна форма должна соответствовать Author. `min_properties` сохраняет явное требование непустого объекта.
- `wire_name` задаёт относительный DTO-путь листа, включая вложенный путь. `wire_enum`, `wire_offset`, `wire_multiplier` и `wire_divisor` описывают точное преобразование единиц или конечное отображение значений; округление и догадка о варианте запрещены.
- `wire_literals` принадлежит выбранному варианту параметра. Литерал получает receipt `alias_lowering` от точного пути выбранного Author-параметра. Обычные листья получают `delivered` от фактического вложенного пути.
- `CapabilitySpec.fixed_wire_literals` содержит значения, однозначно выбранные самим `fn`, с ключами относительно компонента. Compiler использует `write_derived` от `.fn`; audit требует точных value, output, call identity и единственного полного покрытия.
- `CapabilitySpec.retained_receipt_params` хранит только конечные старые скалярные проекции для аудита уже сохранённого wire без Author. Это не дополнительная Author schema, не importer и не разрешение компилировать старый синтаксис. При наличии Author источником истины остаются только текущие `params`.
- `ParamSpec.wire_presence_requires_receipt` отмечает новый скалярный event/controller параметр, для которого каждый присутствующий wire leaf требует единственного exact call receipt и entity/event ownership. Это сохраняет историческое отсутствие поля, но не позволяет приписать новый explicit selector старому payload без provenance. Пример: [child combat inheritance](CHILD_COMBAT_INHERITANCE_RU.md).

`core/schema_validation.py` владеет единственным `strict_schema_errors`; полный Author/Repair и `ParamSpec.selected_variant` используют этот же валидатор без цикла registry → program_schema. Не добавляйте второй shape matcher. Для нового варианта нужны проверки действительного compiler/receipt/Repair пути, неоднозначных и недопустимых форм, сохранения sibling-полей и старой wire-only provenance. Подробный контракт: [TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md](TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md).
