# Projectile Author: композиция, единицы и исполнение

Канонические формы — [`capability_registry.py`](../../../generator/infini_local/core/runtime_authoring/capability_registry.py). Schema, prompt cards, validator, Repair, compiler и receipts читают один registry. Полный набор полей — [generated inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), единицы — [MODEL_FACING_UNITS](../authoring/MODEL_FACING_UNITS_RU.md).

<a id="composable-motion"></a>
## Композиция движения

Author выбирает независимые компоненты, а не готовое семейство оружия:

| Решение | Текущие операции |
|---|---|
| Ось, привязка и рука | `set_aim`, `attach`, `front_arm_pose`; дополнительный вылет — `attach.reachCurve` |
| Полёт и наведение | `move_straight`, `orbit`, `seek`, `turn_velocity`, `homing`, `scale_velocity` |
| Ускорение и колебание | `accelerate_y`, `oscillate_velocity` |
| Возврат, достижение владельца, proximity | `return_when`, `kill_on_arrival`, `proximity_action` |
| Поворот и видимость | `rotate_sprite`, `set_opacity`, `add_sprite_scale`, `sprite_scale_curve` |
| Input/liveness, заряд и контакт | `set_owner_control`, `charge` с optional `releaseEffect`, `gate_contact` |
| Геометрия и поддержание | `beam_geometry` с optional `ramp`, `lash_geometry`, `sustain_mana` |

`target_and_fire` независимо выбирает цель и выпускает явно указанную child entity. Его firing target не выбирает автоматически steering target. `seek` (velocity lerp) и `homing` (ограниченный угловой поворот) — разные законы.

Attachment не создаёт owner control, lifetime, channel, arm pose или collision policy. `front_arm_pose` пишет позу; только отдельная привязка перемещает тело. `reachCurve` перемещает реальный body center и collision, не только рисунок. Несовместимые владельцы позиции отвергаются, а не разрешаются порядком calls. Always-active attachment и lash требуют `tileCollide=false`; ограниченная окном привязка допускает отдельный free-flight interval.

## Lifetime, spawn и immunity

`projectile_lifetime.lifetimeSeconds` проецируется в целое `lifetimeTicks` с диапазоном **1…36000 world ticks**. Конкретные Author bounds и округление принадлежат registry. При Configure world ticks переводятся в AI updates через `updatesPerTick`; activation delay добавляется отдельно. Native sentry budget может завершить снаряд раньше.

`charge` только накапливает заряд и фиксирует release. Lifetime при зарядке приостанавливается лишь при явном `charge.releaseEffect.pauseLifetimeWhileCharging=true`. Обычная lifetime, modifier clocks и active age — разные часы.

`spawn.position` задаётся одной закрытой формой:

```json
{"at":"activation_origin"}
```

```json
{"above":"cursor","heightTiles":8,"activationDelay":0.25}
```

Anchors: `activation_origin`, `owner_center`, `cursor`, `ground_at_cursor`, `native_resting_spot`. Последний вызывает native resting-spot geometry, но не включает sentry lifecycle. Вертикальный сдвиг предшествует расчёту aim, `offsetBlocks` применяется после него. Ожидающий projectile занимает live slot, не движется и не наносит контактный урон; `on_spawn` происходит на первом активном update. Delay события — отдельный scheduler clock.

| Author `projectile_collision` | Native wire / смысл |
|---|---|
| `immunity:"owner_shared"` | Общий owner immunity; local cooldown wire — технический `-1`, engine использует owner lane |
| `immunity:"once_per_npc"` | Local immunity с `localNpcHitCooldownTicks=-1` |
| `immunity:{"localCooldown":n}` | Integer 0…600 сырых engine counts, не длительность в секундах |
| `updatesPerTick:n` | Integer 1…6 → `extraUpdates=n-1` |

`pierce=-1`, lifetime и immunity независимы. Ноль local cooldown не заменяется другим значением. Физические скорости lowerer пересчитывает по N данного target; безразмерные per-update коэффициенты применяются на каждом update и не превращаются в world rates.

## Events и тяга

`when:"on_hit"` выбирает реальное событие; `when:{"everySeconds":0.2}` — периодический producer. Optional `delay` задаёт секунды scheduler delay. `on_hit` требует попадания, proximity expiry им не является; `on_expire` и `on_kill` имеют разных producers.

