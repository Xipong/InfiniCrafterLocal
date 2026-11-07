# Луч: геометрия, прогрев и поддержание

Author задаёт независимые `beam_geometry`, optional `beam_geometry.ramp`, `sustain_mana` и `set_owner_control`. `set_aim` предоставляет мировую ось. Никакая из этих операций не выбирается по DamageClass, имени или VFX. Полная композиция и окна — [Projectile Author](PROJECTILE_AUTHOR_API_RU.md).

## Геометрия и прогрев

`beam_geometry` задаёт `length` и `widthBlocks` в мировых блоках, явный `raycastTiles` и optional `startOffsetBlocks`. Offset сдвигает начало линии вдоль оси, но не тело, reach или размер PNG. Нулевой offset начинает линию в центре тела.

Optional `ramp` содержит `warmupSeconds`, `initialDamageMultiplier`, `initialWidthMultiplier`, `damageStartProgress`. Initial multipliers 0.01…1 линейно достигают 1; progress threshold 0…1 включителен. Объявленные нейтрали — единичные множители и `damageStartProgress=0`. Отсутствие `ramp` не создаёт прогрев. Нулевой warmup сразу даёт полный progress.

Урон меняет `NPC.HitModifiers.SourceDamage`, а не `Projectile.damage`. База — фактический native spawn damage; defense, crit и native rounding идут после modifier. `live_parent` у child-spawn читает буквальное поле Projectile.damage и не получает per-target modifier повторно.

`GetChannelBeamGeometry` даёт общие start/end/width для collision, `runtime_geometry` и VFX `texturedPath source=beam`. При `raycastTiles=true` берётся минимум трёх `Collision.LaserScan` samples без temporal smoothing. Нулевая длина не создаёт collision segment; nonfinite ответ native API не заменяется полной длиной. Это bounded sample, не доказательство очистки каждого пикселя объёма.

`damage.ownerHitCheck` проверяет путь owner→NPC, `collision.tileCollide` — тело projectile; оба независимы от raycast. PNG рисуется по выбранному Visual contract, не растягивается автоматически вдоль beam. VFX path width остаётся отдельным декоративным выбором.

## Мана и authority

`sustain_mana` явно включает повторный native `Player.CheckMana` с текущим HeldItem по cadence его `useTime`; исходную оплату делает native item use. Требуется явный owner control. Каждый физический projectile имеет собственный таймер; дополнительные AI updates в том же world tick платёж не повторяют.

Вызов `CheckMana(owner.HeldItem, amount:-1, pay:true, blockQuickMana:false)` сохраняет native cost modifiers и missing-mana effects. Отказ завершает projectile. Guards удержания/channel/animation/liveness выбирает `set_owner_control`, а не сама геометрия луча. Только owner/SP исполняет оплату; remote/server не создают вторую транзакцию. Hydration не перезапускает уже идущий таймер.

## Контракт и проверка

Registry и exact nested-path receipts связывают Author с typed `beamGeometry/beamRamp/manaSustain`; общего controller parameter bag нет. Present null, wrong type/domain и missing dependency отвергаются. Frozen Repair неверной ширины не открывает mana, raycast, соседний multiplier или принятое отсутствие `ramp`.

Owners: `capability_registry.py`, `GeneratedProjectile.ComposableMotion.Lifecycle.cs`, `GeneratedProjectile.RuntimeEvents.cs`; native checks — `EngineRuntimeChecks.ChannelBeam.cs` и composable checks. Проверяй реальный compiler→DTO→consumer, включая geometry, damage, CheckMana, hydration и refusal. Source scan не доказывает исполнение. Команды и уровни — [TESTING](../../development/TESTING_RU.md).
