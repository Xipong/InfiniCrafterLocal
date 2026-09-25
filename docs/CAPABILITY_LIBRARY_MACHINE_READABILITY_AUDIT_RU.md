# Аудит машиночитаемости библиотеки компонентов

> Генерируется `python tools/generate_low_level_runtime_docs.py` из live registry и audit-кода.
> Каноническая архитектурная граница и owner routing: `lowery.md`; этот файл только измеряет projection.

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

## Измеренные свойства

- capabilities: **52**; parameters: **229**; numeric: **180/180 bounded**;
- entity kinds: **7**; inputs: **4**; actions: **5**; events: **10**;
- typed entity references: **2**; requirements: **27**; binding dependency edges: **8**;
- exact wire paths: **312**; global technical lowerer outputs: **149**;
- Python↔C# range parity rows: **85**; vertical witnesses: **52**;
- errors: **0**; warnings: **0**.

## Почему библиотека действительно машиночитаема

1. `CAPABILITY_REGISTRY` — единый явный immutable registry; schema, prompt cards, manifest и compiler dispatch выводятся из него.
2. Каждый parameter объявляет JSON type, semantic type, description, enum/range/units; entity references имеют namespace и допустимые target kinds.
3. Entity kinds, inputs, binding actions и events имеют отдельные registries, а validator использует их, а не дублирующий набор `if`-маршрутов.
4. Capability указывает component slot, exclusivity, position ownership, requirements, emitted/accepted events и authority.
5. Delivery перечисляет точные wire-path; wildcard-output запрещён audit-gate.
6. Owner — не просто имя файла: audit импортирует Python callable и ищет конкретные C# method symbols.
7. Для каждой capability исполняется author→validate→compile→strict-wire witness; неизвестные поля/refs/opcodes fail closed.

## Честные ограничения

- На entity допускается один movement slot и один controller slot. Это намеренная bounded-композиция, не arbitrary ECS/VM.
- Cross-entity references доступны только там, где runtime реально их исполняет (`target_and_fire`, event child spawn).
- Authority metadata проверяется статическими контрактами, но реальный host/client smoke требует tModLoader runtime.
- Статический vertical witness доказывает доставку Python→C# contract surface, но не заменяет успешный C# build и игровой smoke.
- Prompt catalog крупный, но self-contained: около 71k символов на обычных parents и до 83k на rich generated-parent fixture при hard limit 96k; retrieval/tool loop не используется.
- Каталог покрывает реализованные 52 primitive/controller/effect, а не всю потенциальную семантику Terraria/mod ecosystem.

## Практическая оценка

- **Структура и проверяемость: 10/10** — все объявленные проекции замкнуты и проверяются машиной.
- **Однозначность для LLM: 9/10** — API не содержит weapon families и semantic defaults; некоторые item-body calls длинные из-за широких typed DTO.
- **Выразительность текущего runtime: 8/10** — странные multi-entity композиции поддерживаются, но controller layering и произвольная world interaction намеренно ограничены.
- **Доказанность в игре: неполная** до C# build/tModLoader singleplayer/host-client smoke.
