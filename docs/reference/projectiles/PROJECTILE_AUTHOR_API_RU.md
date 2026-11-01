# Projectile Author: точные формы position, immunity и when

Эта категория упрощает выбор уже существующего поведения снарядов. Канонические формы находятся в [`capability_registry.py`](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py); compiler, provider schema, validator, Repair и generated inventory получают их из одного registry. Runtime wire и C# executors сохраняют прежние имена, opcodes и единицы.

[Точное имя `damage_nearest_on_event` и текущий диапазон `sameTargetBias`](../authoring/AUTHOR_EVENT_DOMAINS_RU.md) используют прежние runtime consumers без поддержки retired receipt owners/domains.

[Независимая зарядка, мировая скорость орбиты и collided-axis отскоки](PROJECTILE_CHARGE_ORBIT_BOUNCE_RU.md) расширяют те же драйверы и collision hook; старые сохранённые определения сохраняют прежние значения при отсутствии новых полей.

## Дистанционное завершение: подготовить и активировать

`end_projectiles` завершает живые экземпляры выбранной сущности этого предмета
по принятому нажатию игрока. Первичное использование может размещать заряды,
создавать орбитальные сферы или выпускать летящий снаряд; альтернативное —
завершать их в выбранный игроком момент. Последствия задаются отдельно обычными
`on_kill` действиями и VFX соответствующей сущности.

Фрагмент Author-композиции с уже объявленными `item` и `charge`:

```json
{
  "bindings": [
    {
      "id": "prepare",
      "input": "primary_use",
      "action": {"kind": "spawn_entity", "targetId": "charge"},
      "stackCost": 0,
      "contactDamage": false
    },
    {
      "id": "activate",
      "input": "alternate_use",
      "action": {"kind": "use_item_body", "targetId": "item"},
      "stackCost": 0,
      "contactDamage": false
    }
  ],
  "calls": [
    {
      "id": "end_charges",
      "fn": "end_projectiles",
      "target": "item",
      "params": {
        "when": {"on": "on_use", "useInput": "alternate_use"},
        "entity": "charge"
      }
    }
  ]
}
```

Это фрагмент, а не полное определение предмета: сущности, их spawn/movement,
обязательные характеристики, visuals и terminal actions выбираются отдельно.
`end_projectiles` не наносит урон сам по себе. Например, `spawn_on_event` на
`charge.on_kill` выпускает дочерние снаряды, а `damage_nearby_on_event` создаёт
явно заданный удар вокруг каждой завершённой сущности. Без terminal actions
команда просто убирает выбранные экземпляры.

Границы исполнения:

- Источник — только `item_body`, событие — `on_use`; `useInput` использует
  существующий выбор `primary_use`, `alternate_use` или `both`.
- `entity` адресует существующую projectile-сущность этой композиции. Это
  ссылка управления, а не spawn-edge: она не создаёт снаряд и не увеличивает
  глубину дочерних появлений.
- Совпасть должны владелец, ID определения предмета и ID сущности. Другие
  игроки, другие определения, другие сущности и обычные Terraria projectiles
  не затрагиваются. Две копии одного определения у одного владельца адресуют
  общий набор его снарядов этого определения.
- Все подходящие живые экземпляры выбираются перед первым завершением.
  Дочерние снаряды, появившиеся из `on_kill`, и новые обитатели повторно
  использованных native slots не попадают в эту же команду.
- Вызов немедленный, без собственного delay. Он использует native
  `Projectile.Kill()` и штатный `on_kill`; отдельно не испускает `on_expire`.
  Если экземпляр уже достиг естественного края lifetime, сохраняется обычная
  обработка пропущенного expiry в `OnKill`.
- Команду исполняет владеющий клиент либо single-player. Native kill packet
  и существующий terminal lifecycle доставляют уничтожение остальным peers;
  dedicated server и наблюдающие клиенты повторно не выбирают цели команды.
- Удаление освобождает текущую occupancy, но не восполняет lifetime allowance
  дочерних появлений. Сохраняются существующие лимиты spawn/depth/owner pool.
  При отсутствии подходящих экземпляров результат — обычный no-op.

