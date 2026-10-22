# Ортогональные модификаторы, фазы и независимое притяжение

Категории аудита A13 и B15.1. Это явное расширение низкоуровневой выразимости:
Author выбирает каждый модификатор и его параметры, compiler переносит их
один к одному. Новая композиция не выбирается по названию, damage class,
типу оружия или совпавшим числам. Отсутствие компонента сохраняет прежнее
поведение без вставки новых параметров в сохранённый wire.

## Какую проблему решает PR

Единственный `movement` slot не позволял одновременно выбрать отдельные
поворот, изменение скорости и позднее наведение. Старые spiral/vortex bundles
содержали такие сочетания, но сохранение их имён/кодов не доказывает сохранение
всех математических законов. Кроме того, нынешние vortex/blackhole одновременно
тормозят собственный projectile и притягивают NPC постоянной силой внутри radius.

Новые компоненты дают независимые решения и явные фазы. Старые movement opcodes
не переписаны; их прежние скрытые числовые константы не объявляются новым API.
Для точной композиции Author может явно выбрать `move_straight` и добавить
нужные turn/speed/homing modifiers. Другой допустимый movement остаётся его
самостоятельным выбором и исполняется первым.

## Author API

Все параметры новых компонентов обязательны. Optional является только сам
компонент: невыбранная capability отсутствует. Single-per-target означает,
что один target может иметь по одному компоненту каждого перечисленного типа.

| Capability | Параметры | Точный consumer |
|---|---|---|
| `set_projectile_turn_modifier` | `turnRadiansPerUpdate`, `startDelayTicks`, `durationTicks` | Поворачивает текущую velocity после movement |
| `set_projectile_speed_modifier` | `speedMultiplierPerUpdate`, `maxSpeed`, `startDelayTicks`, `durationTicks` | Умножает текущую velocity и ограничивает её длину после turn |
| `set_projectile_homing_modifier` | `rangeTiles`, `maxTurnRadiansPerUpdate`, `requireLineOfSight`, `startDelayTicks`, `durationTicks` | После speed поворачивает направление к выбранному NPC, сохраняя текущую длину velocity |
| `attract_npcs_while_active` | `rangeTiles`, `strengthPerUpdate`, `falloff`, `maxTargets`, `startDelayTicks`, `durationTicks` | Независимый server NPC impulse на каждом активном projectile update |
| `set_projectile_visual_scale_curve` | `startScale`, `endScale`, `startDelayTicks`, `durationTicks`, `curve` | Размер спрайта относительно исходных drawScale × visual.scale |
| `orient_whip_to_owner_gravity` | `{}` | Явный true marker; sweep и bend whip отражаются при обратной гравитации |

Первые три применимы к `free_projectile`/`child_projectile` с явным movement,
без controller, который владеет позицией. Это исключает молча перезаписанную
velocity у held/channel/sentry. Притяжение и visual curve доступны всем
projectile entity kinds, включая field/stationary. Visual curve исключает
beam/whip drivers: их special runtime body читает собственные collision
dimensions, а не sprite scale. `no_asset` остаётся явным выбором скрыть body;
при таком выборе curve не создаёт изображение автоматически. Притяжение само по себе
считается эффективным поведением поля без damage или movement.

Пределы: turn −0.5…0.5 radians/update; speed multiplier 0.8…1.2, cap 0.1…80
pixels/update; homing range 1…120 tiles и turn cap 0.0001…3.2 radians/update;
attraction range 1…80 tiles, strength 0.001…4, maxTargets 1…16. Delay 0…21600
world ticks, duration 1…21600. Visual endpoints 0.25…8.

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

Сами turn, speed и strength явно заданы **на projectile update**: extraUpdates
увеличивает количество применений за world tick. Это не скрытая нормализация
коэффициента в units/second. Например, multiplier 1.01 на 60 активных updates
даёт множитель `1.01^60` до cap; на 180 updates — `1.01^180`. Phase duration
при этом остаётся одной и той же в world ticks.

Скорость после turn/speed: `v = rotate(v, turn)`, затем
`v = v × multiplier`, затем ограничение magnitude до `maxSpeed`.
Нулевая velocity остаётся нулевой. Компоненты не создают начальный aim/speed.
Homing ограничивает кратчайший signed angle до authored turn cap и сохраняет
текущую magnitude после предыдущих модификаторов.

