# TECHNICAL LOWERING AUDIT

> Generated: [`tools/generate_low_level_runtime_docs.py`](tools/generate_low_level_runtime_docs.py) из [technical_lowering.py](LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py). Не редактировать вручную; [refresh/check всех трёх outputs](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md#refresh).
> Policy/owners: [Lowery](lowery.md). Полные wire outputs каждого lowerer: [manifest](lowery.md#lowering).

Schema: `infini.technical-lowering-manifest.v1`.

Lowering разрешён только как семантически без потерь технический перевод. Ни один lowerer не выбирает entity kind, movement, attachment, delivery, input, lifecycle, targeting или visual topology.

Authoring compression: только `exact_repetition`, минимум `5` literally equal placements, requiresLiteralEquality=`true`, mayAddDesignChoice=`false`. Mandatory wire projection уже authored identity не является compression.

**Навигация:** [lowerers](#lowerers) · [receipts/proof](#receipts) · [удалённый lowering](#retired).

<a id="lowerers"></a>

## Global lowerers

| id | inputs | exact outputs | equivalence | preserves |
|---|---|---:|---|---|
| `entity_kind_to_visual_role` | runtimeProgram.entities[].kind | 2 | one canonical renderer role name for each explicitly authored entity kind | entity kind, entity identity, all gameplay components |
| `primary_entity_to_binding_role` | runtimeProgram.primaryEntityId, runtimeProgram.bindings[].usePolicy.action.targetId | 1 | primary exactly when the authored binding target equals the exact authored primary entity id; secondary otherwise | primary entity identity, binding identity, binding target, input, action |
| `primary_entity_kind_to_owner` | runtimeProgram.primaryEntityId, runtimeProgram.entities[].id, runtimeProgram.entities[].kind | 1 | wire owner family for the exact kind of the exact authored primary entity id | primary entity identity, entity kind |
| `capability_name_to_opcode` | runtimeProgram.calls[].fn | 3 | finite numeric wire opcode for the exact authored capability name | capability identity, target, params, event links |
| `item_fields_to_tml_projection` | item_body capability params | 142 | same authored semantic value copied into the exact DTO fields consumed by Terraria/tModLoader | all authored item values, explicit zero, units |

`item_fields_to_tml_projection` имеет конечный автоматически выведенный список output-path; broad `gameplay.*`/`accessory.*`/`armor.*` запрещены.

<a id="receipts"></a>

## Capability-level proof

- **Receipt shape.** Capability receipts содержат `callId`, `fn`, `authoredPath`, `finalPath`; class-damage selector дополнительно привязывает `phase`, `damageClass` и `bonusPercent` через `authoredPaths`. Global projection receipts содержат `lowererId`, `authoredPaths`, `finalPath`.
- **Exact delivery.** `audit_compiler_receipts` требует receipt для каждого authored параметра и сверяет заявленный output с фактическим final wire. Для equipment и item stats проверяется точная пара вход→выход из registry, включая случай двух равных значений; простой whitelist путей не доказывал эту связь. Delivery wire без `runtimeContract` проверяется отдельно, но не заявляет provenance. Mutation tests должны отклонять подмену пути, значения и пропуск receipt.
- **Declared omission.** Для optional params с явно объявленным default=neutral статус `declared_neutral_omission` отдельно фиксирует материализацию отсутствия в полном Author. Это не `delivered` присутствующего authored значения. Audit проверяет registry default, точный wire path/value, отсутствие параметра в исходном документе (если документ доступен) и полноту receipts. Старые корректные явные значения не меняются.

<a id="retired"></a>

## Решение по старому lowering

Удалены family/root reducers и whole-weapon route tables. Извлечённые movement/controller/event helpers вызываются только по явно authored capability name. Никакой путь `family → held/thrust/straight/retract` не существует.
