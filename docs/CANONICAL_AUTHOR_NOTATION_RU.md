# Переход на единственный Author v5

[Текущий Author contract](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Владельцы](../PROJECT_MAP_RU.md#python) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md) · [Technical lowering](../TECHNICAL_LOWERING_AUDIT_RU.md)

## Архитектурное решение

`infini.runtime-program.authoring.v5` — единственная принимаемая Author-нотация. Её использует обычный `llm_authoring_pipeline.py`: initial Author, provider envelope, строгая локальная проверка, targeted Repair и компиляция работают с одним исходным документом. Отдельные compact schema, compiler API, pipeline, importer и source-map слой удалены.

Классификация: новая Author grammar и точный Alias Lowering выбранных ветвей и ссылок в wire; declared neutral omissions остаются явно разрешённым исключением для optional `ParamSpec`.

Форма принадлежит `program_schema.py`, факты capabilities — `capability_registry.py`, scope и frozen merge — `repair_scope.py`, технические проекции и их evidence — `technical_lowering.py`. Это описание изменения, а не второй реестр правил.

`calls` остаётся одним плоским упорядоченным массивом с явными стабильными `id`. `callGroups` не входит в грамматику: при таком решении не возникает другого порядка обхода, групповых identities или правила расширения Repair на соседние вызовы. Политика exact repetition compression с порогом 5 не ослабляется.

## Что Author больше не повторяет

| Источник | Каноническое правило | Основание проекции |
|---|---|---|
| Item-only capability | Ключ `target` отсутствует и запрещён | `CapabilitySpec.target_kinds` содержит только `item_body`; validator требует ровно одно явно объявленное тело предмета |
| Capability без параметров | Ключ `params` отсутствует и запрещён, даже для `{}` | В registry нет параметров этой capability |
| Binding | `input`, `action`, `stackCost`, `contactDamage` расположены непосредственно в binding | Единственная строгая shape; оболочки `usePolicy` в Author нет |
| `hold` | Явный `action.targetId`; `action.kind`, стоимость и contact-флаг отсутствуют | Единственный action данного input и его фиксированная транзакция |
| `equipped` | Только `id` и `input` | Единственный action данного input, единственное тело предмета, фиксированная транзакция |
| `use_item_body` / `apply_item_effects` | Явные `action.kind`, `stackCost` и `contactDamage`; `targetId` отсутствует | Action допускает только единственное тело предмета; расход и контакт остаются решением Author |
| `place_item` | Явные `action.kind` и `placementCallId`; `targetId`, `stackCost`, `contactDamage` отсутствуют | Item-only action, точная ссылка на placement call, фиксированные стоимость 1 и contact=false |
| Активный `spawn_entity` | Явные `action.kind`, `targetId`, `stackCost`, `contactDamage` | Выбор projectile, расхода и контакта остаётся решением Author |
| Intent check в `realization` | `plannedActionIndex`: integer 0..7 или `null` | Явная диагностическая ссылка вместо копии строки `plannedIntent` |

Например, вызов без параметров имеет вид `{"id":"flight","fn":"move_straight","target":"bolt"}`; equipped binding — `{"id":"worn","input":"equipped"}`. Для активного использования тела предмета форма — `{"id":"use","input":"primary_use","action":{"kind":"use_item_body"},"stackCost":0,"contactDamage":true}`. Это фрагменты уже объявленного графа, не самостоятельные предметы.

Пропуск разрешён только там, где schema и registry доказывают единственное значение. Неверное явное поле не исправляется автоматическим удалением, а получает shape error. Отсутствующее или неоднозначное тело предмета требует структурного Repair; compiler не выбирает первое подходящее entity. Для capabilities с несколькими допустимыми target kinds цель по-прежнему обязательна, даже если одним из kinds является `item_body`.

Существующий механизм [declared neutral omission](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) сохраняется отдельно: только явно optional `ParamSpec` с `default == neutral` может получить значение в приватной копии compiler после полной проверки. Пропуск в Repair-фрагменте по-прежнему означает «не менять».

## Report и Repair

`plannedActionIndex` хранится как присланное диагностическое значение. Код не подбирает индекс по тексту, не восстанавливает `plannedIntent` и не связывает `null` исключительно со статусом `added`. `concept` остаётся необязательным эскизом: отсутствие или неполнота эскиза не создаёт новый gameplay blocker. Наличие корректного index не доказывает полноту реализации замысла.

Текущий stamp scope — `infini.runtime-repair-scope.v7`: разрешённые binding-транзакции и field paths описывают новую исходную форму. Targeted Repair адресует исходные `entities`, `calls`, `bindings` и report напрямую. ID/order и frozen siblings сохраняются. В scope нет промежуточного старого Author graph и групповых адресов. Shape diagnostics выбирают точную вложенную ветку по имеющимся discriminators; отсутствующий `input`, неизвестный `action.kind` и запрещённые variant-поля должны давать ошибки на соответствующих source paths, чтобы не расширять разрешённый scope до целого документа.

Repair может явно удалить запрещённое поле в пределах разрешённого исправления. Это отличается от скрытой нормализации: исходная ошибка, patch и ignored/frozen audit остаются наблюдаемыми. Создание отсутствующего единственного `item_body` не требует переписывать все item-only calls или bindings.

## Gameplay wire и evidence

Runtime API остаётся `infini.runtime-program.v5`, wire schema — `infini.runtime-program.wire.v3`. Compiler пишет прежние gameplay DTO, включая nested `usePolicy`, и полные явные wire-значения. Author grammar и сохранённый wire имеют разные жизненные циклы.

Новые receipts связывают item-only target с исходной capability и точными `entities[i].id/kind`; binding-проекции — с исходным binding и точным entity. Identity, input, source indices, final path и значение проверяются совместно. `runtimeContract.authoringSchema` отмечает текущую provenance-форму: удаление обязательного нового evidence или подмена его прежним receipt не проходит wire audit при этом marker.

Ранее сохранённый wire v3 с исходными receipts продолжает читаться. Для этого wire consumers используют явные `wire_*` readers; старой Author schema или функции её импорта нет. Wire-only audit проверяет доступные wire/evidence связи и не утверждает, что проверил отсутствующий Author source. Если исходный Author документ предоставлен, source audit требует текущую форму и её точные зависимости.

Прежние `plannedIntent` и receipt paths внутри frozen saved-wire fixtures являются историческими диагностическими данными. Они не открывают второй путь Author. Полные сериализованные metadata bytes меняются намеренно; gameplay-проекции проверяются отдельно и точно.

## Проверка эквивалентности и размера

До изменения канонических владельцев сохранены размеры Author и SHA-256 четырёх gameplay-секций (`runtimeProgram`, `gameplay`, `accessory`, `armor`) для 8 составных fixtures и 54 capability witnesses. Baseline снят после подключения foundation `f5012379f3c814d1b22e0a69f2a676adb5272fae` к исходному PR head `9013256117587d0d30ae271a1fbe6b6cb8242367`.

[Baseline](../LocalGenerator/tests/fixtures/author_notation_baseline.json) содержит данные, а не прежнюю грамматику или encoder. Все 62 текущих native fixtures должны совпасть по этим gameplay hashes. [Отдельный saved-wire fixture](../LocalGenerator/tests/fixtures/saved_wire_v3_baseline.json) проверяет чтение старого wire без переписывания его receipts. Seed replay сохраняет прежние expected delivery wire и frozen hashes; при сравнении новой компиляции учитывается только намеренно изменившийся diagnostic report.

[Измеритель](../tools/measure_author_notation.py) воспроизводит [результат](../contracts/author_notation_measurements.generated.json) и проверяет gameplay hashes перед подсчётом. Единица — Unicode-символы JSON без пробелов; это не токены и не стоимость запроса. Strict-provider столбец учитывает существующую nullable envelope.

| Fixture | До | После | Экономия | Strict provider: до → после |
|---|---:|---:|---:|---:|
| `workbench_blade` | 5053 | 4942 | 111 | 5072 → 4961 |
| `umbrella_grenade` | 5789 | 5655 | 134 | 5807 → 5673 |
| `door_on_chain` | 3738 | 3655 | 83 | 3756 → 3673 |
| `returning_potion` | 3917 | 3834 | 83 | 3953 → 3870 |
| `fishing_platform_tool` | 3876 | 3623 | 253 | 3876 → 3623 |
| `shield_and_disc` | 5539 | 5405 | 134 | 5539 → 5405 |
| `held_and_deployed` | 6954 | 6820 | 134 | 6954 → 6820 |
| `equipment_tool_combat` | 5090 | 4665 | 425 | 5632 → 5207 |

Экономия на этих fixtures составляет 83–425 символов. Измерение охватывает Author output; оно не измеряет весь prompt, runtime context, Repair calls, billed tokens или скорость генерации. Live LLM first-pass quality, latency и игровой smoke должны публиковаться отдельными результатами; данный offline замер их не доказывает.

## Воспроизводимые проверки

Основные регрессии: `test_canonical_author_schema.py`, `test_canonical_author_wire.py`, `test_repair_native_source_contract.py`, существующие registry/Repair/pipeline/seed tests. Они проверяют строгую единственную grammar, shape paths, точный frozen Repair, сохранность gameplay, историю saved wire и подмены projection receipts.

```sh
PYTHONPATH=LocalGenerator python tools/measure_author_notation.py --check
PYTHONPATH=LocalGenerator python tools/export_contract_schemas.py --check
PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/audit_targeted_repair.py --check
PYTHONPATH=LocalGenerator python tools/audit_terraria_standardization.py --check
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
PYTHONPATH=LocalGenerator python tools/contract_parity.py
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
PYTHONPATH=LocalGenerator python -m pytest -q
python tools/check_csharp_contracts.py
python tools/check_project_hygiene.py
python tools/validate_sandbox.py
```

C# source scanner и offline delivery parity не заменяют реальную сборку tModLoader и запуск игрового runtime.