Пример независимой композиции на уже объявленном `bolt`:

```json
[
  {"id":"flight","fn":"move_straight","target":"bolt","params":{}},
  {"id":"turn","fn":"set_projectile_turn_modifier","target":"bolt","params":{"turnRadiansPerUpdate":0.04,"startDelayTicks":0,"durationTicks":90}},
  {"id":"accelerate","fn":"set_projectile_speed_modifier","target":"bolt","params":{"speedMultiplierPerUpdate":1.01,"maxSpeed":20,"startDelayTicks":0,"durationTicks":40}},
  {"id":"seek_later","fn":"set_projectile_homing_modifier","target":"bolt","params":{"rangeTiles":40,"maxTurnRadiansPerUpdate":0.1,"requireLineOfSight":true,"startDelayTicks":40,"durationTicks":50}}
]
```

Это фрагмент calls, а не полный playable item. Spawn, damage, lifetime,
collision, bindings и presentation остаются отдельно authored.

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
То же касается существующего `move_expanding_wave`. Repair ошибки этого
конфликта открывает точный mirror leaf, сохраняя остальные корректные числа.

## Whip и границы исторической реставрации

Выбор `orient_whip_to_owner_gravity` требует настоящего `move_whip_lash` и
исключает beam precedence. При owner.gravDir=-1 знаки sweep и bend меняются
вместе: полилиния отражается около исходного authored aim axis. Сам aim не
инвертируется. Та же `_whipPoints` коллекция задаёт body, tip и collision.
Отсутствующий marker сохраняет прежнюю геометрию независимо от gravDir.

Старые источники в аудите: `f04ee02` Runtime.cs 883–917 (spiral/vortex/pull),
939–943 (multiplicative scale + drag), 373–401 (whip gravDir). Новая API
описывает доступные математические компоненты и не обещает побайтово те же
bundled trajectories/константы или всю прежнюю temporal smoothing.

Старый yoyo timed-return branch имел отдельный lifetime defect: после начала
return он обходил timeLeft refresh. Исправный полный lifecycle по нему не
доказан. Этот PR не возвращает ошибочный timer и не объявляет yoyo полностью
утраченным семейством. Нынешний release-to-return остаётся существующим API.

## Provenance, Repair и проверки

Каждый новый leaf имеет source-backed compiler receipt. Wire с provenance
обязан предъявить ровно один соответствующий receipt на фактической entity;
нельзя приписать компонент чужому call/target или стереть его доказательства.
Gravity marker имеет отдельный exact fn receipt. Unknown/null/partial
components и неверные types/enums/ranges отклоняются, без clamp-to-valid repair.

Schema/cards и numeric range audit строятся из registry. C# DTO field inventory
содержит все пять новых component classes; mutation с неэкспонированным полем
делает audit RED. Frozen Repair проверяет исходные права: изменение duration
не даёт менять уже корректные delay, coefficients или другую кривую.

Восьми прежним fixture payloads не добавляются компоненты. Сохраняется также
полный frozen compiled-document baseline после отдельной проверки единственного
изменения global diagnostics count requirements: 28 → 37 с учётом A12 и
шести дополнительных declarative requirements этого PR.

Native harness вызывает production methods для turn/speed/phase/cap,
visual hydration без damage growth, server attraction/falloff/maxTargets,
homing owner/remote/range/tie, whip collision reflection и JSON boundaries.
Два унаследованных A12 сценария расширены наблюдением фактических PNG/primitive
vertices для отдельного visual owner: baked/reuse, declared/absent frame scale,
произведения 0.015625, 12 и 128, неизменный collision rectangle и `no_asset`.
Эти сценарии подготовлены, но их исполнение, C# build и SP/MP game smoke
**notRun**: в окружении нет native dependencies. Python/source checks не
подменяют проверку Terraria world loop, LOS на реальных tiles и network jitter.

База PR — A12 `audit/runtime-hitbox-curve`: общие declarative conflicts и
разделение visual/gameplay scale. C# source owners:
`GeneratedProjectile.Modifiers.cs`, `GeneratedProjectile.Executors.cs`,
`RuntimeProgramSpec.cs`. Default old wire и old movement opcodes не меняются.