Wire action `end_projectiles` использует opcode `12`. Выбранный `fn` фиксирует
`delayTicks=0` с compiler receipt: это точная проекция объявленной операции,
без добавления механики из имени предмета. Author/Repair/provider schema
получают контракт из registry; strict wire и C# отклоняют неверный
source/event/reference и положительную задержку.

## Lifetime и независимые пределы

`set_projectile_lifetime.lifetimeTicks` принимает **1…36000 world ticks**.
Author/provider schema, обычный и Repair catalog, validator и compiler берут
предел из canonical registry; wire сохраняет выбранное целое без изменения.
C# `InfiniRuntimeLimits.MaxRuntimeLifetimeTicks` сохраняет 36000 при
`FromJson` и full/cache/network round trips; значение выше предела отклоняется,
а не превращается в допустимое через clamp. Прежний нижний normalization
persisted DTO не меняется. `GeneratedProjectile.Configure` переводит world ticks
в projectile updates через `1 + extraUpdates`; activation delay добавляется отдельно.

Этот же canonical C# constant уже используется detached VFX для **retention
неактивного source particle-budget ledger**: запись теперь удаляется после более
чем 36000 ticks без активности вместо 21600. Это намеренный сопутствующий эффект,
не увеличение duration самих VFX emissions или particle/draw allowance.
Buff durations, modifier/curve `startDelayTicks`/`durationTicks`, spawn activation
delay, event delays и `maxEventSpawnsPerActivation=32` сохраняют свои прежние пределы.
Native sentry limit может удалить sentry раньше заданной lifetime.

У сохранённого `charge_then_release` ожидание отпускания не расходует этот lifetime:
controller компенсирует native decrement после каждого charging AI update,
включая `extraUpdates`. После release countdown идёт обычным способом;
поздняя hydration его не перезапускает. `_age` и независимые periodic/modifier
clocks продолжают идти во время charging. Смена предмета запускает release,
а недоступный/погибший owner по-прежнему завершает projectile без ожидания.

В новой композиции `accumulate_projectile_charge` только накапливает заряд и
фиксирует release. Пауза lifetime выбирается отдельно через
`apply_projectile_charge_release.pauseLifetimeWhileCharging=true`; при `false`
или без этой операции обычный lifetime продолжает расходоваться во время зарядки.

## NPC immunity и число обновлений

Полный пример collision:

```json
{
  "id": "collision",
  "fn": "set_projectile_collision",
  "target": "projectile",
  "params": {
    "tileCollide": true,
    "ignoreWater": false,
    "bounceCount": 2,
    "pierce": -1,
    "updatesPerTick": 2,
    "immunity": {"localCooldown": 10}
  }
}
```

| Author | Точные поля collision в существующем wire |
|---|---|
| `immunity: "owner_shared"` | `npcImmunityMode: "owner"`, `localNpcHitCooldownTicks: -1` |
| `immunity: "once_per_npc"` | `npcImmunityMode: "local"`, `localNpcHitCooldownTicks: -1` |
| `immunity: {"localCooldown": n}` | `npcImmunityMode: "local"`, `localNpcHitCooldownTicks: n`; integer `0..600` |
| `updatesPerTick: n` | `extraUpdates: n - 1`; integer `1..6` ↔ `0..5` |

Owner immunity разделяет Terraria cooldown между снарядами владельца; consumer сам выставляет локальный engine cooldown в `-2`. Поэтому wire `-1` в этой ветви — объявленная неисполняемая техническая константа. В local ветви `-1` означает один hit по каждому NPC, а `0..600` передаются как сырые engine counts. `0` сохраняется; он не переименован в частоту по world ticks. `pierce`, lifetime и immunity независимы.

`updatesPerTick` меняет только способ записать число обновлений. Скорость, gravity, steering, drag и local cooldown сохраняют свои прежние единицы на projectile update. Таймеры сохраняют собственные conversions и фазу; compiler не масштабирует их вместе с этим параметром.

## Одна spawn position

`configure_spawn.params.position` имеет ровно две закрытые формы:

```json
{"at": "activation_origin"}
```

```json
{"above": "cursor", "heightTiles": 8, "activationDelayTicks": 15}
```

