# Внешние references низкоуровневого runtime

## Версия

Проект объявляет `<TmlVersion>stable</TmlVersion>` и .NET 8, но локальная tModLoader installation/DLL отсутствует, поэтому точный stable patch из build environment определить нельзя. API-паттерны проверены по официальной stable документации и ветке tModLoader/ExampleMod `1.4.4`; Calamity references — ветка `1.4.4`. Development/1.4.5 API не использовался.

## Официальная документация tModLoader

| source | path/class/method | использованный вывод |
|---|---|---|
| tModLoader docs stable | `ModItem.AltFunctionUse`, `CanUseItem`, `ConsumeItem`, `UseItem`, `Shoot`, `HoldoutOffset` | alternate input и item lifecycle — отдельные hooks; `CanUseItem` не должен иметь side effects |
| tModLoader docs stable | `ModProjectile.AI`, `Colliding`, `OnTileCollide`, `OnHitNPC`, `SendExtraAI`, `ReceiveExtraAI` | movement/collision/events/net state разделяются и могут быть bounded components |
| Terraria/tModLoader Item/Projectile API | item stats, `timeLeft`, `penetrate`, `tileCollide`, local immunity | units и hard clamps для DTO |

Документация: https://docs.tmodloader.net/docs/stable/class_mod_item.html и https://docs.tmodloader.net/docs/stable/class_mod_projectile.html

## Official ExampleMod 1.4.4

| repo/branch/path | class/method | использованный pattern |
|---|---|---|
| `tModLoader/tModLoader`, `1.4.4`, `ExampleMod/Common/GlobalProjectiles/ExampleProjectileNetSync.cs` | `SendExtraAI` / `ReceiveExtraAI` | отправлять только необходимое instance state и читать ровно тот же wire shape |
| `ExampleMod/Content/Projectiles/ExampleAdvancedFlailProjectile.cs` | state-driven `AI`, collision | tether/return как reusable movement controller, не whole weapon |
| `ExampleMod/Content/Projectiles/ExampleYoyoProjectile.cs` | yoyo hover/return state | owner-relative hover/return controller |
| `ExampleMod/Content/Projectiles/ExampleWhipProjectile.cs` | control points/collision | bounded lash geometry as controller |
| `ExampleMod/Content/Items/Weapons/ExampleHeldProjectileWeapon.cs` + projectile | channel, one held instance, owner aim sync | explicit owner-attached entity and input binding |
| `ExampleMod/Content/Items/Weapons/ExampleLastPrism.cs` | held channel/holdout check | beam controller separated from item identity |

Repository: https://github.com/tModLoader/tModLoader/tree/1.4.4/ExampleMod

## CalamityModPublic 1.4.4

| path | class/method | использованный pattern |
|---|---|---|
| `Projectiles/BaseProjectiles/BaseGunHoldoutProjectile.cs` | `ManageHoldout`, owner aim, `KillHoldoutLogic` | owner computes mouse aim; other peers consume synchronized projectile state; holdout lifecycle is reusable |
| `Projectiles/Ranged/AdamAcceleratorBeam.cs` | `Colliding`, beam length/scale lifecycle | beam line collision and visual length are bounded controller/collision concerns |

Repository: https://github.com/CalamityTeam/CalamityModPublic/tree/1.4.4

Calamity code использован только как reference: assets не копировались, зависимости не добавлялись, крупные блоки кода не переносились.

## Соответствие capability groups

- item/use/alternate/tool/placeable/equipment → `ModItem` hooks/fields;
- owner-attached/channel/beam → ExampleMod held projectiles + Calamity holdout/beam;
- flail/yoyo/whip → ExampleMod custom projectile AI patterns;
- child/event authority/net sync → projectile hooks + `SendExtraAI/ReceiveExtraAI`;
- collision/AoE → `Colliding`, `OnTileCollide`, explicit server-authoritative event actions.
## v0.4.241 Terraria-standardization references

| official source | применённое решение |
|---|---|
| tModLoader stable releases (`1.4.4-refs/heads/stable`) | проект продолжает ориентироваться на stable 1.4.4 API, а не на development/1.4.5 |
| `ItemUseStyleID` stable docs | Author tokens соответствуют точным константам; `DrinkOld`/`None` и свободные spellings не exposed |
| `DamageClass` stable docs | finite mapping для `Generic`, `Melee`, `MeleeNoSpeed`, `Ranged`, `Magic`, `Summon`, `SummonMeleeSpeed`; неизвестное fail closed |
| `Projectile` stable docs | `ignoreWater=false`, `extraUpdates=0`, local immunity semantics и другие defaults не подменяются скрыто |
| official ExampleHeldProjectileWeapon | advanced item animation/aim остаётся held projectile behavior; ammo category и spawned projectile type — разные поля/решения |
| `Projectile.NewProjectileDirect` stable API | generated spawn получает созданный instance напрямую и затем hydrate-ит authored entity spec |
| `ModType.FullName` + `ModContent.TryFind<T>` stable API | modded `DamageClass` адресуется только точным `ModName/ClassName`; loose search/fallback запрещены |
| `AmmoID`, `Item.ammo`, `Item.useAmmo`, `ItemLoader.PickAmmo` stable API | ammo-item identity отделена от ammo-consuming weapon pipeline; `Item.shoot`, `Item.shootSpeed`, damage и knockback являются отдельными входами PickAmmo |
| `RarityLoader`, `BuffLoader`, `TileLoader`, `WallLoader` | numeric loaded-content IDs проверяются против текущих loader counts, а не молча clamp-ятся |
| official ExampleMod `ExampleHamaxe` | `Item.axe` хранит внутреннее значение; tooltip показывает его ×5 |
| official ExampleMod item value examples | `Item.value` задаёт base/shop value; helper `Item.buyPrice`/`Item.sellPrice` лишь удобная запись copper value |

Подробная граница vanilla/custom зафиксирована в `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md`; полный alias inventory — в корневом `lowery.md`.
