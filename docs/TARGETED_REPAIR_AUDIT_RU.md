# Targeted Repair Audit — InfiniCrafterLocal v0.4.241

## Итог

Новый low-level runtime использует conditional **leaf-local frozen Repair**. Repair не переавторивает весь предмет, не возвращается к weapon-family routing и не отменяется из-за попытки модели переписать корректные старые значения.

Модель получает только точные ошибки, сломанные fragments, локальный read-only dependency context и минимальный blocker catalog. После ответа deterministic filter сохраняет старые валидные значения, применяет точные исправления и игнорирует лишние изменения с audit.

## Машинные гарантии

- 33 semantic validator error codes;
- 33/33 явных `REPAIR_ERROR_POLICY`;
- новый semantic error без policy краснит tests;
- `shape_*` обрабатываются strict provider/schema boundary;
- `runtime_repair_scope_schema()` имеет `additionalProperties: false` и обязательные `repairStrategy`/`llmRepairable`;
- exact `fieldPermissions` для существующих узлов;
- exact create/retarget/delete policy;
- blocker alternatives фильтруются по target kind, frozen dependency values и возможности закрыть ошибку за один Repair;
- model-facing `requiredOneOfCapabilities` совпадает с реально выданными capability cards;
- полный stage validator запускается после frozen merge;
- один conditional Repair на стадию, без repair-loop;
- registry/runtime defects не отправляются LLM.

## Контекст модели

Gameplay Repair handoff `infini.gameplay-repair-dossier.v1` содержит:

- exact validation errors;
- `readOnlySourceFragments`: broken fragments, malformed rows по index и valid dependency fragments из blocker graph — это входные данные, не поля ответа;
- output shape card — последнее поле `requiredJsonShape` того же JSON user-сообщения (system→user сохраняется): только перечисленные внутри него корневые patch-поля допустимы в ответе;
- immutable ID/kind/function index без полных параметров независимых узлов;
- direct blocker capability cards;
- обязательные supporting capability cards;
- existing broken capability cards;
- parent facts и accepted item concept metadata.

Он не содержит полный старый `runtimeProgram`, прошлую chat history или весь каталог из all capabilities.

## Измерение prompt locality

Machine audit: `tools/audit_targeted_repair.py` и `contracts/targeted_repair_audit.generated.json`.

| Сценарий | Repair dossier | Capability cards | Что получает модель |
|---|---:|---:|---|
| Missing обязательного `useStyle` | 18 884 символа | 1 | сломанный `configure_item_use`, exact missing leaf |
| Полностью отсутствует `configure_item_use` | 18 697 | 1 | ровно `configure_item_use` как создаваемый blocker |
| Нет position driver | 30 080 | 20 | только одношаговые совместимые movement alternatives |
| `channel_beam`, но `channel=false` | 20 787 | 2 | beam как read-only/broken context и `configure_item_use.channel=true` как blocker |

Для сравнения полный Gameplay Author payload в том же audit — **80 260 символов** и all capabilities.

В movement-case исключены `channel_beam` и `charge_then_release`: первый требует изменить отдельное frozen channel-состояние, второй сам не является завершённым position driver без дополнительной movement capability. Deterministic код не выбирает один из оставшихся 20 вариантов за модель.

## Merge semantics

При ответе модели:

1. strict patch shape проверяется;
2. точные разрешённые leaves/nodes фильтруются;
3. старые корректные значения сохраняются;
4. exact broken/missing поля и allowed blocker nodes применяются;
5. frozen rewrites и optional unreported additions записываются в `ignoredChanges`;
6. собранный полный output заново валидируется.

Следовательно, ответ «добавить missing `useStyle`, но заодно изменить damage» даёт готовый предмет с новым `useStyle` и прежним damage. Полезная дочинка не теряется из-за scope escape.

## Visual и VFX

Visual Repair получает broken item/entity/animation fragments, валидные Visual rows как read-only context, parent facts и accepted runtime entity card. VFX Repair получает broken globals/slots, валидные slots, accepted visual kit и точный `entityId + event` surface.

Во всех трёх стадиях:

- valid old fields frozen;
- exact missing required fields принимаются;
- independent rewrites игнорируются;
- после merge выполняется полный stage validator;
- предыдущие валидные стадии не перезапускаются.

## Проверка

- targeted three-stage/Repair suite: `python -m pytest LocalGenerator/tests/test_low_level_three_stage_pipeline.py -q`;
- полный Python suite: `python -m pytest LocalGenerator/tests toolbox/tests -q`;
- machine blocker audit: `python tools/audit_targeted_repair.py --check`;
- generated Repair scope schema: current;
- stage accounting happy path: `1/0/1/0/1/0`.

## Ограничения

- Malformed patch JSON/provider schema не восстанавливается deterministic догадками.
- Если единственный Repair не исправил обязательный blocker, stage честно падает.
- При нескольких семантически разных честных low-level alternatives окончательный выбор остаётся за моделью.
- C#/tModLoader runtime после Gameplay Repair всё равно проходит обычные compile/wire/runtime gates; Repair не обходит их.
