# Charge-release и sentry — finite runtime slices

Этот документ описывает два исполняемых вертикальных среза. Они не являются общей action/state-machine и не вводят вложенный `AttackSpec`.

## Charge-release

Canonical family: `charge_release`.

Authoring surface:

- существующий `fire_ranged_weapon(family=charge_release)`;
- существующий `cast_magic_weapon(family=charge_release)`;
- low-level `shoot_projectile(runtimeFamily=charge_release, delivery=shoot|cast|throw)`;
- `chargeTicks: 1..300`;
- `chargePowerMultiplier: 1..3`.

Owners:

- Python limits/conflicts: `LocalGenerator/infini_local/core/runtime_charge_release_policy.py`;
- lowering: `core/runtime_authoring/semantics.py`;
- final projection: `pipelines/combine_genome.py`, `pipelines/combine_gameplay.py`;
- C# item affordance: `Common/Models/GeneratedItemData.Apply.cs`, `Content/Items/GeneratedItem.cs`;
- C# executor: `Content/Projectiles/GeneratedProjectile.ChargeRelease.cs`;
- compact sync: `GeneratedProjectile.NetSync.cs`.

Lifecycle:

1. Item use создаёт один held root projectile.
2. Пока удерживается use button, root накапливает bounded charge и отслеживает aim.
3. При release root создаёт обычные authored primary projectiles.
4. Released projectile меняет family на `shoot|cast|throw`, поэтому не создаёт новый charge root.
5. On-hit/secondary/effect/VFX authored contract сохраняется у выпущенного projectile.
6. Root уничтожается после release или при invalid owner/death/CC/item switch.

Ограничения:

- vanilla ammo запрещено: ammo projectile не несёт Generated `AttackSpec`;
- charge влияет на damage и knockback до `chargePowerMultiplier`;
- это один линейный charge, без stage graph, custom curves и scripted release actions;
- один активный charge root на generated item.

## Sentry

Canonical function: `deploy_sentry`. Canonical runtime family: `sentry`.

Authoring surface:

- `placement: grounded|floating`;
- `attackIntervalTicks: 12..180`;
- `targetRangeTiles: 8..60`;
- `helperLifetimeTicks: 120..36000`;
- `shotCount: 1..4`;
- обычные exact projectile fields для sentry shot: speed, spread, movement, effect, onHit, shape, trail, impact;
- общий lifetime shot budget максимум 48.

Owners:

- Python limits/conflicts: `LocalGenerator/infini_local/core/runtime_sentry_policy.py`;
- engine-call lowering: `core/runtime_authoring/semantics.py`;
- item placement: `Content/Items/GeneratedItem.Sentry.cs`;
- root targeting/fire executor: `Content/Projectiles/GeneratedProjectile.Sentry.cs`;
- shared damage-class owner: `Common/Models/GeneratedDamageClassPolicy.cs`;
- compact sync: `GeneratedProjectile.NetSync.cs`.

Lifecycle:

1. Item marks itself `Item.sentry` and places root at cursor or Terraria resting spot.
2. Root marks itself `Projectile.sentry`, remains stationary and targets owner-assigned NPC first, then nearest visible NPC.
3. Только authoritative owner/server path создаёт shots.
4. Каждый shot становится ordinary `runtimeFamily=shoot`; он не наследует sentry lifecycle.
5. Все shots расходуют один lifetime child budget; после исчерпания root завершается.
6. `player.UpdateMaxTurrets()` применяет обычный Terraria sentry limit.

Ограничения shared projectile type:

`GeneratedProjectile` обслуживает все generated projectile families одним ModProjectile type. Поэтому нельзя глобально включить:

- `ProjectileID.Sets.SentryShot[Type]`;
- `ProjectileID.Sets.MinionTargetingFeature[Type]`.

Иначе эти static sets применятся ко всем generated projectiles. Текущий sentry имеет честный item/root lifecycle, placement, targeting, maxTurrets и bounded shots, но не обещает все accessory/static-set synergies vanilla sentry. Для полного набора таких synergies понадобится отдельный dedicated ModProjectile type, а не условная ветка в shared type.

## Запрещённые расширения

- не объединять charge и sentry в universal state-machine;
- не добавлять вложенный LLM-authored AttackSpec для sentry shot;
- не выбирать эти mechanics по name/tooltip/projectile prose;
- не добавлять legacy aliases;
- не копировать limits в compiler/C# consumers — менять owner policy и cross-layer tests.

## Regression proof

Основной тест: `LocalGenerator/tests/test_v15_charge_release_sentry_contract.py`. Он проверяет compiler, provenance, final gameplay projection, DTO fields, net sync, C# owner paths, release sound, damage-class parity и отсутствие recursive sentry roots.