При положительном `activationDelayTicks` все ожидающие projectile updates, включая последний, остаются без NPC-урона. На следующем, первом активном update выполняются `on_spawn` и controller до native collision; поэтому ожидание не может потратить `pierce` и удалить ещё не испущенные `on_spawn` actions. Число ожидающих updates равно `activationDelayTicks × (1 + extraUpdates)`; lifetime активной фазы и выбранная launch velocity не меняются.

У обеих форм одинаковый список anchors:

| Anchor | Прежний wire placement и смысл |
|---|---|
| `activation_origin` | `item_use_origin`: origin вызывающего producer, включая event position или sentry origin |
| `owner_center` | `owner_center`: mounted center владельца |
| `cursor` | `cursor`: позиция курсора |
| `ground_at_cursor` | `ground_at_cursor`: прежний поиск земли под курсором |
| `native_resting_spot` | `native_resting_spot`: явный `Player.FindSentryRestingSpot` с native reachable-area clamp и выравниванием по половине hitbox height; не включает native sentry lifecycle |

`at` записывает нулевые `overTarget.heightTiles` и `overTarget.delayTicks`. `above` записывает явные `heightTiles` в диапазоне `1..80` и `activationDelayTicks` integer `0..600` в прежние `overTarget.heightTiles` / `overTarget.delayTicks`. Для отсутствия задержки в этой форме нужно написать `0`. Новая форма `at` с положительной задержкой не входит в этот контракт: это отдельное расширение прежнего Author, для которого нужна отдельная проверка runtime.

Вертикальный сдвиг происходит до расчёта `aim`, а forward `offsetPx` — после него. Поля `aim`, speed, offset и movement остаются самостоятельными решениями. Старый `above_cursor` выражается как `above: "cursor"`; старый вариант без явной высоты имел высоту один tile, которую теперь нужно написать явно.

Activation delay относится к уже созданному projectile: он занимает live slot, до активации не движется и не запускает `on_spawn`. Начальный `timeLeft` включает authored lifetime и updates ожидания. Это отдельный clock от delay event action. Retired `spawn_over_target` capability удалена; current `configure_spawn.position` по-прежнему проецирует `spawn.overTarget` и сохраняет current front-hand/hit-target запреты.

## Typed when и единая тяга

В event capabilities ключ `when` задаёт обычное событие либо период:

```json
{"when": "on_hit"}
```

```json
{"when": {"everySeconds": 0.2}}
```

Каждая capability сохраняет прежний конечный набор допустимых events. Периодическая форма доступна только там, где раньше поддерживался `periodic`; `everySeconds` задаёт интервал в секундах с проекцией в bounded world ticks (`6..3600`). Она записывает `event: "periodic"` и `periodTicks` после объявленного округления. Обычная строка записывает только прежний event. Ни старый ключ `event`, ни отдельный `periodTicks`, ни строка `when: "periodic"` не принимаются как новая Author форма.

Call IDs, порядок actions, producer dependencies, фаза item/projectile periodic, scheduler и бюджеты сохраняются. Optional `delaySeconds` проецируется в отдельный wire leaf `delayTicks`. При Repair ошибочного `when.everySeconds` валидные siblings и остальные параметры frozen.

```json
{
  "id": "grapple_hit",
  "fn": "pull_on_event",
  "target": "projectile",
  "params": {"when": "on_hit", "mode": "both", "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
}
```

Свежий `pull_on_event` явно выбирает `target_to_owner`, `target_to_entity`,
`owner_to_target` или `both`. Последние два режима требуют `on_hit/on_crit`
и действительную цель события, без поиска замены. У `both` две независимые
силы; NPC учитывает `knockBackResist`, игрок — нет. Authority игрока и NPC
раздельная. NPC-режимы сохраняют свой radius и прежний fallback при отсутствии
active directTarget; `target_to_entity` использует центр source projectile,
зафиксированный до delay. [Полный новый договор](../authoring/AUTHOR_API_SIMPLIFICATION_RU.md).

Исторический `pull_owner_to_event_target` остаётся внутренним receipt owner:
его сохранённые литералы `actionCode=5`, `mode=owner_to_target`, `radiusTiles=1`
и прежние события исполняются без миграции. Это не свежая Author-форма.

## Радиусы в tiles на точной решётке

