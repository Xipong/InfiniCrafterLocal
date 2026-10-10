# Типизированные параметры Author: точная проекция

Canonical owner — `core/runtime_authoring/capability_registry.py::ParamSpec`; форма всего документа остаётся в `program_schema.py`. Эта инфраструктура сама не добавляет новых gameplay операций и не принимает прежние Author spelling как aliases.

`ParamSpec.properties` описывает группу явных полей; `alternatives` — конечный взаимоисключающий выбор. В schema это строгие object/oneOf с `additionalProperties=false`. Отсутствующий либо неоднозначный вариант отвергается. Неизвестные поля, неправильные значения и отсутствующие обязательные листья не заполняются.

Provider projection разрешает `oneOf → anyOf` только после доказательства
непересечения каждой пары: разные JSON types, непересекающиеся required finite
domains либо required key, который запрещён закрытым object другой ветви.
Разные пары могут иметь разные discriminators; numeric `integer/number` и
JSON-equal `1/1.0` не считаются непересекающимися. Optional ancestors и
`patternProperties`, допускающие спорный key, не дают такого доказательства.
Это lossless transport **Normalization**, без изменения Author choices/wire.

Nullable inverse использует только эти узкие selectors, а не успешную проверку
всей ветви. Неверный соседний параметр остаётся доступен Repair; required null,
unknown keys, отсутствующий выбор и конфликтующие object alternatives остаются
RED. Singleton union также проверяет свой required literal discriminator.
`test_provider_union_proof.py` проводит typed registry choices через реальный
Author request и Repair inverse, проверяет границы и отказ при overlap.

`projected_fields(value, name)` возвращает точные пары `authored_path → wire_path/value`. Вложенность Author не обязана менять C# DTO. Каждый leaf применяет свой прежний ParamSpec, включая units, consumer storage и bounds. `wire_enum` допускает лишь зарегистрированное отображение токена; `wire_offset` — точное целочисленное смещение. Ни один из них не использует name/category/prose либо состояние игры.

`wire_literals` принадлежит явно выбранному варианту. Его constants имеют статус receipt `alias_lowering` и source path самого выбора; код не делает вид, будто отсутствующий scalar был передан моделью. Полный конечный список source/output pairs выводится `projection_paths()`, а список wire fields — `wire_field_names()`. Дублирование одного output несколькими решениями в одном варианте отвергается.

Compiler сохраняет точные nested source paths в receipts. Source-aware audit проверяет текущие schema/type/domain через `ParamSpec.projected_fields`, связывает final entity ID с точным target исходного call и final event ID с его callId независимо от сортировки arrays. Требуется единственное полное покрытие outputs. Подмена source-only target, согласованная подмена wire+receipt owner, bool/int/float, исчезновение или дублирование receipts дают RED.

Wire-only audit удостоверяет только согласованность заявленных source/output paths с wire, не происхождение отсутствующего Author (`authoredSourceChecked=false`). `ParamSpec.matches_projection_records` требует ровно один полный registered variant: нельзя собрать discriminator одной ветви с domain/outputs другой. Проверяются и текущие scalar domains; прежние domains допустимы лишь через явный `retained_receipt_params`, включая прежний domain параметра с сохранившимся именем. Ни одна проверка не меняет принятые wire/receipt bytes.

Numeric/consumer validation идёт по присутствующим реальным leaves. Neutral omission остаётся отдельным контрактом: object grouping не объявляет новые defaults.

Для известной union-ветки shape validator сообщает точную невалидную leaf. Общая ошибка oneOf не расширяет Repair permissions, когда есть точный descendant. Уже корректные соседи и принятое отсутствие остаются frozen; omission в patch означает «не менять».

Проверки: `LocalGenerator/tests/test_registry_structured_params.py` использует реальный compiler существующего C# collision DTO, проверяет все источники receipts, отрицательные варианты и leaf-local Repair scope. Production vocabulary и прежние scalar projections не меняются этим foundation.

## Сохранённые receipts

При замене canonical Author поля его прежняя scalar projection может быть явно зарегистрирована в `CapabilitySpec.retained_receipt_params`. Это внутренний конечный список прежних source paths, wire paths, типов, domains и conversions. Он не экспортируется в Author/Repair schema, cards или compiler и не позволяет новую генерацию по прежнему spelling.

Только audit без исходного Author принимает такую запись: проверяет прежнюю exact пару и фактическое wire значение, не переписывая документ, IDs, hashes и receipts. При наличии Author всегда действует текущий canonical source contract. Неизвестный прежний path остаётся RED. Отсутствие исходного Author никогда не превращается в `authoredSourceChecked=true`.

Для integer/lattice projections проверяется точное преобразование; для небиективного binary64 деления — прежний wire domain без выдуманного восстановления исходного float. Это предел wire-only проверки, а не миграция и не разрешение approximate Author conversion.

`CapabilitySpec.fixed_wire_literals` описывает constants, выбранные самим canonical `fn`, например неиспользуемый радиус конкретного owner-only pull. Keys — пути относительно component prefix. Compiler обязан писать их через `write_derived`, source — точный `.fn`, status — `technical_projection`. Audit проверяет значение, конечный declared output, originating call id/fn и уникальную полную coverage. Этот механизм не определяет новые constants автоматически.

`core/schema_validation.py` — единственный нижний owner строгой проверки JSON shape. `program_schema.py` экспортирует этот же валидатор для полного Author и Repair; `ParamSpec.selected_variant` вызывает его напрямую без обратной зависимости registry → program_schema.
