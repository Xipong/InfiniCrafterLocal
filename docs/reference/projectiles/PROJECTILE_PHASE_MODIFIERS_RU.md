# Ортогональные модификаторы, фазы и независимое притяжение

Текущие модификаторы выбираются независимо. Их отсутствие не создаёт поведения; имя предмета и DamageClass не выбирают состав компонентов. [Projectile Author](PROJECTILE_AUTHOR_API_RU.md) владеет общей композицией и окнами.

## Author API

| Capability | Решение | Единицы |
|---|---|---|
| `turn_velocity` | Поворот velocity после motion | Signed world angular rate |
| `scale_velocity` | Множитель после turn, до homing; optional speed cap | `scalePerUpdate` и `maxSpeed` в блоках/с |
| `homing` | Ограниченный поворот к ближайшей цели с сохранением скорости | Range в блоках, angular rate в рад/с |
| `attract_npcs` | Независимое ускорение NPC внутри радиуса | Блоки/с², explicit falloff и maxTargets |
| `sprite_scale_curve` | Интерполяция визуального размера, не collision | Множители и world-time interval |

Точные keys/bounds берутся из [registry inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md). Optional timing у turn/homing/attraction имеет объявленную нейтраль whole-life window; partial timing невалиден. `scale_velocity` допускает до двух доказуемо непересекающихся окон. Visual curve исключает beam/lash geometry и конфликтующий hitbox mirror; `no_asset` не создаёт изображение.

## Порядок и часы

На каждом активном AI step сохраняется следующий порядок:

1. Existing periodic actions и controller/movement.
2. Turn, затем speed, затем homing — фиксированный порядок независимо от
   расположения calls в Author. Author выбирает параметры и пересечение фаз.
3. Независимое NPC attraction.
4. Явная gameplay-to-sprite mirror из A12 либо отдельная visual curve.

Начальный activation delay останавливает весь active age. Внутри AI `_age`
увеличивается до consumers, поэтому активность интервала проверяется по времени
**начала** текущего шага: `max(0, age-1)/(extraUpdates+1)`. Интервал
`[startDelayTicks, startDelayTicks+durationTicks)` включает начало и исключает
конец. При duration=1 и extraUpdates=2 выполняются ровно три применения.

World angular rates и ускорение lowerer пересчитывает с учётом N данного target. Только явно безразмерный `scalePerUpdate` применяется на каждом AI update: больше updates означает больше умножений. Window duration остаётся world-time interval.

Порядок `v = rotate(v, turn)`, затем `v *= scalePerUpdate`, optional magnitude cap, затем homing сохраняется независимо от порядка calls. Нулевая velocity остаётся нулевой; modifiers не выбирают начальный aim/speed.

## Выбор цели и сетевая сторона

Homing просматривает ограниченный native NPC array и выбирает ближайший
`CanBeChasedBy(Projectile)` target внутри реального геометрического radius.
Равные расстояния разрешаются в пользу меньшего NPC slot index. При
`requireLineOfSight=true` используется native `Collision.CanHitLine` между
projectile и candidate boxes. Target за стеной исключается до выбора.
Нет target — нет steering; нет подстановки owner cursor или случайного NPC.

Homing selection выполняет owner/SP через существующий
`ShouldRunProjectileGameplay`. Изменённая velocity отмечается `netUpdate`.
Другие peers получают native projectile velocity; stateless turn/speed следуют
прежней prediction модели movement. Это не новая server collision proof и
не новый protocol для управления projectile.

NPC attraction выполняется только в SP/server через `ShouldRunNpcGameplay`.
Сканирование идёт по NPC slot index. Неактивные, нечейзабельные и zero-resistance
targets пропускаются; центр на нулевой дистанции и нулевая сила на границе
linear falloff не расходуют maxTargets. Применяется не более authored числа
положительных impulses за update. Изменённые NPC получают `netUpdate`.

Пусть `d` — расстояние, `r` — radius, `s` — authored strength и `k` — native
knockBackResist. Для eligible targets:

- constant: `impulse = direction × s × clamp(k, 0.1, 1)`;
- linear: `impulse = direction × s × max(0, 1-d/r) × clamp(k, 0.1, 1)`.

