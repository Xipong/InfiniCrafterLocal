# Runtime references — external patterns, не локальная authority

[Standardization boundary](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) · [Source owners](../PROJECT_MAP_RU.md) · [Current proof limits](../PROJECT_ARCHITECTURE_RU.md#runtime-trust)

<a id="version"></a>
## Версионная граница

Проект объявляет stable tModLoader/.NET 8. Pattern references ниже — official stable docs и ExampleMod/Calamity `1.4.4`, не development/1.4.5. Точный patch/наличие DLL/build result определяются **конкретной проверкой и references**, не этим статическим обзором. Старое «локальной installation нет» было статусом исходного прохода; поздние [headless records](HISTORY_RU.md#typed) нельзя переименовывать в current game/MP proof.

<a id="official"></a>
## Official API и ExampleMod

- [ModItem stable](https://docs.tmodloader.net/docs/stable/class_mod_item.html): AltFunctionUse/CanUseItem/ConsumeItem/UseItem/Shoot/HoldoutOffset — разные input/lifecycle hooks; CanUseItem не место для mutation.
- [ModProjectile stable](https://docs.tmodloader.net/docs/stable/class_mod_projectile.html): AI/Colliding/OnTileCollide/OnHitNPC/SendExtraAI/ReceiveExtraAI — movement, collision, events и необходимое instance net state отдельно.
- [Projectile API](https://docs.tmodloader.net/docs/stable/class_projectile.html): timeLeft/penetrate/tileCollide/immunity/extraUpdates; NewProjectileDirect для created-instance hydrate. Defaults не скрытые design choices.
- [ItemUseStyleID](https://docs.tmodloader.net/docs/stable/class_item_use_style_i_d.html), [DamageClass](https://docs.tmodloader.net/docs/stable/class_damage_class.html): exact finite mappings, не loose names. ModType.FullName + ModContent.TryFind<T> — exact registered content; AmmoID/PickAmmo и loader counts объясняют [ammo/loaded-ID exclusions](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#ammo-healing).
- [Stable releases](https://github.com/tModLoader/tModLoader/releases?q=stable) задают release line, не pinned current patch.

Все ExampleMod paths ниже относительны [tModLoader/1.4.4/ExampleMod](https://github.com/tModLoader/tModLoader/tree/1.4.4/ExampleMod):

| Path / method | Pattern |
|---|---|
| `Common/GlobalProjectiles/ExampleProjectileNetSync.cs` SendExtraAI/ReceiveExtraAI | Только нужное instance state, симметричный wire shape |
| `Content/Projectiles/ExampleAdvancedFlailProjectile.cs` AI/collision | Reusable tether/return controller, не whole-weapon macro |
| `ExampleYoyoProjectile.cs`, `ExampleWhipProjectile.cs` в Content/Projectiles | Owner-relative hover/return; bounded lash points/collision |
| `Content/Items/Weapons/ExampleHeldProjectileWeapon.cs` + projectile | Explicit owner-attached entity, channel, one held instance и aim sync |
| `Content/Items/Weapons/ExampleLastPrism.cs` | Beam controller/holdout lifecycle отделён от item identity |
| ExampleHamaxe / item value examples | Internal Item.axe ×5 tooltip; buyPrice/sellPrice helpers задают copper Item.value, не resale guarantee |

<a id="calamity"></a>
## Calamity reference и capability routing

[CalamityModPublic/1.4.4](https://github.com/CalamityTeam/CalamityModPublic/tree/1.4.4): `Projectiles/BaseProjectiles/BaseGunHoldoutProjectile.cs` (ManageHoldout/KillHoldoutLogic) — owner mouse aim, peers consume sync; `Projectiles/Ranged/AdamAcceleratorBeam.cs` (Colliding/length/scale) — bounded line collision и visual length lifecycle. Assets, dependencies и крупные blocks не копировались; это patterns, не runtime requirement.

Item/use/alternate/tool/placeable/equipment → ModItem; attached/channel/beam → held-projectile/beam patterns; flail/yoyo/whip → bounded custom AI; child/events/net → hooks + extra AI; collision/AoE → exact collision/event consumers. Последняя группа **не** blanket server collision proof: owner-hit отдельно использует [vanilla owner trust](../PROJECT_ARCHITECTURE_RU.md#runtime-trust).

Внешний пример не расширяет executable surface. Mapping/units/ranges/exclusions принадлежат [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#boundary), finite aliases/lowerings — [generated Lowery](../lowery.md), доказанный новый adapter — [vertical slice](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md#vertical-slice).