| Capability / Author leaf | Domain | Прежний integer wire |
|---|---|---|
| `damage_nearby_on_event.radiusTiles` | `0.5..60`, шаг `1/16` | `radiusPx = n × 16`, integer `8..960` |
| Сохранённый `move_proximity_missile.triggerRadiusTiles` | `0.25..32`, шаг `1/16` | `proximityRadiusPx = n × 16`, integer `4..512` |

Все 761 AoE и 509 proximity значений старого integer domain сохраняются точно. Дробь со знаменателем 16 и умножение на 16 не округляют эти значения. Произвольные дроби, например `0.1 tile`, отвергаются в этих lattice projections; compiler не округляет их. Новый независимый `set_projectile_proximity_action.triggerRadiusBlocks` имеет собственный float-domain из registry и не наследует integer-lattice ограничение старого controller. Event radius проходит тот же registry projection и receipt proof. Damage basis, search, excluded direct target и authority не меняются.

<a id="только-объявленные-неисполняемые-поля-можно-опустить"></a>
## Только объявленные технические значения можно опустить

Точный owner — `ParamSpec` и Lowery, не совет в prompt. Пропуск разрешён только в объявленном контексте; present `null`/неверный тип не превращается в default. Валидное явно выбранное значение сохраняется, даже если выбранная ветвь его не читает.

| Leaf | Когда omission разрешён | Материализованный wire |
|---|---|---|
| `configure_spawn.count` | target kind строго `child_projectile` | `1` |
| `configure_spawn.spreadRadians` | `child_projectile` либо exact integer `count=1` | `0` |
| `spawn_entity_on_event.spreadRadians` | exact integer `count=1` | `0` |
| `set_projectile_collision.bounceCount` | `tileCollide` строго `false`; старые return-controller branches сохраняются для проверки принятого wire | `0` |
| `set_projectile_aim.turnOwner` | независимый поворот владельца не выбран | `false` |
| `attach_projectile` axis/normal offsets | смещение не выбрано | `0` |
| `set_projectile_return_trigger` release/tile flags и collision-disable policy | соответствующее независимое поведение не выбрано | `false` |
| `set_projectile_owner_control` guard/claim flags, animation/lifetime overrides | соответствующий эффект не выбран; полностью пустой control запрещён | `false`, `none`, `authored` |
| `set_projectile_rotation.offsetRadians` | дополнительный offset не выбран | `0` |
| `set_projectile_rotation.radiansPerSecond` | exact mode не `spin` | `0` |
| `apply_projectile_charge_release` damage/knockback/speed multipliers | усиление соответствующего значения зарядом не выбрано | `1` |
| `apply_projectile_charge_release.pauseLifetimeWhileCharging` | пауза lifetime не выбрана | `false` |
| `set_projectile_beam_ramp` initial width/damage multipliers | соответствующий ramp не выбран | `1` |
| `set_projectile_beam_ramp.damageStartProgress` | дополнительная задержка eligibility не выбрана | `0` |

`child_projectile` получает count/spread от своего producer; root `free_projectile` не становится child из-за ссылки event. При `count>1` fan spread остаётся явным выбором. Radial/disk velocity по-прежнему несовместима с ненулевым fan spread: допустимый пропуск удовлетворяет exact zero, но present nonzero не стирается. У обычного движущегося projectile с `tileCollide=true` bounce count обязателен: N контактов отражаются, следующий убивает. Старые return opcodes сохраняют прежний early-return branch; это не общее правило новых return primitives. Пустой ReturnTrigger невалиден: должны быть выбраны хотя бы время, расстояние, release или tile contact.

Единственные варианты `arrival.action=kill` и `manaSustain.cadence=held_item_use_time` выбраны точным `fn` и материализуются Lowery, а не повторяются обязательными source-полями. Это не нейтраль `kill`: смысл выбранной операции явно описан её карточкой. Native wire сохраняет оба discriminators.

Нейтральные множители charge release не означают «сохранить текущую velocity»: выбранный release по-прежнему запускает снаряд по своему направлению с обязательной явно заданной `launchSpeedBlocksPerSecond`. `warmupSeconds` beam ramp также остаётся явным. Ни пропуски, ни Repair не создают отсутствующие charge/beam capabilities и не меняют их зависимости.