На половине radius linear даёт половину constant. На границе linear равен
нулю. Boss/immune NPC с native k≤0 не притягиваются. Этот PR не обходит native
resistance и не добавляет отдельный NPC maximum-speed policy. Повторное
применение действительно складывает velocity impulses.

## Visual growth и collision

Новая visual curve использует те же явные linear/exponential формы и world
tick schedule, что и gameplay curve A12, но хранится отдельным компонентом.
Её значение вычисляется из исходных endpoints и age, а не через повторное
умножение текущего `Projectile.scale`. Поздняя hydration поэтому не запускает
рост заново и не накапливает ошибку двойного scale.

`linear = start + (end-start)×t`; `exponential = start×(end/start)^t`, где
`t` ограничен 0…1. До delay сохраняется start, после duration — end.
Projectile.scale = drawScale × visual.scale × curve. Размер damage rectangle
и tile collision из этого значения не выводятся.

При явном motion `window` curve пишет scale только во время выбранной фазы;
после её закрытия сохраняется последнее значение. `visualScaleRate` также
накапливает состояние по активным AI updates. Native `SyncProjectile` не
переносит `Projectile.scale`, поэтому только эти два stateful случая используют
ExtraAI v7: прежний composable snapshot и одно конечное число scale в диапазоне
0.01…128. Exact definition обязана содержать `visualScaleRate` или windowed
`visualScaleCurve`; отсутствующее, лишнее, non-finite или выходящее за диапазон
состояние отвергается, в том числе при поздней загрузке definition. Остальные
projectiles сохраняют прежние варианты v4/v5/v6; сохранённый item DTO не меняется.
Для stateful scale клиент и сервер должны использовать совпадающую версию мода.

Hydration восстанавливает полученное значение без повторного применения rate.
Локальный authoritative source сохраняет собственный scale; старые наблюдения
не откатывают scale и active clock ни у уже исполняющегося peer, ни в pending
очереди definition. Следующая AI-update выполняет ровно следующий authored шаг.

Основной PNG и generic `runtime_geometry` получают полный продукт именно
этой явно выбранной visual curve. Старый clamp 0.1…8 и минимальные размеры
generic body не обрезают его; например, drawScale=2, visual.scale=3 и curve=2
дают 12 в конечной отрисовке. Без explicit visual owner сохраняются прежние
пределы renderer. Отдельные VFX body-copy consumers сохраняют собственные
опубликованные формулы масштаба и не объявляются автоматически синхронными.

Visual Director и его Repair получают принятые компоненты с точными
registry-owned meanings как read-only context. Реальные image/retry packets
содержат visual curve и independent hitbox curve для distinct PNG и shared
root/reuse. Эти стадии не создают кривую, не выбирают mirror и не изменяют
gameplay endpoints. Размер root item PNG по-прежнему принадлежит item,
а reuse не создаёт дополнительный image job.

Отдельная gameplay curve может одновременно иметь другие endpoints/timing.
Для такого выбора её `mirrorToSprite` должен быть false. При true она сама
владеет динамическим sprite scale; две явные scale authority отвергаются.
Repair ошибки этого
конфликта открывает точный mirror leaf, сохраняя остальные корректные числа.

## Lash и гравитация

`lash_geometry.useOwnerGravity` явно отражает sweep и bend при owner.gravDir=-1. Aim не инвертируется; одна полилиния задаёт collision и принятую presentation geometry. Это поле текущей geometry, не marker для старого movement opcode.

## Provenance, Repair и проверки

Каждый новый leaf имеет source-backed compiler receipt. Wire с provenance
обязан предъявить ровно один соответствующий receipt на фактической entity;
нельзя приписать компонент чужому call/target или стереть его доказательства.
Unknown/null/partial
components и неверные types/enums/ranges отклоняются, без clamp-to-valid repair.

Schema/cards и numeric ranges строятся из registry. Frozen Repair неверного timing не открывает валидные coefficients, delay или другую кривую.

Native owners: `GeneratedProjectile.Modifiers.cs`, `GeneratedProjectile.ComposableMotion*.cs`, `RuntimeMotionComponents.cs`. Registered checks наблюдают turn/speed/phase/cap, visual hydration, server attraction/falloff/maxTargets и homing authority/range/tie через actual consumers. Source-scanner полнота DTO не является доказательством исполнения; текущие команды — [TESTING](../../development/TESTING_RU.md).
