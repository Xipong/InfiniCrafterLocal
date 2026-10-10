# Targeted Repair — leaf-local frozen-first protocol

[Generated boundary](../lowery.md) · [Author construction](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Stage accounting](THREE_STAGE_LLM_PIPELINE_RU.md#repairs-accounting)

Exact shape — `program_schema.py`; permissions/filter — `repair_scope.py`; requirement closure — `validator.py`; event alternatives — `capability_registry.py`; shared leaf merge — `core/repair_merge.py`. [Owner paths](../PROJECT_MAP_RU.md#python) не заменяются facade/shadow contracts.

<a id="context"></a>
## Досье Repair

Conditional Repair получает `path/code/allowed/relatedIds` validator errors, invalid fragments, exact missing dependencies, valid dependency context и компактный immutable index. Gameplay capability subset состоит из direct blockers, обязательных supporting capabilities и existing-broken calls. Полный valid item/stage response, planner/chat history и весь catalog в Gameplay Repair не отправляются; Repair не второй Author и не weapon-family router.

Canonical список ошибок ограниченного графа не обрезается для досье или failure envelope: поздняя ошибка должна попасть в тот же единственный Repair. Compiler-owned `author_repair_targets` сохраняют свой приоритет; downstream-only rejection не превращается в широкое разрешение менять Author. Это полнота diagnostics, не доказательство качества live-модели или достаточности её context window.

Author shape owner выводит конечный diagnostic ceiling из канонической schema, а не использует общий предел сбора 128. Отдельный итеративный guard ограничивает nodes/depth/text: сырой provider object проверяется до projection/copy, Author surface — до schema walk и построения Repair fragments. Превышение work bounds — явный отказ, не усечение входа, не частичный список с неполными правами и не новый Format/Gameplay Repair. Общий `strict_schema_errors` и его explicit `limit` для других consumers не изменены; preview текста исключения не ограничивает authoritative error list.

<a id="frozen-first"></a>
## Frozen-first merge

Уже принятые существующие значения **и принятое отсутствие** frozen. Возвращённый полный broken call/entity/binding/Visual row/VFX slot не открывает полный rewrite. Filter принимает лишь exact `fieldPermissions`, missing mandatory leaves, create-policy blocker/dependency nodes и policy-разрешённые удаления.

Scope escape (valid damage/target/kind, соседний call, motif/magnitude, необязательное unreported поле) игнорируется с сохранением прежнего значения и `ignoredChanges` audit; полезное exact исправление не отменяется. `old valid state + accepted leaves + allowed missing nodes = repaired state`. Пропуск в patch означает **не менять**, не материализовать default. Новые узлы подчиняются полному capability contract.

Индексы diagnostics, broken fragments и index-delete относятся к исходному массиву, включая malformed/ID-less строки. No-op не очищает их и не схлопывает duplicate occurrences; неоднозначный ID не открывает rewrite/delete всех совпадений. Удаление требует exact policy-разрешения на исходный индекс, валидный сосед остаётся frozen.

Невалидные числа, включая JSON integer вне float range, дают structured refusal по точной leaf, а не исключение преобразования. Нулевое healing-only `apply_item_effects` требует исправления healing leaves; тот же нейтральный вызов с другим активным разрешённым use-effect допустим. Runtime не выбирает недостающий эффект за модель.

Malformed provider/patch shape фатален: код не угадывает структуру. После tolerant filter всегда full stage validation; оставшаяся обязательная ошибка завершает единственный Repair неуспехом. Нет рекурсивного/бесконечного loop, hidden repair API или разрешения переносить авторство в compiler.

<a id="format"></a>
## Синтаксический Repair первоначального ответа

Для initial Gameplay/Visual JSON parse failure единственный conditional format pass видит исходный текст. Его output не новый design source. Scanner восстанавливает **только trailing commas вне JSON strings**; восстановленный целый объект сравнивается с Repair output после объявленной lossless projection / Visual normalization. Изменение valid damage или visualIdentity отклоняется. Невозможность восстановить целый объект и доказать сохранность — fail closed, не произвольный JSON5 и не дописывание missing design.

<a id="gameplay"></a>
## Gameplay scope и patch shape

`build_runtime_repair_scope()` выводит:

| Поле scope | Разрешение |
|---|---|
| `fieldPermissions`, `mutable`, `deletable` | Exact leaf paths, IDs broken nodes, policy-разрешённые IDs/indices удаления |
| `identityChanges` | Exact retarget/fn/input/action/event/reference changes |
| `create` | Bounded шаблоны доказанных missing entity/binding/call |
| `blockerPlan`, `capabilitySubset` | Direct/supporting/existing-broken closure и выданные cards |
| `nonRepairableErrors` | Registry/runtime defects: не маскируются LLM Repair |

Каждый `VALIDATION_ERROR_CODES` имеет явный `REPAIR_ERROR_POLICY`; добавление/удаление без parity краснит gate, фиксированное число в prose не контракт.

- `missing_movement_component`: только совместимые position drivers, замыкающие программу за один проход с frozen context; code не выбирает movement, честный выбор между вариантами принадлежит модели.
- `add_equipment_damage_bonus(phase=matching_armor_set)` + пустой `setKey`: открывается только `configure_armor.params.setKey`, не валидная bonus phase. Для body/legs policy может удалить ровно неисполняемый bonus call; перенос slot на head разрешён только явным scope, не автоматической миграцией.
- Missing `configure_item_use` не разрешает добавить light/projectile или изменить damage.
- `primaryEntitySelection` / `exclusiveInputSelections` — schema-owned repair transactions, не выбор primary/input кодом. Создание/retarget/deletion применяются только при выданных permissions.

Root patch разрежен: отсутствующие upsert/delete arrays и `metadataPatch` — no change. Каждый присутствующий upsert — полный типизированный node. `note` обязателен в local patch shape; model-facing Repair также требует полный non-null `realizationReplacement` как проверяемый report после merge. Nullable provider wrappers optional object properties кодируют omission только в фактически применённом `json_schema`; unknown keys, required non-null fields и null array elements не удаляются. В `json_object/off` явный null не такой эквивалент. [Transport/null rules](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract).

Порядок: provider envelope → local strict patch → exact deterministic scope → tolerant frozen merge/audit → full runtime validation → normal compile/receipts/final-wire gates. Сужение provider envelope не сужает local validation. Request-local calls grammar берётся из exact blocker/create scope; fn/whole-call edits сохраняют полный public union, пустой scope не расширяется. Nullable inverse использует ту же request-local schema. Syntax-only Repair не копирует повторный статический Author catalog; malformed text и equality с восстановимым исходником сохраняются. [Контракт и измерения](REPAIR_REQUEST_COMPACTION_RU.md).

<a id="visual"></a>
## Visual Repair

Input: invalid item/entity/animation fragments, accepted runtime entity context, parent facts и read-only valid-row index. Valid fields frozen; exact missing required visual fields доступны. Независимые rewrites игнорируются. Одна плохая leaf не разрешает удалить required entity row; malformed/duplicate technical rows удаляются только по policy. Missing required asset остаётся честным failure; placeholder не создаётся. Post-image failure не даёт дополнительного reauthor budget.

<a id="vfx"></a>
## VFX Repair

Input: exact invalid globals/slots, accepted visual kit и реальный `entityId + event` inventory. Valid globals/соседние slots frozen; entity/event retarget открывается только их ошибкой. Missing required slot leaves — exact scope; optional unreported design additions игнорируются. Invalid optional slot удаляется лишь при policy permission. Gameplay read-only; material/PNG dependencies — [VFX owner](VFX_MATERIAL_ELEMENTS_RU.md).

<a id="checks"></a>
## Проверяемые seams

Stage limit и happy path определены в [pipeline](THREE_STAGE_LLM_PIPELINE_RU.md#repairs-accounting), не копируются здесь. Regressions (`test_repair_*_contract.py`, `test_pipeline_repair_contract.py`, `test_low_level_three_stage_pipeline.py`) проверяют полезное исправление со scope escape, frozen absence/values, typed patch/nulls, exact dependency creation, minimal blocker cards, error-policy parity, registry-defect rejection, syntax-only preservation и finite transport stages `author_repair/visual_repair/vfx_repair`.

Offline audit: `PYTHONPATH=LocalGenerator python tools/audit_targeted_repair.py --check`; это projection/contract proof, не новая live/game/MP acceptance.
