# Scoped grammar и syntax-only context Gameplay Repair

## Текущая граница

Schema `callsUpsert` — request-local projection **того же** canonical
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

Из `originalRecipeContext` удаляется только копия пяти `_AUTHOR_CACHE_PREFIX_KEYS`:
priorityHeader, runtimeProgramInvariants,
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

## Offline capture production requests

```bash
PYTHONPATH=LocalGenerator python tools/measure_llm_request_sizes.py --out request-sizes.json
```

Скрипт использует реальные builders/adapters/serializers и блокирует network/LLM calls. Родители — synthetic fixtures; measured JSON bytes/chars не являются billed tokens, latency или model quality. Сравнение baseline допускается отдельным `--repo /path/to/base-checkout`, не через восстановление старого контракта в production.

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

Актуальные команды и границы proof — [TESTING](TESTING_RU.md). Offline request/merge checks не доказывают live LLM quality, native game-loop/GPU или MP match.
