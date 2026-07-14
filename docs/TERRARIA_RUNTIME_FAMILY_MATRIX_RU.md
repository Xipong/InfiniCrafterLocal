# Матрица Terraria-native lifecycle для generated runtime

Дата проверки: 2026-07-13

Эта матрица описывает фактически исполняемый конечный runtime, а не fantasy/tooltip. Источник executable intent — `runtimePlan.engineCalls`; Python компилирует только известные поля, C# принимает только канонический `runtimeFamily` и конечный movement opcode.

## Зафиксированные источники

- `tModLoader/tModLoader`, ExampleMod stable/1.4.4: spear, advanced flail, yoyo, whip, Last Prism holdout/beam, sentry.
- `codingwatching/terraria-1.4.4.5-source-code`, commit `69b5a80eab473dca8a08f491bf7a090d9e7f22dc`: vanilla `Projectile.cs`, в частности boomerang `AI_003_Flying`.
- `CalamityTeam/CalamityModPublic`, commit `2e10cae1c84fd271e28db07b6da5b4d55f2f2996`: boomerang/chakram/harpoon/black-hole comparisons. Только поведенческая сверка; код не копируется.
- `Fargowilta/FargowiltasSouls`, commit `226fadeadbe3422785a7708ba2cdf53bd8548c00`: flail/yoyo/whip/sentry comparisons.

Локальные sparse-копии для повторного аудита находятся в `/tmp/infini-native-audit/`. Они не являются build dependencies.

## Канонические runtime families

| Runtime family | Item/projectile lifecycle | Позиция и collision | Authority/sync | Terraria-native статус и ограничения |
|---|---|---|---|---|
| `none` | Не создаёт специальный generated projectile executor. | Обычная item-side логика. | Специального projectile state нет. | Без gameplay promise о projectile-механике. |
| `swing` | Melee item body остаётся активным; projectile не владеет использованием. | Terraria item melee hitbox; отдельные authored child/overhead эффекты возможны только явным call. | Обычная item authority. | Starfury-style carrier сохраняет item body, а не превращается в невидимый projectile-only предмет. |
| `thrust` | Held projectile живёт пока идёт `itemAnimation`; `heldProj` и `itemTime` поддерживаются. | `ShouldUpdatePosition=false`; executor сам ставит `Projectile.Center`; line collision по owner-mounted extension/retraction. | Направление приходит со spawn/sync; gameplay position выводится из owner state. | Соответствует главному `ExampleSpearProjectile` invariant. Нет произвольного vanilla `AIType` на общем generated type. |
| `returning` | Outbound → return по первому outbound NPC hit, tile collision или timeout; owner catch завершает projectile. | Movement только 5/14; на return `tileCollide=false`, homing к owner. `penetrate=-1`; return-path damage остаётся активным. | `_returningPhase` синхронизируется; переход ставит `netUpdate`. Pull имеет отдельную authority по `pullMode`. | Vanilla boomerang invariant: первый hit защёлкивает return, но не является общим hit budget. |
| `flail` | Held tether; owner validity, channel release/timeout/range/tile hit переводят в retract; owner catch завершает. | Head использует обычный hitbox; chain — presentation tether; outbound использует tile collision, retract отключает. | Owner lifecycle определяется синхронизированным player/channel state; projectile state синхронизируется обычным net update. | Finite simple flail, не обещает полную advanced state machine (spin/drop/ricochet). |
| `yoyo` | Held hover до release/expiry/CC, затем ручной retract и owner catch. | `ShouldUpdatePosition=false`; cursor distance сохраняется до max range; manual `TileCollision`; executor меняет `Center` в hover и return. | Owner пишет target в `ai[0]/ai[1]` и ставит `netUpdate`; remote использует синхронизированную цель. | Per-instance реализация вместо static `ProjectileID.Sets.Yoyos*`, потому что generated projectiles имеют общий type. |
| `whip` | Один lash по item animation; затем kill; `localNPCHitCooldown=-1`. | `ShouldUpdatePosition=false`; 10–24 control points; collision и drawing используют один список сегментов. | Направление берётся из spawn projectile; gameplay state не хранится в несинхронизированном `localAI`. | Per-instance whip geometry. Static `IsAWhip[Type]` недоступен выборочно для общего generated type, поэтому vanilla tag/flask integration не заявляется. |
| `shoot` | Обычный конечный projectile shot. | Movement выбирается из кодов 0–15; обычное position integration кроме специальных movement implementation. | Projectile owner создаёт/sync-ит shot; server owns NPC/world side effects. | Не подразумевает gun-specific механику без authored fields. |
| `cast` | Обычный magic projectile shot. | Те же конечные movement executors 0–15. | Как у `shoot`; mana принадлежит item/beam contract, а не fantasy text. | `cast` не означает channel beam автоматически. |
| `beam` | Held channel loop; kill при release/death/noItems/CC; периодическая authored mana payment. | `ShouldUpdatePosition=false`; owner-mounted origin, `LaserScan`, wall-bounded length, line collision и `CanHitLine`. | Owner-local aim ставит `netUpdate`; beam length синхронизируется; damage cadence через local immunity. | Last-Prism-like invariant в одном finite held executor; не произвольный shader/beam language. |
| `charge_release` | Наносящий 0 damage holdout копит bounded charge; release один раз создаёт ordinary authored shots и умирает. | `ShouldUpdatePosition=false`; holdout у руки, released shots возвращаются в обычный family executor. | Owner-authoritative channel/aim; spawn выполняется один раз под projectile gameplay authority. | Полный terminal release path обязателен. Charge motif без executor остаётся visual/partial. |
| `overhead_barrage` | Неповреждающий target marker ждёт `delayTicks`, один раз создаёт bounded authored children сверху и умирает. | Stationary, `tileCollide=false`, marker не наносит contact damage. | Child spawn выполняется только projectile gameplay authority. | Это конечный marker→delay→spawn executor, не generic event/state framework. Swing carrier может сохранить item melee body. |
| `throw` | Обычный authored thrown projectile; item sprite может быть projectile body. | Movement 0–15; returning поведение появляется только при family `returning`, не из слова «throw». | Как у ordinary projectile. | Не является скрытым router к boomerang/harpoon. |
| `summon` | Одноразовый summon-damage projectile/helper. | Movement 0–15 и обычный bounded lifetime. | Как ordinary projectile. | **Не minion:** нет minion slots, persistent follow AI или minion lifecycle. Tooltip не должен обещать постоянного прислужника. |
| `sentry` | Stationary root с authored lifetime; item spawn вызывает `UpdateMaxTurrets`; root создаёт только ordinary child shots. | Grounded/floating placement; root `friendly=false`, `sentry=true`, `netImportant=true`; target требует range и LOS. | Owner/projectile gameplay authority создаёт shots; designated minion target имеет приоритет. | Соответствует базовым ExampleSentry invariants; child не наследует sentry lifecycle. |

