# Аудит машиночитаемости библиотеки компонентов

> Generated: [`tools/generate/generate_low_level_runtime_docs.py`](../../../tools/generate/generate_low_level_runtime_docs.py) из [registry](../../../generator/infini_local/core/runtime_authoring/capability_registry.py) и [audit-кода](../../../generator/infini_local/qa/capability_library_audit.py). Не редактировать вручную; [refresh/check всех трёх outputs](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md#refresh).
> Architecture/owners: [Lowery](LOWERY_RU.md). Полный каталог: [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md).

**Навигация:** [вердикт/критерии](#verdict) · [измерения](#metrics) · [проверяемость](#proof) · [ограничения](#limits) · [практическая оценка](#assessment).

<a id="verdict"></a>

## Registry metadata и Python wire witnesses

Проверяются declarations и исполнение Author→validator→compiler→wire в Python. C# execution/range preservation здесь **не проверены**; owner names — навигационные metadata.

| критерий | результат |
|---|---:|
| `registryIdentity` | PASS |
| `typedParameters` | PASS |
| `compositionMetadata` | PASS |
| `exactDelivery` | PASS |
| `declaredOwnership` | PASS |
| `projectionParity` | PASS |
| `verticalSlices` | PASS |

<a id="metrics"></a>

## Измеренные свойства

- capabilities: **74**; parameters: **395**; numeric: **232/232 bounded**;
- entity kinds: **7**; inputs: **4**; actions: **6**; events: **12**;
- typed entity references: **4**; requirements: **102**; binding dependency edges: **9**;
- exact wire paths: **660**; global technical lowerer outputs: **237**;
- Python vertical witnesses: **71**; native execution: **notRun**;
- errors: **0**; warnings: **0**.

<a id="proof"></a>

## Почему библиотека действительно машиночитаема

1. `CAPABILITY_REGISTRY` — единый явный immutable registry; schema, prompt cards, manifest и compiler dispatch выводятся из него.
2. Каждый parameter объявляет JSON type, semantic type, description, enum/range/units; entity references имеют namespace и допустимые target kinds.
3. Entity kinds, inputs, binding actions и events имеют отдельные registries, а validator использует их, а не дублирующий набор `if`-маршрутов.
4. Capability указывает component slot, exclusivity, position ownership, requirements, emitted/accepted events и authority.
5. Delivery перечисляет точные wire-path; wildcard-output запрещён audit-gate.
6. Audit разрешает Python compiler callable; C# owner указан для навигации, без проверки method spelling.
7. Для каждой capability исполняется author→validate→compile→strict-wire witness; неизвестные поля/refs/opcodes fail closed.

<a id="limits"></a>

## Честные ограничения

- На entity допускается один movement slot и один controller slot. Это намеренная bounded-композиция, не arbitrary ECS/VM.
- Cross-entity references доступны только там, где runtime реально их исполняет (`target_and_fire`, event child spawn).
- Authority metadata проверяется статическими контрактами, но реальный host/client smoke требует tModLoader runtime.
- Исполняемый Python witness проверяет validator/compiler/strict-wire, но не C# consumer, игровой smoke или native bounds.
- Author получает self-contained catalog без retrieval/tool loop. Исторические оценки около 71k/83k символов при лимите 96k из прежнего аудита не являются текущими размерами или верхней границей. Текущий размер **компактного полного Author user payload** (без system text/provider envelope/schema), configured limit и headroom измеряет [`tools/checks/check_planner_prompt_usability.py`](../../../tools/checks/check_planner_prompt_usability.py); catalog-only size — другая величина.
- Публичный каталог покрывает реализованные 74 primitive/controller/effect, а не всю потенциальную семантику Terraria/mod ecosystem.

<a id="assessment"></a>

## Практическая оценка

- **Доказанность в игре: неполная** до C# build/tModLoader singleplayer/host-client smoke.
