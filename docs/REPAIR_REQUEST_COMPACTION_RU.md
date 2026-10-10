# Scoped grammar и syntax-only context Gameplay Repair

## Что меняется

Gameplay Repair уже получал exact scope, frozen source и несколько blocker cards,
но provider schema всегда включала все capabilities. Format Repair дополнительно
копировал полный original Author prompt с каталогом и общими инструкциями.

Теперь schema `callsUpsert` — request-local projection **того же** canonical
`program_schema.author_item_repair_schema`. Выбор registry variants задаёт
`repair_scope.runtime_repair_schema_capabilities`:

- параметрический scope включает exact capabilitySubset, direct/support/existing
  blocker names и разрешённые create.calls.allowedFns;
- когда разрешено менять fn или целый call, сохраняется полный public union.
  Старый capabilitySubset описывает карточки blockers и сам по себе не является
  полной allowlist для таких replacements;
- explicit empty scope разрешает только пустой callsUpsert; он никогда не
  означает «все capabilities»;
- неизвестные/non-public names отказывают явно вместо выбора замены.

Params берутся целиком из canonical capability variants. Нет параллельных
таблиц их полей, scalar-only предположений или выбора event producer кодом.
Allowed event alternatives/supporting/create choices сохраняются. Grammar
visibility не выдаёт новых permissions; допустимость patch по-прежнему решают
frozen-first filter и полный post-merge validator.

Nullable inverse получает **ту же request-local local schema**, из которой был
сделан outgoing provider envelope. Иначе required nullable wrappers узкого
callsUpsert не совпали бы с глобальной schema и null scaffolding достиг бы
валидатора. Singleton union проверяет literal fn и не выбирает ветвь по одному
object type. При json_object/off null остаётся authored value.

## Format Repair

Из `originalRecipeContext` удаляется только копия шести `_AUTHOR_CACHE_PREFIX_KEYS`:
priorityHeader, gameplayAuthoringStages, runtimeProgramInvariants,
runtimeCapabilityContract, requiredJsonShape, diagnosticReport.

Точный malformedRawText, parse error, собственные syntax-only rules,
allowedCallParamsReadOnly, full output shape, recipeKey, parents, balance и все
прочие dynamic recipe fields сохраняются. Это не allowlist, теряющая будущие
parent facts. Equality с синтаксически восстановимым исходным Author object
продолжает отвергать любое добавление, удаление или изменение gameplay.

Классификация — **Normalization request representation** по существующему
контракту, без gameplay/compiler transformation. Request-local schema — его
ограниченная grammar projection, не новый Author API и не Repair permissions.
Compiler receipts и C# wire/execution не изменяются.

## Измерение production requests

База `62762da` имеет тот же исполняемый код, что `ff039fc`. Offline-скрипт использует
настоящие builders, Chat/Responses/Codex adapters и production JSON serializer;
все сетевые и LLM calls блокируются. Parent/craft данные — synthetic fixtures.
Default style, фиксированный model route label gpt-6.1, max tokens 9000.

| Запрос | User до → после | Provider schema до → после | Полный Chat HTTP до → после |
|---|---:|---:|---:|
| Missing configure_item_use.useStyle, json_schema | 35 622 → 35 622 | 140 705 → 19 950 | 192 873 → 64 548 |
| Syntax-only repair, json_object | 134 428 → 17 296 | отсутствует | 147 167 → 20 643 |
| Syntax-only repair, json_schema | 134 428 → 17 296 | 138 811 → 138 811 | 295 648 → 169 124 |

Initial Author request в этом независимом PR не изменяется. Общая очистка
provider annotations и Author context вынесены в отдельную категорию; savings
двух PR нужно измерять вместе, не складывать независимо полученные проценты.
Частота Repair, billed tokens, latency и model quality не измерены.

```bash
PYTHONPATH=LocalGenerator python tools/measure_llm_request_sizes.py --out request-sizes.json
PYTHONPATH=LocalGenerator python tools/measure_llm_request_sizes.py --repo /path/to/base-checkout --out base-request-sizes.json
```

## Проверки и hostile responses

`test_repair_request_compaction.py` проверяет real request → nullable inverse →
frozen merge с сохранением accepted omission, create/event support, пустой scope,
полный fn/whole-call scope, неизвестные names и отказ Format Repair при изменении
damage. Существующий corpus продолжает проверять single Repair budget,
синтаксическое восстановление и невозможность заполнить отсутствующий дизайн.

Strict provider grammar теперь отвергает out-of-scope fn ещё на decoding.
Отдельные negative tests намеренно возвращают такой ответ вопреки envelope:
полезный разрешённый leaf сохраняется, посторонние корректно типизированные
правки frozen nodes игнорируются с audit. Это не утверждение, что hostile ответ
schema-valid; malformed types/unknown shapes сохраняют прежний отказ.

Полный offline suite: **7108 passed**. Все 11 portable gates из `AGENTS.md`
пройдены, включая generated docs parity, frozen Repair audit и dependency-free
sandbox validation.

Native build/game/MP и live LLM quality comparison: **notRun**. Эти размеры не
доказывают качество синтаксического восстановления или игровые lifecycle.
