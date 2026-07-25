# TECHNICAL LOWERING AUDIT

Schema: `infini.technical-lowering-manifest.v1`.

Lowering разрешён только как семантически без потерь технический перевод. Ни один lowerer не выбирает entity kind, movement, attachment, delivery, input, lifecycle, targeting или visual topology.

## Global lowerers

| id | inputs | exact outputs | equivalence | preserves |
|---|---|---:|---|---|
| `entity_kind_to_visual_role` | runtimeProgram.entities[].kind | 1 | one canonical renderer role name for each explicitly authored entity kind | entity kind, entity identity, all gameplay components |
| `capability_name_to_opcode` | runtimeProgram.calls[].fn | 3 | finite numeric wire opcode for the exact authored capability name | capability identity, target, params, event links |
| `item_fields_to_tml_projection` | item_body capability params | 96 | same authored semantic value copied into the exact DTO fields consumed by Terraria/tModLoader | all authored item values, explicit zero, units |

`item_fields_to_tml_projection` имеет конечный автоматически выведенный список output-path; broad `gameplay.*`/`accessory.*`/`armor.*` запрещены.

## Capability-level proof

Каждая compiler receipt содержит `callId`, `fn`, `finalPath`. `audit_compiler_receipts` принимает запись только когда `finalPath` объявлен в exact outputs соответствующей capability. Mutation test добавляет недекларированный output и обязан получить отказ.

## Решение по старому lowering

Удалены family/root reducers и whole-weapon route tables. Извлечённые movement/controller/event helpers вызываются только по явно authored capability name. Никакой путь `family → held/thrust/straight/retract` не существует.
