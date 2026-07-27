# Targeted Repair Protocol — InfiniCrafterLocal v0.4.241

> Это protocol projection, а не второй owner. Каноническая граница и edit-routing: [`../lowery.md`](../lowery.md). Exact repair shape принадлежит `program_schema.py`; permissions/filter — `repair_scope.py`; requirement closure — `validator.py`; event alternatives — `capability_registry.py`.

## Цель

Conditional Repair не переавторивает предмет и не возвращается к weapon-family архитектуре. Он получает только:

1. точные `path + code + allowed + relatedIds` ошибки deterministic validator;
2. сломанные fragments, к которым относятся эти ошибки;
3. уже валидные dependency fragments и компактный immutable index для контекста;
4. exact create/retarget/delete permissions, выведенные из ошибок;
5. минимальный blocker capability subset: direct blockers, обязательные supporting capabilities и уже существующие сломанные capabilities.

Полный предыдущий Gameplay response, прежняя chat history и весь capability catalog в Gameplay Repair не отправляются.

## Frozen-first merge

Источник истины — уже принятый stage output. Все существующие корректные значения **заморожены**.

Модель может для удобства вернуть полный объект сломанного call/entity/binding/claim, Visual-row или VFX-slot. Deterministic filter применяет только:

- exact leaf paths из `fieldPermissions`;
- exact missing mandatory fields, указанные validator/schema;
- новые blocker/dependency nodes, явно разрешённые `create` policy;
- удаления только для ошибок, чья machine-readable policy допускает удаление узла.

Попытки модели изменить валидный damage, target, entity kind, соседний call, Visual motif, VFX magnitude либо добавить необязательное поле вне scope **не отменяют полезный Repair**. Они игнорируются, старые значения сохраняются, а попытка записывается в `ignoredChanges` audit.

Итоговая семантика:

```text
old valid values
+ exact accepted repair leaves
+ exact allowed missing blocker/dependency nodes
= repaired stage output
```

Malformed provider/patch shape остаётся фатальным: deterministic code не угадывает структуру ответа. После tolerant filter всегда запускается полная валидация stage output. Если обязательная ошибка не исправлена, один условный Repair считается неуспешным; бесконечного Repair-loop нет.

## Gameplay Repair

`build_runtime_repair_scope()` строит:

- `fieldPermissions` — точные mutable leaf paths;
- `mutable` — IDs существующих сломанных узлов;
- `deletable` — только policy-разрешённые IDs/indices;
- `identityChanges` — точные разрешения на retarget/fn/input/action/event/reference;
- `create` — ограниченный шаблон нового missing entity/binding/call;
- `blockerPlan` — direct/supporting/existing-broken capabilities;
- `capabilitySubset` — только эти capabilities;
- `nonRepairableErrors` — внутренние registry/runtime defects, которые нельзя скрывать LLM-ремонтом.

Все machine validator codes из `VALIDATION_ERROR_CODES` обязаны иметь явную запись в `REPAIR_ERROR_POLICY`. Число не дублируется в prose: добавление/удаление кода без parity краснит тесты.

Особый случай `missing_movement_component`: deterministic code не выбирает movement за модель. Repair получает только совместимые position drivers, которые могут замкнуть программу за один проход с frozen context. Несовместимые варианты отфильтровываются; если остаётся несколько честных вариантов, выбор делает модель.

Новый call разрешён только при доказанном blocker/dependency. Например, отсутствие `configure_item_use` не открывает создание света, нового projectile или переписывание damage.

Порядок:

```text
provider strict schema
→ local strict patch shape
→ build exact deterministic scope
→ tolerant frozen merge
→ scope/filter audit
→ full runtimeProgram validation
→ normal compile/final-wire gates
```

## Visual Repair

Visual Repair получает только невалидный item/entity/animation fragment, accepted runtime entity context, parent facts и read-only index валидных rows.

- существующие валидные поля frozen;
- exact missing required visual fields разрешены;
- независимые entity rewrites игнорируются;
- удаление целой required runtime-entity row не разрешается из-за одного плохого поля;
- malformed/duplicate technical rows могут быть удалены по policy;
- отсутствующий обязательный PNG остаётся честным failure/Repair, placeholder не создаётся.

## VFX Repair

VFX Repair получает exact invalid global fields/slots, accepted visual kit и реальный `entityId + event` inventory.

- валидные global fields и соседние slots frozen;
- retarget разрешён только когда ошибка относится к `entityId/event`;
- missing required slot fields разрешены exact leaf paths;
- optional unreported VFX design additions игнорируются;
- invalid optional VFX slot можно удалить, если scope это допускает.

## Stage topology

Happy path остаётся:

```text
1 Gameplay Author
1 Visual Director
1 VFX Director
0 Repairs
```

Каждая стадия имеет не более одного conditional Repair. Repair одной стадии не перезапускает уже валидные предыдущие стадии.

## Проверки

`test_low_level_three_stage_pipeline.py` проверяет:

- baseline `1/0/1/0/1/0`;
- conditional Gameplay/Visual/VFX Repair;
- frozen valid values при одновременном полезном исправлении;
- игнорирование scope escape вместо отмены Repair;
- запрет необязательных unreported additions;
- exact missing dependency creation/repair;
- minimal blocker capability subset и совпадение model-facing requirement с реально выданными cards;
- отсутствие полного valid-node payload в prompt;
- 33/33 validator-code → Repair-policy parity;
- запрет LLM Repair для registry/runtime defect;
- доступность finite transport stages `author_repair`, `visual_repair`, `vfx_repair`.