## Movement opcodes

| Code | Movement | Исполняемая геометрия/lifecycle | Ограничения |
|---:|---|---|---|
| 0 | `straight` | Terraria position integration с постоянной velocity. | Нет скрытого homing/return. |
| 1 | `slow_homing` | Плавный поворот к ближайшей chaseable цели в authored range. | Homing strength/range hard-clamped. |
| 2 | `gravity_arc` | Постепенное увеличение Y velocity. | Обычный tile collision по authored contract. |
| 3 | `drift` | Velocity damping. | Не orbit/owner tether. |
| 4 | `orbit` | Owner-anchored orbit; стартовый radius ограничен `RangeTiles`. | Не persistent minion; lifetime остаётся bounded. |
| 5 | `boomerang` | Outbound delay/hit/tile → return homing → owner catch. | Допустим только с `runtimeFamily=returning`; return hits разрешены. |
| 6 | `bounce` | Gravity + bounded `OnTileCollide` rebound budget. | Bounce count конечный. |
| 7 | `sine_homing` | Forward motion с sinusoidal lateral component и bounded homing. | Не меняет family. |
| 8 | `phase` | Phase drift с отключённым обычным tile collision. | Не означает teleport/player movement. |
| 9 | `accelerate` | Bounded velocity acceleration. | Speed sanitization остаётся общей. |
| 10 | `spiral` | Вращающийся outward trajectory. | Bounded lifetime. |
| 11 | `vortex_orb` | Damped orb/vortex motion. | Visual vortex не создаёт pull без explicit field. |
| 12 | `blackhole_pull` | Stationary/damped field; pull uses authored `PullStrength`, `PullMode=target_to_projectile`, `RangeTiles`. | NPC pull server-authoritative; player-pull modes are not accepted by this movement. |
| 13 | `proximity_missile` | Ищет близкую цель и один раз выполняет bounded child/proc path. | Child count/depth capped; не бесконечный spawner. |
| 14 | `returning_glaive` | Та же native outbound→return структура, с glaive rotation/return settings. | Допустим только с `runtimeFamily=returning`; первый outbound hit запускает return. |
| 15 | `expanding_wave` | Projectile scale растёт; damage hitbox увеличивается по тому же scale. | Visual и damage geometry не расходятся; max scale hard-clamped. |
| 16 | `flail_tether` | Dedicated finite flail executor. | Допустим только с `runtimeFamily=flail`. |
| 17 | `yoyo_hover` | Dedicated owner-target hover/retract executor. | Допустим только с `runtimeFamily=yoyo`. |
| 18 | `whip_lash` | Dedicated control-point lash executor. | Допустим только с `runtimeFamily=whip`. |

## Damage, immunity и hit promises

- `Pierce` означает общий hit budget только для обычных projectiles. `returning` использует `penetrate=-1`, а first outbound hit — phase transition, не расходуемый глобальный latch.
- Whip использует `usesLocalNPCImmunity=true`, `localNPCHitCooldown=-1`: один hit по NPC за lash.
- Beam использует authored local immunity cooldown как реальную repeated-hit cadence.
- Flail/yoyo/обычные projectiles используют clamped positive local cooldown, если специальный native invariant не требует `-1`.
- Expanding-wave hitbox масштабируется вместе с rendered scale.
- Любой gameplay claim со статусом `executable` должен иметь разрешившиеся `backingRefs`; поле `backing` является только пояснением.

## Multiplayer authority

- NPC velocity, NPC debuffs и world-side effects: server-authoritative.
- Owner aim, player velocity/pull и безопасный teleport: owning player authority с требуемой sync операцией.
- Child projectile spawn: `ShouldRunProjectileGameplay(Projectile)` и bounded child policy.
- Presentation/VFX: client-side; visual text не выбирает gameplay.
- Gameplay state, который не входит в стандартные projectile fields, передаётся через `SendExtraAI/ReceiveExtraAI`; `localAI` не считается сетевым контрактом.

## Честные ограничения

1. Один общий `GeneratedProjectile` type не может безопасно включать static `IsAWhip`/`Yoyos*` только для отдельных instances. Поэтому реализована per-instance геометрия, но не заявляются недоступные static vanilla integrations.
2. `summon` — temporary helper/projectile, не minion.
3. Finite flail — не полная advanced flail state machine.
4. Source/build тесты не заменяют живой Terraria SP/MP playtest: feel, owner catch и remote interpolation должны быть подтверждены пользователем в игре.
