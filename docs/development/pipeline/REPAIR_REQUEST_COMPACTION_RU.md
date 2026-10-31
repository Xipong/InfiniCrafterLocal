# Scoped grammar и syntax-only context Repair

## Текущая граница

Schema `callsUpsert` — request-local projection **того же** canonical
`program_schema.author_item_repair_schema`. Выбор registry variants задаёт
`repair.fragments.runtime_repair_schema_capabilities`:

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

## Visual/VFX Repair

Request-local grammar берётся из exact `repairScope.fieldPermissions` и
create/delete permissions, а не из имени, prose или одного особого error leaf.
Initial Director schemas/public exports и полная post-merge admission не меняются.

- Visual передаёт только разрешённые owner operations, selectors и nested leaves.
  Sparse patch дополняется исключительно уже authored source siblings перед
  прежним frozen-first filter; отсутствующий дизайн не придумывается. Для size-only
  Repair остаются calibration, accepted mechanics и parent PNG/visual references,
  но не повторный полный parent/design dossier. Art edits сохраняют art context.
- VFX сохраняет canonical grammar editable leaves, точные frozen companions и
  раздельные row-ID branches. Не разрешённые delete/upsert operations не
  рекламируются. Renderer/entity/event discriminator и create/whole-response
  scopes сохраняют полный необходимый domain; unrelated renderer/material/sound
  grammar и vocabulary не отправляются для независимого scalar Repair.
- Case-specific constants и IDs остаются USER. Static grammar extraction не
  обязана существовать для каждого scoped packet: неизменная полная schema
  ради cache hit не нужна. Provider schema остаётся inline/self-contained.

## Format Repair

Gameplay Format Repair получает точный `malformedRawText`, parse error,
краткий индекс корневых ключей и допустимые params только тех exact `fn`, которые
однозначно восстанавливаются из источника. Из canonical Author schema выбираются
эти же call variants; новый набор params или второй Author API не создаётся.
Неизвестные/повреждённые identities сохраняют полный grammar domain и прежний
fail-closed, а не угадываются по prose. Nullable inverse читает именно отправленную
local schema. Первоначальный Author packet и Gameplay semantic Repair не меняются.

Родители, balance, повторный concept/design guide и остальные поля
`originalRecipeContext` модели не отправляются: единственный источник дизайна —
исходный ответ. `recipeKey` остаётся у trace owner, не теряется вместе с dossier.
Equality с синтаксически восстановимым исходным Author object продолжает отвергать
любое добавление, удаление или изменение gameplay; невозможность доказать источник
остаётся отказом. Никакие values, strings или массивы source не обрезаются.

Классификация — **Normalization request representation** по существующему
контракту, без gameplay/compiler transformation. Request-local schema — его
ограниченная grammar projection, не новый Author API и не Repair permissions.
Compiler receipts и C# wire/execution не изменяются.

## Offline capture production requests

```bash
PYTHONPATH=LocalGenerator python tools/diagnostics/measure_llm_request_sizes.py --out request-sizes.json
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

Актуальные команды и границы proof — [TESTING](../TESTING_RU.md). Offline request/merge checks не доказывают live LLM quality, native game-loop/GPU или MP match.
