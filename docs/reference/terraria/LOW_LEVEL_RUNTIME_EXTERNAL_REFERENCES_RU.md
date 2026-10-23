# Runtime references — external patterns, не локальная authority

[Standardization boundary](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) · [Source owners](../../development/CODE_MAP_RU.md) · [Current proof limits](../../development/architecture/ARCHITECTURE_RU.md#runtime-trust)

<a id="version"></a>
## Версионная граница

Проект объявляет stable tModLoader/.NET 8. Pattern references ниже — official stable docs и ExampleMod/Calamity `1.4.4`, не development/1.4.5. Точный patch/наличие DLL/build result определяются **конкретной проверкой и references**, не этим статическим обзором. Старое «локальной installation нет» было статусом исходного прохода; поздние [headless records](../../archive/HISTORY_RU.md#typed) нельзя переименовывать в current game/MP proof.

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

Item/use/alternate/tool/placeable/equipment → ModItem; attached/channel/beam → held-projectile/beam patterns; flail/yoyo/whip → bounded custom AI; child/events/net → hooks + extra AI; collision/AoE → exact collision/event consumers. Последняя группа **не** blanket server collision proof: owner-hit отдельно использует [vanilla owner trust](../../development/architecture/ARCHITECTURE_RU.md#runtime-trust).

Внешний пример не расширяет executable surface. Mapping/units/ranges/exclusions принадлежат [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#boundary), finite aliases/lowerings — [generated Lowery](../generated/LOWERY_RU.md), доказанный новый adapter — [vertical slice](../../development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md#vertical-slice).

## Проверенные NPC-hit статусы родителей

`Item.buffType` описывает buff от использования предмета, а не дебафф попадания
снаряда. Нулевой `buffType` поэтому не доказывает отсутствие on-hit эффекта.
Native `Projectile.StatusNPC` вызывается из hit path отдельно от `SetDefaults`:
[официальный patch ветки 1.4.4](https://github.com/tModLoader/tModLoader/blob/1.4.4/patches/tModLoader/Terraria/Projectile.cs.patch).

`directProjectileRaw` / `effectiveProjectileRaw.onHitStatusReference` передают
узкую read-only справку, только если SHA256 IL метода совпадает с проверенным.
Она сохраняется целиком в Author parent dossier, включая scope и certificate.
Тот же canonical capture используется для `/infinidump`: и внутри item projectile
snapshot, и в отдельном projectile roster. Старые dumps не дополняются догадками.
Это не автоматическое наследование эффекта и не маршрутизация generated AI.

Проверен официальный [tML v2026.08.3.0](https://github.com/tModLoader/tModLoader/releases/tag/v2026.08.3.0):

- ZIP SHA256: `61e865f3702b12ce4a26c5a90b9de99a12c65ffc228455eb3390ce54af1eab15`.
- `Projectile.StatusNPC` IL SHA256: `0409d6e8aeb6c41acc5454f7f818368639b041341d9eafff9dd1336cd42e2cf7`.
- `GoldenShowerFriendly` → `BuffID.Ichor`, запрос на **600 ticks**.
- `ShadowFlameKnife` → `BuffID.ShadowFlame`, `Main.rand.Next(60, 180)`:
  равномерный целый срок **60–179 ticks**, не фиксированные 10 секунд.

Независимо проверен также [tML v2026.06.3.6](https://github.com/tModLoader/tModLoader/releases/tag/v2026.06.3.6),
упомянутый в контрактах установленной среды. ZIP SHA256
`de501c82d25e8485a4c6174c64f8bcd6f4948e9fc4ee3d963745a7186e526674`,
`StatusNPC` IL SHA256 `ea30212888353eea100edc863b651f8ee1555b4f39891eb2de442ba3339dcb79`:
те же две проверенные ветки `AddBuff` и диапазоны; оба certificate разрешены.

IDs берутся из загруженных native constants; имя предмета, tooltip и `aiStyle`
не выбирают статус. Другой IL, неизвестный тип или `ModProjectile` → справка
отсутствует, а не угадывается. Это vanilla NPC-hit **запрос** `AddBuff`:
иммунитет NPC, другие моды, PvP/player hits и child AI не покрыты. Во время
крафта hit hooks не запускаются. Native regression отдельно вызывает настоящий
`StatusNPC` на изолированных тестовых NPC и сравнивает buff/duration с dossier.