[Event contract](../authoring/AUTHOR_EVENT_DOMAINS_RU.md) описывает `damage_nearby_on_event` и четыре режима `pull_on_event`. AoE использует один event center и nearest ordering, не цепь физических снарядов. Для `owner_to_target`/`both` нужна действительная direct hit target; при её утрате новая цель не выбирается. Для NPC-only режимов radius-search — явно объявленная семантика.

<a id="только-объявленные-неисполняемые-поля-можно-опустить"></a>
## Только объявленные технические значения можно опустить

Разрешение принадлежит `ParamSpec.default=neutral` и точному omission condition. Present null/неверный тип не становится default. В полном Author допустимый пропуск получает `declared_neutral_omission` receipt после проверки композиции; в Repair пропуск означает **не менять**.

- `spawn.count` можно опустить только у `child_projectile`: producer задаёт multiplicity.
- `spawn.spreadRadians` — у child либо при exact `count=1`; у `spawn_on_event` — при exact `count=1`.
- `projectile_collision.bounceCount` — при `tileCollide=false`. Возврат не создаёт скрытого исключения этого правила.
- Offset, guard flags и multipliers опциональны только по registry; пустой `set_owner_control` или `return_when` остаётся ошибкой.
- `kill_on_arrival` и `sustain_mana` выбирают свои единственные technical discriminators точным `fn`, а не дополнительным model choice.

Native компоненты `beamRamp`, `reach`, `chargeRelease` остаются отдельными consumers, но Author задаёт их **вложенными свойствами** `beam_geometry.ramp`, `attach.reachCurve`, `charge.releaseEffect`. Отсутствующий объект не создаётся. Присутствующий `releaseEffect` с единичными множителями всё равно задаёт `launchSpeed`; он не равен отсутствующему эффекту.

## Окна и порядок

`window` выбирает фазу `always`, `charging`, `released`, `outbound`, `returning`. Форма `{phase}` означает всю фазу; timing-группа целиком задаёт `clock`, `startDelay`, `duration` в секундах. Частичная группа и present null отвергаются. `released` может пересекаться с `returning`. Relative clocks начинаются только после своего latch; `charging/released/since_release` требуют `charge`, `returning/since_return` — `return_when`.

`turn_velocity`, `homing`, `attract_npcs` могут опустить всю timing-группу как объявленное `window={phase:"always"}`. Явная полная пара start/duration и окно действуют как пересечение. Native wire обязан содержать материализованный timing contract. Кривые pose/reach/scale/hitbox описывают интерполяцию и не заменяются omission правилами gate.

Интервал полуоткрытый и включает первый исполняемый subupdate. `scale_velocity` выполняется после turn и до homing: обязательный `scalePerUpdate` 0…1.2, optional `maxSpeed` в блоках/с. Отсутствующий cap действительно отсутствует. Допустим один вызов на всё время либо до двух с доказуемо непересекающимися окнами; порядок calls не разрешает overlap.

`oscillate_velocity` явно выбирает `angular_sine` либо `lateral_velocity_sine`. Для lateral при мировой скорости S, амплитуде B, фазе q и N updates поворот равен `atan((B/S)·sin(q))/N`; делится угол после atan. Нулевая скорость остаётся нулевой. Фаза использует общий active age: закрытие окна не перезапускает синус и не выпрямляет скорость. Это дискретное интегрирование, не обещание одинаковой траектории при любом N.

## Wire и проверка

Author/Repair, strict wire и C# исполняют только текущую композицию. Поддержка старых bundled opcodes или predecessor receipts не требуется для нейтральных omissions и точных aliases текущего языка. Общая ломающая граница — [обновление](../../user/UPDATING_RU.md).

Проверяй registry/provider → validator → compiler receipts → strict wire → C# DTO/executor. Основные owners: `test_composable_motion_*`, `test_motion_lowering_*`, `test_motion_repair_visibility.py`, `test_motion_presentation_handoffs.py`, `EngineRuntimeChecks.ComposableMotion*.cs`. Native CPU execution, игра, GPU и MP — разные уровни; команды — [TESTING](../../development/TESTING_RU.md).
