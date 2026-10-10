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
python tools/audit_targeted_repair.py --output contracts/targeted_repair_audit.generated.json
python tools/audit_terraria_standardization.py --write
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
- `ParamSpec.wire_presence_requires_receipt` отмечает новый scalar/composite параметр, для которого каждый присутствующий wire leaf требует единственного exact call receipt и entity/event ownership. Compound variant проверяется целиком: branch literals, source paths, JSON types, call ID и полное уникальное покрытие. `_wire_projection_witness` проверяет полные конечные typed records через единственный `ParamSpec.matches_scalar_projection` и `matches_projection_records`, не восстанавливает inverse Author, не выбирает недостающий variant и возвращает только exact projection rows. Историческое отсутствие поля сохраняется; новый explicit selector нельзя приписать старому payload без provenance. Примеры: [child combat inheritance](CHILD_COMBAT_INHERITANCE_RU.md), [velocity/target geometry](SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md).
- `CapabilitySpec.wire_action` объявляет event fn alias, который использует прежние action/name и opcode. Compiler применяет общий event projector; `fixed_wire_literals` автоматически получает exact action/actionCode. Старый fn не становится вторым свежим spelling нового варианта; receipt owner остаётся фактическим authored fn.

Составные числовые поля требуют рекурсивного обхода `properties`/`alternatives` в range parity. Для strict nullable C# setters владелец `qa.primitive_loss_audit.nullable_number_rejection_bounds` доказывает реальные bounds для `float?`, `double?`, `int?`, finite floating guards и exact backing assignment по AST. Это source proof; native исполнение проверяется отдельным harness.

`RequirementSpec.other_param` связывает два выбранных листа для `ordered_params` и `present_param_requires_param_value`. `referenced_param_presence_requires_value` использует `other_param` как entity reference, `capability` как child capability, `any_of` как список nested child paths, а `param/equals` как ограничение на исходный call. Пример: radial/disk child требует нулевой event spread. Такой reference constraint, `referenced_entity_capability_params`, `referenced_entity_without_capability` и отрицательный `present_param_forbids_capability` не являются локальными create dependencies. Repair не имеет права обходом этих правил добавлять capabilities к корректному target или менять frozen child. Политика ссылок — [REFERENCED_ENTITY_REQUIREMENTS_RU.md](REFERENCED_ENTITY_REQUIREMENTS_RU.md).

`core/schema_validation.py` владеет единственным `strict_schema_errors`; полный Author/Repair и `ParamSpec.selected_variant` используют этот же валидатор без цикла registry → program_schema. Не добавляйте второй shape matcher. Для нового варианта нужны проверки действительного compiler/receipt/Repair пути, неоднозначных и недопустимых форм, сохранения sibling-полей и старой wire-only provenance. Подробный контракт: [TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md](TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md).
