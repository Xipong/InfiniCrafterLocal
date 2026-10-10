# Компактная версия Author: исходные пути, точная проекция и Repair

Категории аудита D1–D7. Классификация: явная новая версия authored notation,
точное alias lowering в прежний canonical graph и три отдельно объявленных
neutral omissions. Gameplay runtime, wire version, IDs, event order и числовые
решения не выводятся из имени, категории или соседних параметров.

## Статус и выбор версии

Версия `infini.runtime-program.authoring.compact.v1` выбирается отдельным API
`infini_local.pipelines.compact_author_pipeline`. Существующий генератор
продолжает запрашивать свою текущую Author version. Ошибка JSON, неизвестный fn,
неподходящая grammar или Repair не переключают версию автоматически.

Новый API предоставляет `build_compact_author_request`, `request_compact_author`,
`build_compact_repair_request` и `request_compact_repair`. Каждая `request_*`
функция делает ровно один явно запрошенный model call. Транспорт использует
общие параметры модели и фактический `responseFormatType`/downgrade metadata.
Nullable optional encoding удаляется только при доказанной strict-provider
projection; произвольный null в обычном JSON остаётся ошибочным значением.

Пример явного вызова из Python после получения recipe inputs:

```python
from infini_local.pipelines.compact_author_pipeline import request_compact_author
from infini_local.core.runtime_authoring.compact_api import compile_compact_author

authored = request_compact_author(a, b, ca, cb, recipe_key, model_name=model)
compiled = compile_compact_author(authored)
```

Это реальный opt-in entrypoint, не автоматическая миграция сохранённых предметов.
`compile_compact_author` возвращает прежний gameplay wire и дополнительные
доказательства происхождения внутри `runtimeContract`. Обычная delivery boundary
по-прежнему не посылает этот диагностический контракт в C# DTO.

## Решения модели и новая форма

| Категория | Новое authored правило | Доказательство точности |
|---|---|---|
| D1 | Поля policy находятся прямо в binding | Projection восстанавливает единственный `usePolicy`; значения не меняются |
| D2 | Выбранная ветвь omits только свои fixed constants | Schema запрещает эти свойства даже с формально правильным значением; compiler берёт constants из registry variant |
| D3 | Item-only calls/actions не повторяют item target | Resolver требует ровно один явно объявленный `item_body` с уникальным ID |
| D4 | Последовательные `callGroups` задают target один раз | Flatten идёт по group order, затем call order; IDs сохраняются буквально |
| D5 | Report содержит `plannedActionIndex` | Точная zero-based ссылка в frozen concept; совпадающий текст двух rows не меняет индекс |
| D6 | Zero-argument fn не содержит `params` | Только fn с пустым registry params получает canonical `{}` |
| D7 | Нулевые axe/hammer и healMana можно опустить | Только три registry leaves имеют новые `default=neutral=0`; omission receipt отличается от authored zero |

Фрагмент compact program с уже объявленными entities `item` и `bolt`:

```json
{
  "callGroups": [
    {
      "calls": [
        {"id":"tool","fn":"configure_tool","params":{"pickPower":100,"miningSpeedScale":1}}
      ]
    },
    {
      "target":"bolt",
      "calls":[
        {"id":"life","fn":"set_projectile_lifetime","params":{"lifetimeTicks":150}},
        {"id":"motion","fn":"move_straight"}
      ]
    }
  ]
}
```

Это фрагмент notation, не полный playable item: остальные обязательные components,
bindings, concept и realization сохраняют свои обычные требования.

Группа без `target` разрешает только capabilities, чья полная target-kind область
равна `[item_body]`. Capability, которая работает и на item, и на projectile,
по-прежнему требует явный group target даже при выборе item. Projectile action
сохраняет точный `targetId`; его `primaryEntityId` остаётся независимым выбором.
Модель никогда не получает правила «найди первый projectile».

Если глобальная последовательность была item → bolt → item → bolt, она остаётся
такой же: непоследовательные группы не объединяются. Допустимы и несколько
последовательных групп одного target. Ограничение — не более 48 calls суммарно,
а не 48 calls в каждой из 48 групп. Shared params не вводятся: значения разных
вызовов не наследуются даже при численном совпадении.

Binding `equipped` содержит только `id` и `input`: action kind, item target и
fixed contact/stack следуют из закрытой ветви. `hold` сохраняет выбранный spawn
target. Активные primary/alternate bindings сохраняют action choice,
`stackCost` и `contactDamage`; placement дополнительно сохраняет точный
`placementCallId`, но fixed placement cost/contact не повторяются.

`plannedActionIndex` обязателен в каждой actionChecks row. Для `result="added"`
требуется явный `null`; при остальных result требуется integer в реальном
диапазоне concept rows. Resolver возвращает именно authored intent выбранной
строки. `implementedBehavior`, reason, result, intentionality и runtimeRefs
сохраняются. Он не пишет оценку исполнения вместо Author.

## Происхождение и отказ при подмене

`project_compact_author` возвращает canonical graph и source map. Каждый
canonical call path ссылается на исходный `callGroups[i].calls[j]`. Target
ссылается на исходный group target либо ID единственного item declaration.
Binding constants ссылаются на выбранный variant discriminator. Planned intent
ссылается одновременно на исходный индекс и конкретную concept row.

