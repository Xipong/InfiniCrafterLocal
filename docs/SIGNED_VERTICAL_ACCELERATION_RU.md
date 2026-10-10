# Знаковое вертикальное ускорение

Категория аудита **A14** открывает для свежего Author существующий знаковый диапазон `move_gravity_arc.gravityVelocityPerUpdate`: **−2…2** вместо положительного 0.001…2. Это расширение Author domain поверх прежнего низкоуровневого consumer, а не заявление о когда-то работающей исторической Author capability.

## Явный контракт

```json
{"id":"rise","fn":"move_gravity_arc","target":"shot","params":{"gravityVelocityPerUpdate":-0.1875}}
```

Terraria считает положительный Y направлением вниз. На каждом активном projectile update opcode 2 прибавляет указанное значение к `Projectile.velocity.Y`. Отрицательное значение ускоряет вверх, положительное — вниз; явный ноль оставляет вертикальную скорость прежней. Горизонтальная скорость не меняется. Это ускорение без terminal-speed cap, а не displacement, заданная высота или обещание приземления. Столкновение с тайлами, bounceCount, penetration, lifetime и отдельный controller остаются самостоятельными authored choices.

При `updatesPerTick=N` за world tick выполняется N прибавлений. При `N=6` и `gravityVelocityPerUpdate=-0.1875` вертикальная скорость за один полностью активный world tick изменяется на −1.125 pixels/projectile-update. Spawn speed по-прежнему измеряется в pixels/projectile-update; автоматического пересчёта единиц нет. Activation delay подавляет движение до первого активного update; lifetime учитывается по существующему контракту configure_spawn. Если controller в этот момент владеет движением, базовый movement не выполняется.

Поле обязательно: `neutral=0` описывает смысл нуля и float32 guard, но не разрешает пропуск; `default` отсутствует. Schema, prompt-card и validator берут диапазон из единственного `ParamSpec`. Bool, null, строки, нечисла, значения вне диапазона и ненулевые числа, исчезающие в float32, отвергаются. Никакого округления, clamp или выбора знака вместо Author нет. Обычное конечное float32 округление сохраняется; проверка nonneutral storage не обещает точного эффекта каждого микроскопического прибавления к уже большой скорости.

## Wire, provenance и совместимость

Значение дословно проецируется в `movement.params.gravityPerTick`; `name=move_gravity_arc`, `code=2` не меняются. Receipt связывает тот же authored leaf с фактическим final path и value. Strict wire принимает подписанный handoff и отвергает расхождение payload с receipt. Runtime body и DTO не изменены: существующий `RuntimeParamsSpec.Normalize` допускает −2…2, а `GeneratedProjectile.RunMovement` прибавляет `p.GravityPerTick`. Эта проекция — identity, не lossy normalization.

Прежний wire с положительными значениями и сохранённые opcode 6/`move_bounce` не переписываются. Fresh Author продолжает использовать только `move_gravity_arc`; retained bounce остаётся internal. Другие широкие defensive DTO ranges — shrink/expanding scale, return speed и timed yoyo — этим PR не открываются. Исторические fixtures и hashes сохраняются; общий suite продолжает проверять сохранённые документы.

Repair выдаёт разрешение только для неверного acceleration leaf. Попытка одновременно заменить валидные `fn`, collision или отрицательный acceleration во время починки другого поля игнорируется с audit; полезный разрешённый leaf merge сохраняется.

## Проверка

`LocalGenerator/tests/test_signed_vertical_acceleration.py` проверяет положительные, отрицательные, точный ноль, малые ненулевые числа, три update rates, provider/card parity, malformed inputs, receipts и frozen Repair. `test_source_audit_gates.py` вносит пять изолированных мутаций native DTO/consumer/timing и доказывает, что source gate их обнаруживает. Source gate проверяет method-scoped body, а не комментарий или совпадение строки в другом consumer.

`tools/EngineRuntimeChecks.VerticalAcceleration.cs` подготовлен для реального strict JSON reader и production `GeneratedProjectile.AI()`: две проверки охватывают четыре сетевые роли, N=1/2/6, signed/zero/float32 epsilon, неизменность X, задержку активации и отсутствие повторного запуска при hydration. Helpers изолируют actor arrays и роль, не заменяют ускорение, DTO или AI. Это method-level native checks, не симуляция Terraria world/network loop.

C# build, запуск EngineRuntimeChecks и игровые SP/MP smoke требуют .NET 8, stable tModLoader, ParticleLibrary и Luminance. В исходной среде подготовки PR они были **notRun**; это историческое ограничение не заменяется portable/source проверками.

При локальной композиции PR #26 ← проверенный #24/#14 выполнены parent-owned linked-native build (0 warnings, 0 errors) и четыре canonical checks: два signed vertical acceleration, один target bias, один nearest event damage; 4 PASS, 0 FAIL. DLL SHA-256: `bd0179e03c049457296a980fe0ffcad8d4f141ddc04ebf64187324b511331009`. Все 177 compile inputs сверены с замороженным manifest; Python/docs resolution их не меняет. Это headless method-level evidence, не игровые SP/MP, world/network loop или GPU smoke.

## Владельцы

- `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py`: Author domain, units и storage guard.
- `program_schema.py`, `validator.py`, `compiler.py`, `technical_lowering.py`, `wire_validator.py`: существующий общий schema/validation/identity projection/receipt pipeline.
- `ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs`: существующий signed DTO clamp.
- `ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs`: существующие activation/controller границы и signed opcode 2; opcode 6 сохранён для wire history.
