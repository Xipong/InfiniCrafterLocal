# Знаковое вертикальное ускорение

`accelerate_y.accelY` — явное ускорение в **блоках/с²**. Положительный Y направлен вниз, отрицательный — вверх. Это независимый composable motion component, не готовая траектория или обещание приземления.

Фрагмент calls для уже объявленного `shot`:

```json
{"id":"rise","fn":"accelerate_y","target":"shot","params":{"accelY":-900}}
```

Lowering переводит значение в `verticalAcceleration.accelerationYPerUpdate` по формуле `accelY × 16 / (3600 × N²)`, где N — явный `projectile_collision.updatesPerTick` того же target. Native increment имеет диапазон −2…2; contextual Author bounds выводятся из этого диапазона для выбранного N. Пример при N=2 даёт −1 px/update². X не меняется, speed cap не добавляется.

Activation delay подавляет активную механику; optional motion window ограничивает применение. Lifetime, tile collision, bounce, steering и другие force owners остаются отдельными решениями. Порядок компонентов — [Projectile Author](PROJECTILE_AUTHOR_API_RU.md#composable-motion).

Поле обязательно: смысл neutral=0 не разрешает omission без объявленного default. Bool, null, неверный тип, нечисла и выход за bounds отвергаются. Ненулевое значение не должно исчезать при float32 storage; обычное конечное float32 округление не гарантирует заметного прибавления к сколь угодно большой скорости.

Receipt связывает current authored leaf с exact typed wire, target и call. Predecessor receipts и старые movement opcodes не используются. Repair открывает только неверный leaf; попытка изменить валидные fn/collision/соседние параметры игнорируется с audit без отмены полезного исправления.

Owners: `capability_registry.py`, `parameter_contract.py`, compiler/strict-wire; C# `RuntimeMotionComponents.cs`, `GeneratedProjectile.ComposableMotion.Forces.cs`. Проверки current compiler и native `EngineRuntimeChecks.VerticalAcceleration.cs` должны наблюдать signed/zero, N, delay и hydration через настоящего consumer. Наличие source pattern не является PASS исполнения; команды — [TESTING](../../development/TESTING_RU.md).