Обычные `finalWireReceipts` остаются привязаны к canonical graph. Дополнительные
`compactSourceReceipts` замыкают вторую цепочку к **исходному compact документу**,
который хранится в `compactAuthorSource.document`. Синтетический canonical
документ не выдаётся за первичный authored источник.

Strict wire gate при наличии любого из двух compact provenance claims требует
полный source record, заново вычисляет projection/map/цепочку, проверяет
canonical receipts относительно этого источника и сравнивает итоговые
name/category/concept/realization. Подмена исходного leaf, source path, receipt,
итогового gameplay или report отвергается. Без compact claims сохраняется
прежний wire-only audit.

Duplicate entity/call/binding IDs, отсутствующий либо второй item body,
неизвестные group keys, per-call target в полной grouped форме, лишний params
у zero-argument fn и неявное переключение version отвергаются. Корректный scalar
не превращает запрещённое поле в допустимое.

## Repair: ID сохраняется, валидное значение заморожено

Repair scope содержит digest полного исходного документа, исходные error paths,
точную source map и разрешения существующего frozen-first kernel. Изменённый
источник, расширенный caller-supplied scope или чужая map не принимаются.

Patch остаётся ID-addressed: `callsUpsert` содержит обычный stable `id`, `fn` и
params, а для projectile-capable fn ещё отдельный точный `target`. Item-only fn
не содержит target; zero-argument fn не содержит params. `bindingsUpsert` использует
flat compact variant. `realizationReplacement` содержит явные новые indices.

Например, исправление missing useStyle посылает разрешённый `callsUpsert` с
прежним call ID. Frozen kernel исправит именно этот leaf, а предложенное
одновременно изменение валидного autoReuse будет проигнорировано и отражено
в audit. Отсутствие поля в Repair означает no change, в том числе для новых
нейтральных axe/hammer/healMana leaves.

Если только один call группы имеет ошибочный target, разрешённый per-call
target edit разделяет группу около него. Валидные соседние calls не
перенаправляются; global order и прежние group boundaries сохраняются. Исправления
не создают неуказанные call IDs и не перенумеровывают прежние.

Out-of-range planned index остаётся явной repairable ошибкой. Scope хранит
оригинальное неправильное число; вместо него не подставляется row 0. Явная
`realizationReplacement` может выбрать правильную row из неизменённого concept.

Missing scalar/params leaf в проецируемой структуре проходит к прежнему
targeted kernel. Структура с неоднозначным item body, duplicate IDs или
неразрешимой группой отклоняется до построения scope: этот opt-in API не
притворяется, что умеет безопасно восстановить потерянную идентичность.
Отдельный syntax-only recovery pipeline здесь не добавлен. Caller получает
ошибку; скрытого redesign или попытки старой grammar нет.

## Измерение результата

Owner: `tools/measure_compact_author.py`. Восстановленный canonical документ и
`runtimeProgram/gameplay/accessory/armor` сравниваются точно. Единица — Unicode
characters в компактном JSON, не tokens, network bytes, provider usage или
средняя стоимость запроса. Указана совокупная D1–D6 notation; пересекающиеся
экономии отдельных приёмов не складываются.

| Fixture | Canonical JSON | Compact JSON | Сокращение | Strict provider JSON: до → после |
|---|---:|---:|---:|---:|
| workbench_blade | 5053 | 4788 | 265 | 5072 → 4807 |
| umbrella_grenade | 5789 | 5418 | 371 | 5807 → 5436 |
| door_on_chain | 3738 | 3548 | 190 | 3756 → 3566 |
| returning_potion | 3917 | 3710 | 207 | 3953 → 3746 |
| fishing_platform_tool | 3876 | 3648 | 228 | 3876 → 3648 |
| shield_and_disc | 5539 | 5224 | 315 | 5539 → 5224 |
| held_and_deployed | 6954 | 6487 | 467 | 6954 → 6487 |
| equipment_tool_combat | 5090 | 4690 | 400 | 5632 → 5232 |

D7 отдельно даёт 43 chars при omission нулевых axe/hammer и 13 chars при
omission healMana0 в canonical JSON. Strict provider требует nullable keys,
поэтому эти конкретные optional defaults сами по себе не обеспечивают такого
же уменьшения strict response.

Воспроизведение:

```bash
python tools/measure_compact_author.py --output contracts/compact_author_measurements.generated.json --check
python tools/export_contract_schemas.py --check
python -m pytest -q LocalGenerator/tests/test_compact_author_notation.py LocalGenerator/tests/test_registry_neutral_provenance.py
```

В тестах есть все public capability witnesses, восемь контрольных compositions,
malformed/duplicate/ref boundaries, точные receipts и source-path mutations,
frozen Repair, repeated intent identity, strict nullable roundtrips и
provider downgrade. Платный LLM quality experiment, first-pass validity/Repair
rate на реальных генерациях и native game smoke здесь **notRun**. Решение о
смене default pipeline требует отдельной оценки качества модели; эта версия
не объявляет measured JSON savings доказательством такого качества.
