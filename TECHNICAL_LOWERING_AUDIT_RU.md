# TECHNICAL LOWERING AUDIT

> Generated projection. Каноническая политика и owner routing находятся в `lowery.md`.

Schema: `infini.technical-lowering-manifest.v1`.

Lowering разрешён только как семантически без потерь технический перевод. Ни один lowerer не выбирает entity kind, movement, attachment, delivery, input, lifecycle, targeting или visual topology.

Authoring compression: только `exact_repetition`, минимум `5` literally equal placements, requiresLiteralEquality=`true`, mayAddDesignChoice=`false`. Mandatory wire projection уже authored identity не является compression.

## Global lowerers

| id | inputs | exact outputs | equivalence | preserves |
|---|---|---:|---|---|
| `entity_kind_to_visual_role` | runtimeProgram.entities[].kind | 1 | one canonical renderer role name for each explicitly authored entity kind | entity kind, entity identity, all gameplay components |
| `primary_entity_to_binding_role` | runtimeProgram.primaryEntityId, runtimeProgram.bindings[].target | 1 | primary exactly when the authored binding target equals the exact authored primary entity id; secondary otherwise | primary entity identity, binding identity, binding target, input, action |
| `primary_entity_kind_to_owner` | runtimeProgram.primaryEntityId, runtimeProgram.entities[].id, runtimeProgram.entities[].kind | 1 | wire owner family for the exact kind of the exact authored primary entity id | primary entity identity, entity kind |
| `capability_name_to_opcode` | runtimeProgram.calls[].fn | 3 | finite numeric wire opcode for the exact authored capability name | capability identity, target, params, event links |
| `item_fields_to_tml_projection` | item_body capability params | 96 | same authored semantic value copied into the exact DTO fields consumed by Terraria/tModLoader | all authored item values, explicit zero, units |

`item_fields_to_tml_projection` имеет конечный автоматически выведенный список output-path; broad `gameplay.*`/`accessory.*`/`armor.*` запрещены.

## Capability-level proof

Capability receipts содержат `callId`, `fn`, `finalPath`; global projection receipts содержат `lowererId`, `authoredPaths`, `finalPath`. `audit_compiler_receipts` принимает запись только когда authored inputs и final output объявлены соответствующим owner manifest. Mutation test добавляет недекларированный input/output и обязан получить отказ.

## Решение по старому lowering

Удалены family/root reducers и whole-weapon route tables. Извлечённые movement/controller/event helpers вызываются только по явно authored capability name. Никакой путь `family → held/thrust/straight/retract` не существует.