Compiler не переписывает Author: каждый разрешённый пропуск получает `declared_neutral_omission` receipt. Audit заново проверяет контекст и exact output/value по Author, а при его отсутствии — по доступным final-wire discriminator/kind. Source-free proof не удостоверяет отсутствующий Author. Fn-selected технические literals, включая executor identity и activation flags, также требуют точного значения и уникального покрытия; согласованная подмена значения вместе с receipt не доказывает его правильность.

Repair сохраняет принятое отсутствие frozen. Разрешённое изменение контекста может открыть только leaf, который действительно стал обязательным; оно не разрешает заполнить остальные отсутствующие side controls или поменять валидные siblings.

<a id="composable-motion"></a>
## Композиция движения вместо составного controller

Новая модель не выбирает bundled «flail», «phase», «sine homing» или «front hand attack». Она независимо выбирает исполняемые операции из [живого registry inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md):

| Решение | Независимые операции |
|---|---|
| Направление, привязка, рука и вылет | `set_projectile_aim`, `attach_projectile`, `set_front_arm_pose`, `set_projectile_reach_curve` |
| Траектория и steering | `move_straight`, `orbit_projectile`, `seek_projectile`; turn/homing modifiers и `scale_projectile_velocity` |
| Ускорение, затухание и колебание | `accelerate_projectile_vertical`, `multiply_projectile_velocity`, `oscillate_projectile_velocity` |
| Начало возврата, достижение владельца, proximity | `set_projectile_return_trigger`, `set_projectile_arrival`, `set_projectile_proximity_action` |
| Вращение и видимость | `set_projectile_rotation`, `set_projectile_opacity`, `add_projectile_visual_scale`; существующие visual/hitbox curves остаются раздельными |
| Input/liveness, накопление, release и контакт | `set_projectile_owner_control`, `accumulate_projectile_charge`, `apply_projectile_charge_release`, `gate_projectile_contact` |
| Beam/lash geometry и независимое поддержание | `set_projectile_beam_geometry`, `set_projectile_beam_ramp`, `set_projectile_lash_geometry`, `sustain_projectile_mana` |

`oscillate_projectile_velocity` сохраняет оба закона. `angular_sine` задаёт периодическую угловую скорость и не меняется. `lateral_velocity_sine` поворачивает текущую скорость, сохраняя её модуль: при ненулевой мировой скорости `S`, амплитуде `B`, фазе `q` и `u=updatesPerTick` приращение направления равно `atan((B/S)·sin(q))/u`. Делится **угол после atan**, не амплитуда внутри него: медленные снаряды по-прежнему реагируют сильнее с нелинейным насыщением. Нулевая скорость остаётся нулевой.

Для lateral при `u=1` сохранён прежний расчёт; при `u>1` устранено ошибочное усиление поворота с числом subupdates. Это намеренно меняет траектории уже сохранённых composable lateral items с `u>1`, без миграции wire. Старый bundled sine controller не меняется. Фаза берётся из общего active age, окно только включает/выключает воздействие: не перезапускает синус и не выпрямляет уже изменённую скорость. Это дискретное интегрирование первого порядка, а не обещание тождественных траекторий при разных `u`; высокая частота по-прежнему может давать sampling aliasing.

`target_and_fire` уже независим от движения и не заменяется новым контроллером. Поиск цели для firing не выбирает цель steering. Старый velocity-lerp seek не объявлен эквивалентом capped-angular homing: это разные явно выбранные законы.

Optional `window` задаёт конечные native phases `always`, `charging`, `released`, `outbound`, `returning`, а не произвольную state graph. Форма `{phase}` означает всю фазу без выдуманного максимального duration. Timing задаётся целиком: `clock`, `startDelaySeconds`, `durationSeconds`; частичная группа и present null отвергаются. `released` — latch, который может пересекаться с `returning`, а не отдельная взаимоисключающая стадия. Relative clock не активен до соответствующего release/return. Отсутствие window не добавляет фазу или таймер.

