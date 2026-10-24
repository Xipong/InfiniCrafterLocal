# Projectile Author: точные формы position, immunity и when

Эта категория упрощает выбор уже существующего поведения снарядов. Канонические формы находятся в [`capability_registry.py`](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py); compiler, provider schema, validator, Repair и generated inventory получают их из одного registry. Runtime wire и C# executors сохраняют прежние имена, opcodes и единицы.

[Точное имя `damage_nearest_on_event` и текущий диапазон `sameTargetBias`](../authoring/AUTHOR_EVENT_DOMAINS_RU.md) используют прежние runtime consumers без поддержки retired receipt owners/domains.

[Независимая зарядка, мировая скорость орбиты и collided-axis отскоки](PROJECTILE_CHARGE_ORBIT_BOUNCE_RU.md) расширяют те же драйверы и collision hook; старые сохранённые определения сохраняют прежние значения при отсутствии новых полей.

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

## Typed when и отдельная тяга владельца

В event capabilities ключ `when` задаёт обычное событие либо период:

```json
{"when": "on_hit"}
```

```json
{"when": {"everyTicks": 12}}
```

Каждая capability сохраняет прежний конечный набор допустимых events. Периодическая форма доступна только там, где раньше поддерживался `periodic`; `everyTicks` — integer `6..3600`. Она записывает `event: "periodic"` и `periodTicks: n`. Обычная строка записывает только прежний event. Ни старый ключ `event`, ни отдельный `periodTicks`, ни строка `when: "periodic"` не принимаются как новая Author форма.

Call IDs, порядок actions, producer dependencies, фаза item/projectile periodic, scheduler и бюджеты сохраняются. Optional `delayTicks` остаётся отдельным leaf event action. При Repair ошибочного `when.everyTicks` валидные siblings и остальные параметры frozen.

```json
{
  "id": "grapple_hit",
  "fn": "pull_owner_to_event_target",
  "target": "projectile",
  "params": {"when": "on_hit", "strength": 2}
}
```

Эта операция записывает старые `action: "pull_on_event"`, `actionCode: 5`, `mode: "owner_to_target"`, `radiusTiles: 1`. Константы связаны receipt с выбранным `fn`, а не с вымышленным authored числом. Strength сохраняет диапазон `0.01..4` и прежнюю точность.

Тяга направлена к active directTarget события. При отсутствии directTarget она ничего не делает; nearby NPC не выбирается. Поэтому periodic owner pull остаётся выразимым прежним no-op, а `on_expire` может иметь цель у proximity missile. Сетевая authority и executor не меняются.

`pull_on_event` теперь предлагает только NPC modes `target_to_owner` и `target_to_entity`; radius остаётся обязательным, поскольку используется fallback-поиском при отсутствии active directTarget. `target_to_entity` сохраняет прежнее назначение event position, которое на прямом hit может совпасть с центром NPC. Эта категория не добавляет новое назначение source projectile center.

## Радиусы в tiles на точной решётке

| Capability / Author leaf | Domain | Прежний integer wire |
|---|---|---|
| `damage_area_on_event.radiusTiles` | `0.5..48`, шаг `1/16` | `radiusPx = n × 16`, integer `8..768` |
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

`child_projectile` получает count/spread от своего producer; root `free_projectile` не становится child из-за ссылки event. При `count>1` fan spread остаётся явным выбором. Radial/disk velocity по-прежнему несовместима с ненулевым fan spread: допустимый пропуск удовлетворяет exact zero, но present nonzero не стирается. У обычного движущегося projectile с `tileCollide=true` bounce count обязателен: N контактов отражаются, следующий убивает. Старые return opcodes сохраняют прежний early-return branch; это не общее правило новых return primitives. Пустой ReturnTrigger невалиден: должны быть выбраны хотя бы время, расстояние, release или tile contact.

Единственные варианты `arrival.action=kill` и `manaSustain.cadence=held_item_use_time` выбраны точным `fn` и материализуются Lowery, а не повторяются обязательными source-полями. Это не нейтраль `kill`: смысл выбранной операции явно описан её карточкой. Native wire сохраняет оба discriminators.

Compiler не переписывает Author: каждый разрешённый пропуск получает `declared_neutral_omission` receipt. Audit заново проверяет контекст и exact output/value по Author, а при его отсутствии — по доступным final-wire discriminator/kind. Source-free proof не удостоверяет отсутствующий Author. Fn-selected технические literals, включая executor identity и activation flags, также требуют точного значения и уникального покрытия; согласованная подмена значения вместе с receipt не доказывает его правильность.

Repair сохраняет принятое отсутствие frozen. Разрешённое изменение контекста может открыть только leaf, который действительно стал обязательным; оно не разрешает заполнить остальные отсутствующие side controls или поменять валидные siblings.

<a id="composable-motion"></a>
## Композиция движения вместо составного controller

Новая модель не выбирает bundled «flail», «phase», «sine homing» или «front hand attack». Она независимо выбирает исполняемые операции из [живого registry inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md):

| Решение | Независимые операции |
|---|---|
| Направление, привязка, рука и вылет | `set_projectile_aim`, `attach_projectile`, `set_front_arm_pose`, `set_projectile_reach_curve` |
| Траектория и steering | `move_straight`, `orbit_projectile`, `seek_projectile`; существующие turn/speed/homing modifiers |
| Ускорение, затухание и колебание | `accelerate_projectile_vertical`, `multiply_projectile_velocity`, `oscillate_projectile_velocity` |
| Начало возврата, достижение владельца, proximity | `set_projectile_return_trigger`, `set_projectile_arrival`, `set_projectile_proximity_action` |
| Вращение и видимость | `set_projectile_rotation`, `set_projectile_opacity`, `add_projectile_visual_scale`; существующие visual/hitbox curves остаются раздельными |
| Input/liveness, накопление, release и контакт | `set_projectile_owner_control`, `accumulate_projectile_charge`, `apply_projectile_charge_release`, `gate_projectile_contact` |
| Beam/lash geometry и независимое поддержание | `set_projectile_beam_geometry`, `set_projectile_beam_ramp`, `set_projectile_lash_geometry`, `sustain_projectile_mana` |

`target_and_fire` уже независим от движения и не заменяется новым контроллером. Поиск цели для firing не выбирает цель steering. Старый velocity-lerp seek не объявлен эквивалентом capped-angular homing: это разные явно выбранные законы.

Optional `window` задаёт конечные native phases `always`, `charging`, `released`, `outbound`, `returning`, а не произвольную state graph. Форма `{phase}` означает всю фазу без выдуманного максимального duration. Timing задаётся целиком: `clock`, `startDelaySeconds`, `durationSeconds`; частичная группа и present null отвергаются. `released` — latch, который может пересекаться с `returning`, а не отдельная взаимоисключающая стадия. Relative clock не активен до соответствующего release/return. Отсутствие window не добавляет фазу или таймер.

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
