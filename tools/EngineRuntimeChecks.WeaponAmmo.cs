using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData WeaponAmmoFixture(string category, string speedBasis)
    {
        var data = RootSpawnFixture(0, 1);
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Kind = RuntimeEntityKind.FreeProjectile;
        root.VisualRole = root.Visual.Role = "projectile";
        root.Movement.Name = "move_straight"; root.Movement.Code = 0;
        root.Spawn.SpeedPxPerTick = 8f;
        root.Damage.Enabled = true; root.Damage.Damage = 30;
        root.Damage.Knockback = 2f; root.Damage.DamageClass = "ranged";
        data.Gameplay.Damage = 7; data.Gameplay.Knockback = 1f;
        data.RuntimeProgram.WeaponAmmo = new RuntimeWeaponAmmoSpec { AmmoCategory = category, SpeedBasis = speedBasis };
        return data;
    }

    private sealed class WeaponAmmoProbeItem : GeneratedItem
    {
        internal bool SaveAmmo;
        internal int Shoots;
        internal int SelectedProjectile, FinalDamage;
        internal float FinalKnockback, FinalSpeed;
        public override bool CanConsumeAmmo(Item ammo, Player player) => !SaveAmmo;
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity,
            ref int type, ref int damage, ref float knockback)
        {
            SelectedProjectile = type;
            velocity *= 1.25f; damage += 7; knockback += .5f;
            FinalSpeed = velocity.Length(); FinalDamage = damage; FinalKnockback = knockback;
        }
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position,
            Vector2 velocity, int type, int damage, float knockback)
        {
            Shoots++;
            return base.Shoot(player, source, position, velocity, type, damage, knockback);
        }
    }

    private static WeaponAmmoProbeItem WeaponAmmoHost(GeneratedItemData data)
    {
        var item = new Item(); item.SetDefaults(ItemID.CopperShortsword); item.stack = 1;
        var host = new WeaponAmmoProbeItem();
        typeof(ModType<Item>).GetProperty("Entity", RootPrivate)!.SetValue(host, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
        host.SetDefaults();
        Equal(true, ReferenceEquals(data, host.Data), "weapon-ammo fixture retains explicit definition");
        return host;
    }

    private static void WeaponAmmoNativeShotKeepsSelectionConservationAndStats()
    {
        using var scope = new MobilityConsumptionNativeScope();
        var bridge = new GeneratedRootCombatSystem();
        MethodInfo nativeShoot = typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!;
        try
        {
            bridge.Load();
            foreach (string category in new[] { "arrow", "bullet" })
            foreach (string speedBasis in new[] { "authored_spawn", "native_shot" })
            foreach (bool save in new[] { false, true })
            WithPlayer((player, _) =>
            {
                PrepareMobilityConsumptionPlayer(player);
                var data = WeaponAmmoFixture(category, speedBasis);
                var host = WeaponAmmoHost(data); host.SaveAmmo = save;
                player.inventory[0] = host.Item;
                var ammo = new Item(); ammo.SetDefaults(category == "arrow" ? ItemID.FlamingArrow : ItemID.MeteorShot); ammo.stack = 3;
                // Native ammo slots have selection priority over ordinary inventory.
                player.inventory[54] = ammo;
                Equal(true, host.CanUseItem(player), "native ammo shot admission");
                var root = data.RuntimeProgram.TryGetEntity("root")!;
                var oracle = new Item { type = ItemID.CopperShortsword, damage = root.Damage.Damage,
                    knockBack = root.Damage.Knockback, DamageType = DamageClass.Ranged,
                    shoot = host.Item.shoot, shootSpeed = host.Item.shootSpeed, useAmmo = host.Item.useAmmo };
                Equal(true, player.PickAmmo(oracle, out int expectedProjectile, out float expectedSpeed,
                    out int expectedDamage, out float expectedKnockback, out int expectedAmmo, dontConsume: true), "real native nonconsuming ammo oracle");
                Equal(3, ammo.stack, "ammo oracle has no consumption side effects");
                using var spawn = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect), new[] {
                    typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float),
                    typeof(int), typeof(float), typeof(float), typeof(float) })!,
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                    ((source, position, velocity, type, damage, knockback, owner, a, b, c) =>
                    {
                        Equal(ModContent.ProjectileType<GeneratedProjectile>(), type, "authored runtime proxy owns projectile behavior");
                        Equal(expectedProjectile, host.SelectedProjectile, "real native selected ammo reaches late hook");
                        Equal(expectedDamage + 7, damage, "native root-plus-ammo damage and late hook exactly once");
                        Equal(expectedKnockback + .5f, knockback, "native ammo knockback and late hook exactly once");
                        Equal(host.FinalDamage, damage, "no second player damage scaling at spawn");
                        Equal(host.FinalKnockback, knockback, "no second player knockback scaling at spawn");
                        float expected = speedBasis == "native_shot" ? expectedSpeed * 1.25f : root.Spawn.SpeedPxPerTick;
                        Equal(true, MathF.Abs(expected - velocity.Length()) < .0001f, "explicit initial speed policy reaches actual spawn boundary");
                        Equal(expectedAmmo, ((EntitySource_ItemUse_WithAmmo)source).AmmoItemIdUsed, "native selected ammo identity reaches source metadata");
                        Equal(true, ReferenceEquals(((EntitySource_ItemUse_WithAmmo)source).Item, host.Item), "exact source Item survives root projection");
                        throw new RootCombatSpawnBoundary();
                    }));
                try { nativeShoot.Invoke(player, new object[] { player.whoAmI, host.Item, player.GetWeaponDamage(host.Item) }); }
                catch (TargetInvocationException error) when (RootCombatBoundary(error)) { }
                Equal(1, host.Shoots, "native shot dispatches once");
                Equal(save ? 3 : 2, ammo.stack, "native consumption honors weapon conservation hook");
                Equal(1, host.Item.stack, "ammo debit does not spend reusable generated weapon");
                Equal(false, ItemLoader.ConsumeItem(host.Item, player), "direct-use stack cost remains independent");
            });
        }
        finally { bridge.Unload(); }
    }

    private static void WeaponAmmoMissingAmmoAndIndependentUseLanes()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, generated) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            var data = WeaponAmmoFixture("arrow", "native_shot");
            data.Gameplay.HealLife = 5;
            data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Append(new RuntimeBindingSpec {
                Id = "alternate_effect", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Secondary,
                UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } },
            }).ToArray();
            var host = WeaponAmmoHost(data); player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "CanUseItem never consumes ammo while checking policy");
            Equal(AmmoID.Arrow, host.Item.useAmmo, "explicit active shot requires native arrows");
            Equal(false, player.PickAmmo(host.Item, out _, out _, out _, out _, out _, dontConsume: false), "native selection refuses missing ammunition");
            Equal(0, host.Shoots, "missing ammo never called runtime Shoot");
            player.altFunctionUse = 2;
            Equal(true, host.CanUseItem(player), "independent alternate effects remain usable without ammo");
            Equal(AmmoID.None, host.Item.useAmmo, "non-shot action clears native ammo requirement");
            Equal(5, host.Item.healLife, "alternate native effect remains selected");
            player.altFunctionUse = 0;
            Equal(true, host.CanUseItem(player), "switching back reprojects exact weapon ammo");
            Equal(AmmoID.Arrow, host.Item.useAmmo, "primary requirement restored");
            int before = host.Item.stack;
            using var spawn = RootCombatSpawnObserver((_, _, _) => { });
            try { host.HoldItem(player); }
            catch (RootCombatSpawnBoundary) { }
            Equal(before, host.Item.stack, "passive hold spawn is not a native ammo use");
        });
    }

    private static void WeaponAmmoNativeDtoPreservesAbsenceAndRejectsInvalidPresence()
    {
        string json = WeaponAmmoFixture("bullet", "native_shot").ToJson();
        var parsed = GeneratedItemData.FromJson(json);
        Equal("bullet", parsed!.RuntimeProgram.WeaponAmmo!.AmmoCategory, "ammo category survives native JSON roundtrip");
        Equal("native_shot", parsed.RuntimeProgram.WeaponAmmo.SpeedBasis, "explicit speed choice survives native JSON roundtrip");
        foreach (string mutation in new[] { "null", "missing_category", "missing_speed", "alias", "native_projectile_policy", "passive_only", "dual_ammo_role" })
        {
            JsonObject root = JsonNode.Parse(json)!.AsObject();
            JsonObject runtime = root["runtimeProgram"]!.AsObject();
            JsonObject ammo = runtime["weaponAmmo"]!.AsObject();
            if (mutation == "null") runtime["weaponAmmo"] = null;
            else if (mutation == "missing_category") ammo.Remove("ammoCategory");
            else if (mutation == "missing_speed") ammo.Remove("speedBasis");
            else if (mutation == "alias") ammo["ammoCategory"] = "bullets";
            else if (mutation == "native_projectile_policy") ammo["projectilePolicy"] = "native_ammo";
            else if (mutation == "passive_only")
            {
                JsonArray bindings = runtime["bindings"]!.AsArray();
                for (int index = bindings.Count - 1; index >= 0; index--)
                    if (RuntimeBindingSpec.IsActiveInput((string?)bindings[index]!["input"] ?? ""))
                        bindings.RemoveAt(index);
            }
            else
            {
                root["gameplay"]!["ammoCategory"] = "bullet";
                root["gameplay"]!["ammoProjectileId"] = ProjectileID.Bullet;
            }
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "invalid native weapon ammo rejected: " + mutation);
        }
        Equal(true, GeneratedItemData.FromJson(RootSpawnFixture(0, 1).ToJson())!.RuntimeProgram.WeaponAmmo is null,
            "legacy native DTO does not invent ammo requirements");
    }
}