Для `set_projectile_turn_modifier`, `set_projectile_homing_modifier` и `attract_npcs_while_active` можно опустить одновременно `window`, `startDelaySeconds` и `durationSeconds`: модификатор действует всё активное время жизни без дополнительного timing gate. Это объявленная нейтраль `ParamSpec.default = neutral = {"phase": "always"}`; compiler материализует канонический `window` с receipt `declared_neutral_omission`, не меняя Author и не подставляя максимальную длительность. Для ограничения времени достаточно одного явного `window`; `since_release` и `since_return` начинают интервал от соответствующего latch.

Прежняя полная пара `startDelaySeconds` + `durationSeconds` сохраняет active-age интервал. Явная пара вместе с `window` исполняется как их **пересечение**, как прежде; полная пара и явное окно не переписываются. Одинокое поле пары, present `null`, неверное окно и отсутствующий обязательный motion/latch producer остаются RED. Native/stripped wire без пары и без окна по-прежнему отвергается: разрешение пропуска относится к Author, а timing для wire поставляет compiler. Repair другого numeric leaf сохраняет принятое отсутствие, полную пару и явное окно frozen, без заполнения или удаления. Сохранённые определения не мигрируются. Времена reach/arm/visual/hitbox curves задают саму интерполяцию, а не только gate, поэтому не заменяются этим правилом.

Relative interval включает первый исполняемый AI subupdate: для release/timed return это текущий update, для tile callback после AI — следующий. Окно длиной один tick сохраняет все `updatesPerTick` шаги. Phase-only spin применяет выбранную скорость на каждом шаге, без повторения первого угла после latch.

В свежем Author фазы `charging`/`released` и clock `since_release` требуют явного `accumulate_projectile_charge`; фаза `returning` и clock `since_return` — явного `set_projectile_return_trigger`. Это относится и к окнам существующих modifiers. Сам `seek_projectile` или catch/arrival не создаёт return latch; отсутствующий producer — RED, а не автоматически добавленная механика. `outbound` означает отсутствие return latch и сам по себе не требует триггера возврата.

Tile collision остаётся явным решением: always-active attachment и lash пока не исполняют native body tile collision, поэтому `tileCollide=true` с ними отвергается; код не заменяет его на `false`. Ограниченная phase/timing attachment может сохранить tile collision для самостоятельного free-flight интервала. На одном теле нельзя одновременно назначить несовместимых владельцев абсолютной позиции. Seek допускает два независимых call только с непересекающимися фазами; overlap и неподдерживаемые сочетания дают refusal, не silent last-writer-wins. Привязка во время charging может сочетаться с released flight. Ось, spin, opacity, return trigger, catch, tile collision, lifetime и owner input не добавляются друг из друга. Например, timed/distance return может работать с `channel=false`; return-on-release требует явно выбранного `channel=true`. Beam line может двигаться с обычным lifetime без навязанного channel/attachment/mana. Proximity expiry не требует homing и не становится `on_hit`.

`cursorLeashBlocks` допустим только для cursor seek; `searchRangeTiles` и `requireLineOfSight` — только для nearest-NPC seek. `durationSeconds` у lash допустим только с `clock=active`. Лишний optional leaf даёт RED; targeted Repair может удалить только его, не менять валидный selector. Неизвестный selector не делает соседние значения автоматически невалидными.

Свободные opacity/rotation/force primitives не отменяют снаряд из-за `noItems`, `CCed` или смерти активного владельца: это неявно не добавляет owner control. При proximity expiry owning peer отправляет существующий native projectile snapshot перед native kill. Сервер отдельно проверяет authored cause, окно и фактическую NPC geometry, исполняет свою event authority ровно один раз и передаёт VFX существующим relay; чужой event-fired flag не считается выполнением серверного события. Обычный tile/contact kill не превращается в expiry.

Если metadata отсутствует, terminal receipt может дождаться определения только на том же живом source с неизменившейся конечной позицией. После retirement или изменения позиции сервер не реконструирует и не угадывает пропущенный эффект; event clock receipt не перематывает текущий возраст снаряда.

Параметры нового Author выражаются в объявленных registry units: мировые блоки, секунды и соответствующие скорости; per-update multipliers/lerp остаются безразмерными per-update. Compiler учитывает `updatesPerTick` там, где объявлена такая проекция. В wire остаются native pixels, updates и ticks, а старые сохранённые формулы и clocks не пересчитываются при чтении.

