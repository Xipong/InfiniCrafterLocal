# ToDo: Applied vs Authored Validator

Очень позже, но обязательно: сделать отдельный валидатор, который сравнивает не только «что LLM написала», а весь путь поля до игры.

Цель:

```text
LLM authored
→ Python parsed
→ Python compiled
→ C# model field exists
→ C# runtime actually applies it
→ tooltip/debug честно показывает статус
```

Это не балансер и не автор предметов. Валидатор не должен решать, что предмет «должен быть мечом/луком/бронёй». Он только проверяет, что уже-authored поля реально дошли до исполнимого runtime или честно помечены как debug/future-disabled.

## Что проверять

Для каждого значимого поля:

- authored: есть ли поле в raw LLM JSON / runtimePlan.engineCalls;
- parsed: принял ли Python поле;
- compiled: попало ли оно в `GameplaySpec`, `AttackSpec`, `ArmorSpec`, `AccessorySpec` или debug/future блок;
- csharpField: есть ли поле в C# модели;
- runtimeApplied: есть ли реальный исполнитель в `GeneratedItem`, `GeneratedProjectile`, `InfiniCraftPlayer` и т.д.;
- tooltipVisible: видно ли игроку/разрабу, что поле применилось или было ограничено;
- status: `applied`, `clamped`, `future_disabled`, `unsupported`, `dropped`.

## Пример отчёта

```json
{
  "field": "AttackSpec.OnHitCode",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": true,
  "tooltipVisible": true,
  "status": "applied"
}
```

```json
{
  "field": "ArmorSpec.WhipRange",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": false,
  "tooltipVisible": true,
  "status": "future_disabled",
  "reason": "C# runtime does not implement generated whip range yet"
}
```

## Где хранить

В будущем:

```text
recipeMeta.appliedVsAuthored
/debug endpoint
/infiniitem command
Shift-tooltip short summary
```

## Жёсткие запреты

- Не делать category-routing по словам prompt.
- Не менять fantasy/resultKind.
- Не чинить баланс творчески.
- Не превращать validator в ещё одного автора.
- Не скрывать dropped/future fields.

Если поле не работает — отчёт должен прямо сказать, что оно future/debug-only, а не изображать готовую механику.
