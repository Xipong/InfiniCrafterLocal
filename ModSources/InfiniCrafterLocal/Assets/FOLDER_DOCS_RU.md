# Assets

Static tModLoader assets bundled with the mod.

Files here include base textures such as `GeneratedItem.png`, generated armor placeholder sprites and `GeneratedProjectile.png`.

`InfiniCore.png` is the original Forge Heart icon: a 48×1200 RGBA vertical atlas, 24 frames with 48px artwork plus 2 transparent padding rows per cell. `InfiniCore.SetStaticDefaults` registers the native `DrawAnimationVertical(5, 24)` and `AnimatesAsSoul` presentation flag; the loop lasts 120 ticks (2 seconds). Inventory/world animation changes no crafting, recipe or item-consumption mechanics.

Actual generated item/projectile PNGs are runtime files loaded by `RuntimeSpriteCache` and synchronized via `GeneratedAssetSyncService`, not compiled into this folder.