<a id="один-fresh-gravity-movement-и-сохранённые-записи"></a>
## Сохранённые записи и свежий Author

Runtime API v5 / wire v3 сохраняются. Старые movement opcodes и `channel_beam`/`charge_then_release` доступны для чтения принятого wire, но не предлагаются как свежие Author/Repair capabilities. Их исполнение сохраняет прежние formulas, порядок, return/collision/terminal behavior, включая старые неудачные gameplay choices. Stored definitions, receipts, worlds и player data не мигрируются. Ранее retired opcode `6` остаётся запрещённым; остальные коды не перенумерованы.

Новые комбинации проверяются через реальные validator/compiler/strict-wire и зарегистрированные native CPU observers; DTO admission сама по себе не доказывает движение, render, игру или multiplayer. Основные regressions — `test_composable_motion_*`, `test_motion_lowering_*`, `test_motion_repair_visibility.py`, `test_motion_presentation_handoffs.py` и `EngineRuntimeChecks.ComposableMotion*.cs`. Исторические fixtures не превращаются в свежий model output и не переписываются ради GREEN.

## Вложенные свойства Author

Свежий Author задаёт зависимые настройки непосредственно у их владельца:

- `set_projectile_beam_geometry.params.ramp` — необязательные прежние поля прогрева луча: `warmupSeconds`, `initialWidthMultiplier`, `initialDamageMultiplier`, `damageStartProgress`.
- `attach_projectile.params.reachCurve` — необязательная кривая вылета с прежними полями и собственным `window`. Окно attachment и окно reach независимы; вылет применяется только при активной привязке. Кривая остаётся age-based и не запускается заново при открытии окна.
- `accumulate_projectile_charge.params.releaseEffect` — необязательные прежние усиления и явный `launchSpeedBlocksPerSecond`. Отсутствие свойства не создаёт эффект освобождения. Даже единичные множители в присутствующем эффекте переписывают launch velocity, поэтому это не замена отсутствию.

Это alias lowering явно выбранных полей, а не новый controller: `beamGeometry`/`beamRamp`, `attachment`/`reach`, `charge`/`chargeRelease` остаются отдельными native-компонентами. Опущенные объявленные нейтральные листья материализуются только внутри присутствующего свойства и имеют точные nested-path receipts. Принятые отсутствия и соседние значения остаются frozen при Repair.

Отдельные свежие вызовы `set_projectile_beam_ramp`, `set_projectile_reach_curve`, `apply_projectile_charge_release` больше не принимаются. Их сохранённый wire и исторические receipts продолжают проверяться и исполняться без миграции; это не скрытые свежие aliases.
### Единое масштабирование скорости свежего Author

`scale_projectile_velocity` умножает текущую скорость **после turn, перед homing**.
`multiplierPerUpdate` явно задаётся в диапазоне 0..1.2; ноль останавливает,
малый положительный коэффициент сильно тормозит. Необязательный
`maxSpeedBlocksPerSecond` ограничивает модуль после умножения; отсутствие означает
настоящее отсутствие cap, а не большой подставленный предел. Множитель применяется
каждый projectile update, включая дополнительные updates.

Допустимы один вызов на всё время жизни либо до двух вызовов с доказуемо
непересекающимися `window`: например, разгон в первую секунду и торможение во
вторую, либо разные `outbound`/`returning` фазы. Конечные интервалы одного clock
полуоткрытые; разные clocks не считаются непересекающимися без взаимоисключающих
фаз. Порядок calls не разрешает пересечение. Это не произвольный pipeline.

Старые `multiply_projectile_velocity` и `set_projectile_speed_modifier` больше не
предлагаются свежему Author. Их сохранённые wire-компоненты и исторические receipts
не меняются: ранний retention и поздний speed продолжают исполняться по прежним
правилам. Для новых предметов единственная поздняя стадия — сознательная
нормализация, **не** эквивалентность прежнему одновременному early/late исполнению.
Две независимые временные фазы остаются; комбинация новых и старых scalers
запрещена. Отсутствующий cap и валидное соседнее окно остаются frozen при Repair.
