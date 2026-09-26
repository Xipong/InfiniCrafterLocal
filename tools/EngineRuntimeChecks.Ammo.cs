using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem AmmoFixture(int category, int projectile, float speed)
    {
        var data = GeneratedItemData.Placeholder();
        data.Gameplay.AmmoCategory = category == AmmoID.Rocket ? "rocket"
            : category == AmmoID.Solution ? "solution"
            : category == AmmoID.Bullet ? "bullet"
            : throw new ArgumentException("Unexpected test category");
        data.Gameplay.AmmoProjectileId = projectile;
        data.Gameplay.AmmoShootSpeedPxPerTick = speed;
        data.RuntimeProgram.ItemUse.Configured = true;
        data.Gameplay.HealLife = 1;
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
            Id = "primary", Input = RuntimeInputKind.PrimaryUse,
            Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec {
                Action = new RuntimeBindingActionSpec {
                    Kind = RuntimeBindingAction.ApplyItemEffects,
                    TargetId = data.RuntimeProgram.ItemEntityId,
                },
            },
        } };
        var item = new Item { type = ItemID.MusketBall, stack = 10 };
        var generated = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
        data.ApplyToItem(item);
        return generated;
    }

    private static void GeneratedAmmoPickAmmoRejectsUnrelatedCategoryRewrites()
    {
        WithPlayer((player, _) => {
            var rocket = AmmoFixture(AmmoID.Rocket, 134, 2f);
            var weapon = new Item { useAmmo = AmmoID.Bullet };
            int type = 444;
            float speed = 8f, knockback = 3f;
            var damage = StatModifier.Default;
            // Another mod could opt into cross-category ammo. This narrow hook must
            // not interpret that choice as the vanilla rocket/solution offset path.
            ItemLoader.PickAmmo(weapon, rocket.Item, player, ref type, ref speed, ref damage, ref knockback);
            Equal(444, type, "mismatched weapon category remains untouched");
            Equal(8f, speed, "mismatched speed remains untouched");
            Equal(3f, knockback, "mismatched knockback remains untouched");
        });
    }

    private static void GeneratedAmmoNetworkAndSaveBoundaries()
    {
        WithPlayer((player, _) => {
            var ammo = AmmoFixture(AmmoID.Rocket, 134, 2.5f);
            var network = GeneratedItemData.FromJson(ammo.Data.ToNetworkJson())
                ?? throw new InvalidOperationException("network ammo DTO rejected");
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(ammo, network);
            network.ApplyToItem(ammo.Item);
            Equal(134, ammo.Item.shoot, "network hydrated ammo projectile");
            Equal(2.5f, ammo.Item.shootSpeed, "network hydrated ammo speed");
            if (!ammo.CanUseItem(player)) throw new InvalidOperationException("network ammo direct use rejected");
            Equal(134, ammo.Item.shoot, "network ammo survives direct-use projection");
            var tag = new TagCompound();
            ammo.SaveData(tag);
            var saveOnly = AmmoFixture(AmmoID.Rocket, 135, 0f);
            saveOnly.LoadData(tag);
            if (!GeneratedItemData.IsPlayerSaveReferenceOnly(saveOnly.Data))
                throw new InvalidOperationException("player save must carry a reference, not full ammo gameplay");
            Equal(AmmoID.None, saveOnly.Item.ammo, "unresolved save cannot invent ammo without canonical registry");
        });
    }

    private static void GeneratedAmmoPickAmmoKeepsExactRocketAndSolution()
    {
        WithPlayer((player, _) => {
            foreach (var (category, projectile, contribution) in new[] {
                (AmmoID.Rocket, 134, 2.5f), (AmmoID.Solution, 146, -1.25f),
                (AmmoID.Bullet, 14, 3.75f),
            }) {
                var ammo = AmmoFixture(category, projectile, contribution);
                player.inventory[0] = ammo.Item;
                player.inventory[0].stack = 10;
                player.selectedItem = 1;
                var weapon = new Item {
                    type = ItemID.CopperShortsword, useAmmo = category,
                    shoot = 100, shootSpeed = 8f, damage = 30, knockBack = 2f,
                };
                player.inventory[1] = weapon;
                if (!ammo.CanUseItem(player))
                    throw new InvalidOperationException("direct use before ammo selection was rejected");
                if (!player.PickAmmo(weapon, out int selected, out float speed,
                    out int damage, out float knockback, out int usedId, dontConsume: true))
                    throw new InvalidOperationException("vanilla failed to choose generated ammo");
                Equal(projectile, selected, "final projectile for authored ammo category");
                Equal(8f + contribution, speed, "vanilla ammo shootSpeed contribution");
                Equal(ammo.Item.type, usedId, "vanilla chose generated ammo stack");
                if (damage < 0 || knockback < 0f)
                    throw new InvalidOperationException("vanilla returned invalid combat values");
                Equal(10, ammo.Item.stack, "non-consuming PickAmmo preserved stack");
            }
        });
    }

    private static void GeneratedAmmoDirectUseKeepsDeclaredProjectile()
    {
        WithPlayer((player, _) => {
            foreach (var (category, projectile, speed) in new[] {
                (AmmoID.Bullet, 14, 2.5f), (AmmoID.Rocket, 134, -1.25f),
                (AmmoID.Solution, 146, 3.75f),
            }) {
                var ammo = AmmoFixture(category, projectile, speed);
                Equal(projectile, ammo.Item.shoot, "declared ammo projectile before direct use");
                Equal(speed, ammo.Item.shootSpeed, "declared ammo speed before direct use");
                if (!ammo.CanUseItem(player)) throw new InvalidOperationException("fixture use was rejected");
                Equal(projectile, ammo.Item.shoot, "direct use preserves ammo projectile");
                Equal(speed, ammo.Item.shootSpeed, "direct use preserves ammo speed");
            }
        });
    }
}
