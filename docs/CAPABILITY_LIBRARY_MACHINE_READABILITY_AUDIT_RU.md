# Аудит машиночитаемости библиотеки компонентов

> Generated: [`tools/generate_low_level_runtime_docs.py`](../tools/generate_low_level_runtime_docs.py) из [registry](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) и [audit-кода](../LocalGenerator/infini_local/qa/capability_library_audit.py). Не редактировать вручную; [refresh/check всех трёх outputs](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md#refresh).
> Architecture/owners: [Lowery](../lowery.md). Полный каталог: [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md).

**Навигация:** [вердикт/критерии](#verdict) · [измерения](#metrics) · [проверяемость](#proof) · [ограничения](#limits) · [практическая оценка](#assessment).

<a id="verdict"></a>

## Вердикт: 100/100

Это **структурная оценка контракта**, а не заявление, что реализован весь Terraria runtime.

| критерий | вес | результат |
|---|---:|---:|
| `registryIdentity` | 10 | PASS |
| `typedParameters` | 15 | PASS |
| `compositionMetadata` | 15 | PASS |
| `exactDelivery` | 15 | PASS |
| `runtimeOwnership` | 15 | PASS |
| `rangeParity` | 10 | PASS |
| `projectionParity` | 10 | PASS |
| `verticalSlices` | 10 | PASS |

<a id="metrics"></a>

## Измеренные свойства

- capabilities: **58**; parameters: **260**; numeric: **195/195 bounded**;
- entity kinds: **7**; inputs: **4**; actions: **5**; events: **10**;
- typed entity references: **2**; requirements: **31**; binding dependency edges: **8**;
- exact wire paths: **362**; global technical lowerer outputs: **150**;
- Python↔C# range parity rows: **92**; vertical witnesses: **58**;
- errors: **0**; warnings: **0**.

<a id="proof"></a>

## Почему библиотека действительно машиночитаема

1. `CAPABILITY_REGISTRY` — единый явный immutable registry; schema, prompt cards, manifest и compiler dispatch выводятся из него.
2. Каждый parameter объявляет JSON type, semantic type, description, enum/range/units; entity references имеют namespace и допустимые target kinds.
3. Entity kinds, inputs, binding actions и events имеют отдельные registries, а validator использует их, а не дублирующий набор `if`-маршрутов.
4. Capability указывает component slot, exclusivity, position ownership, requirements, emitted/accepted events и authority.
5. Delivery перечисляет точные wire-path; wildcard-output запрещён audit-gate.
6. Owner — не просто имя файла: audit импортирует Python callable и ищет конкретные C# method symbols.
7. Для каждой capability исполняется author→validate→compile→strict-wire witness; неизвестные поля/refs/opcodes fail closed.

<a id="limits"></a>

## Честные ограничения

- На entity допускается один movement slot и один controller slot. Это намеренная bounded-композиция, не arbitrary ECS/VM.
- Cross-entity references доступны только там, где runtime реально их исполняет (`target_and_fire`, event child spawn).
- Authority metadata проверяется статическими контрактами, но реальный host/client smoke требует tModLoader runtime.
- Статический vertical witness доказывает доставку Python→C# contract surface, но не заменяет успешный C# build и игровой smoke.
- Author получает self-contained catalog без retrieval/tool loop. Исторические оценки около 71k/83k символов при лимите 96k из прежнего аудита не являются текущими размерами или верхней границей. Текущий размер **компактного полного Author user payload** (без system text/provider envelope/schema), configured limit и headroom измеряет [`tools/check_planner_prompt_usability.py`](../tools/check_planner_prompt_usability.py); catalog-only size — другая величина.
- Каталог покрывает реализованные 58 primitive/controller/effect, а не всю потенциальную семантику Terraria/mod ecosystem.

<a id="assessment"></a>

## Практическая оценка

- **Структура и проверяемость: 10/10** — все объявленные проекции замкнуты и проверяются машиной.
- **Однозначность для LLM: 9/10** — API не содержит weapon families и semantic defaults; некоторые item-body calls длинные из-за широких typed DTO.
- **Выразительность текущего runtime: 8/10** — странные multi-entity композиции поддерживаются, но controller layering и произвольная world interaction намеренно ограничены.
- **Доказанность в игре: неполная** до C# build/tModLoader singleplayer/host-client smoke.
