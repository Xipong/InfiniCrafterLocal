using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
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
        AttachItem(host, item, data);
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
                using var spawn = new Hook(NativeProjectileEntry(),
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

    private static void WeaponAmmoActivationDelayPreservesNativeShotAndHydration()
    {
        using var scope = new SwarmRuntimeScope();
        var property = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        var previous = property.GetValue(null);
        using var registry = new GeneratedItemRegistryService();
        try
        {
            property.SetValue(null, registry);
            foreach (string basis in new[] { "native_shot", "authored_spawn" })
            foreach (int extraUpdates in new[] { 0, 2 })
            foreach (float nativeSpeed in new[] { 0f, 12f })
            foreach (string aim in new[] { "velocity", "none" })
            {
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
                var data = WeaponAmmoFixture("arrow", basis);
                var entity = data.RuntimeProgram.TryGetEntity("root")!;
                entity.Spawn.Aim = aim;
                entity.Spawn.OverTarget.DelayTicks = 2; entity.Spawn.OverTarget.HeightTiles = 2;
                entity.Collision.ExtraUpdates = extraUpdates;
                data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
                GeneratedItemRegistryService.StampCurrentWorld(data);
                ((IDictionary)registry.GetType().GetField("_byId", RootPrivate)!.GetValue(registry)!)[data.Id] = data;
                var owner = Terraria.Main.player[0];
                var item = WeaponAmmoHost(data); owner.inventory[0] = item.Item;
                Equal(true, item.CanUseItem(owner), "delayed ammo root is admitted");
                GeneratedProjectile? host = null;
                Vector2 expected = aim == "none" ? Vector2.Zero : Vector2.UnitX * (basis == "native_shot" ? nativeSpeed : 8f);
                // Isolate native allocation only. The real Shoot -> SpawnRuntimeEntity
                // -> Configure -> AI/ExtraAI path executes; no world registration is claimed.
                using (var native = new Hook(NativeProjectileEntry(),
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                    ((source, position, velocity, type, damage, knockback, ownerId, a, b, c) =>
                    {
                        Equal(expected, velocity, "exact selected launch reaches allocation before waiting");
                        var projectile = new Projectile { owner = ownerId, active = true, velocity = velocity,
                            damage = damage, knockBack = knockback, Center = position };
                        host = Attach(projectile);
                        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, host);
                        return projectile;
                    })))
                    item.Shoot(owner, new EntitySource_ItemUse_WithAmmo(owner, item.Item, ItemID.WoodenArrow),
                        Vector2.Zero, Vector2.UnitX * nativeSpeed, 0, 30, 2f);
                Equal(true, host is not null, "real root producer configured isolated host");
                host!.AI(); Equal(Vector2.Zero, host.Projectile.velocity, "first delay update suppresses motion");
                byte[] payload = ReviewExtra(host);
                Equal((byte)(basis == "native_shot" ? 5 : 4), payload[0], "only explicit native delay gains transport extension");
                int remainingWait = 2 * (extraUpdates + 1) - 1;
                for (int update = 0; update < remainingWait; update++) host.AI();
                host.AI(); Equal(expected, host.Projectile.velocity, "local first active update retains selected speed, including zero");
                foreach (var role in SwarmRoles)
                foreach (bool deferDefinition in new[] { false, true })
                {
                    Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                    var definitions = (IDictionary)registry.GetType().GetField("_byId", RootPrivate)!.GetValue(registry)!;
                    if (deferDefinition) definitions.Remove(data.Id);
                    var peer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80, damage = 30 });
                    // This headless hydration check has no ModPacket transport;
                    // observe the unavailable definition off its request cadence.
                    if (deferDefinition) typeof(GeneratedProjectile).GetField("_pendingHydrationTicks", RootPrivate)!.SetValue(peer, 1);
                    peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
                    if (deferDefinition)
                    {
                        Equal(false, peer.Matches(data.Id, entity.Id), "snapshot waits for its exact definition");
                        definitions[data.Id] = data;
                    }
                    else Equal(true, peer.Matches(data.Id, entity.Id), "delayed native root hydrates " + role.Name);
                    for (int update = 0; update < remainingWait; update++)
                    {
                        peer.AI(); Equal(Vector2.Zero, peer.Projectile.velocity, "hydrated delay remains motionless");
                    }
                    peer.AI(); Equal(expected, peer.Projectile.velocity, "hydrated activation keeps exact launch " + role.Name);
                    peer.Projectile.velocity = new Vector2(2f, 7f);
                    peer.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true); peer.AI();
                    Equal(new Vector2(2f, 7f), peer.Projectile.velocity, "late metadata hydration never relaunches live motion");
                    Equal(true, typeof(GeneratedProjectile).GetField("_activationSpawnBudget", RootPrivate)!.GetValue(peer) is null,
                        "received launch snapshot creates no owner spawn ledger");
                }
                if (basis == "native_shot")
                {
                    foreach (string mutation in new[] { "non-finite", "truncated", "authored-policy", "no-delay", "child-depth", "deferred-policy" })
                    {
                        byte[] invalid = (byte[])payload.Clone();
                        if (mutation == "non-finite") Array.Copy(BitConverter.GetBytes(float.PositiveInfinity), 0, invalid, invalid.Length - 8, 4);
                        else if (mutation == "truncated") invalid = invalid[..^1];
                        else if (mutation == "authored-policy") data.RuntimeProgram.WeaponAmmo!.SpeedBasis = "authored_spawn";
                        else if (mutation == "no-delay") entity.Spawn.OverTarget.DelayTicks = 0;
                        else if (mutation == "child-depth")
                        {
                            using var input = new BinaryReader(new MemoryStream(invalid));
                            input.ReadByte(); input.ReadString(); input.ReadString();
                            invalid[(int)input.BaseStream.Position] = 1;
                        }
                        var definitions = (IDictionary)registry.GetType().GetField("_byId", RootPrivate)!.GetValue(registry)!;
                        if (mutation == "deferred-policy") definitions.Remove(data.Id);
                        var peer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80, friendly = true });
                        if (mutation == "deferred-policy") typeof(GeneratedProjectile).GetField("_pendingHydrationTicks", RootPrivate)!.SetValue(peer, 1);
                        peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(invalid)));
                        if (mutation == "deferred-policy")
                        {
                            data.RuntimeProgram.WeaponAmmo!.SpeedBasis = "authored_spawn";
                            definitions[data.Id] = data;
                        }
                        peer.AI();
                        Equal(false, peer.Matches(data.Id, entity.Id), "invalid native launch remains refused " + mutation);
                        Equal(false, peer.Projectile.friendly, "invalid native launch remains inert " + mutation);
                        data.RuntimeProgram.WeaponAmmo!.SpeedBasis = basis;
                        entity.Spawn.OverTarget.DelayTicks = 2;
                    }
                }
            }
        }
        finally { property.SetValue(null, previous); }
    }

    private static void WeaponAmmoDelayedLaunchIsPerShotAndDoesNotLeakToOtherProducers()
    {
        using var scope = new SwarmRuntimeScope();
        var owner = Terraria.Main.player[0];
        var data = WeaponAmmoFixture("arrow", "native_shot");
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Spawn.Aim = "velocity"; entity.Spawn.OverTarget.DelayTicks = 2; entity.Spawn.OverTarget.HeightTiles = 2;
        var item = WeaponAmmoHost(data); owner.inventory[0] = item.Item;
        var hosts = new System.Collections.Generic.List<GeneratedProjectile>();
        using var native = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, ownerId, a, b, c) =>
            {
                var projectile = new Projectile { owner = ownerId, active = true, velocity = velocity,
                    damage = damage, knockBack = knockback, Center = position };
                // A native allocation/spawn hook can refine the launch before Configure.
                if (source.Context == "adjust-native-launch") projectile.velocity += Vector2.UnitY * 3f;
                var host = Attach(projectile); hosts.Add(host);
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, host);
                return projectile;
            }));
        foreach (float speed in new[] { 12f, 17f })
        {
            Equal(true, item.CanUseItem(owner), "same Item admits distinct native shots");
            item.Shoot(owner, new EntitySource_ItemUse_WithAmmo(owner, item.Item, ItemID.WoodenArrow, "adjust-native-launch"),
                Vector2.Zero, Vector2.UnitX * speed, 0, 30, 2f);
        }
        item.HoldItem(owner); // Same definition/root entity, but no native shot speed owner.
        Equal(3, hosts.Count, "two active roots plus independent passive hold root");
        for (int index = 0; index < 3; index++)
        {
            var host = hosts[index];
            Equal((byte)(index < 2 ? 5 : 4), ReviewExtra(host)[0], "snapshot belongs only to actual native shot producer");
            for (int update = 0; update < 3; update++) host.AI();
            Equal(index < 2 ? new Vector2(index == 0 ? 12f : 17f, 3f) : Vector2.UnitX * 8f,
                host.Projectile.velocity, "per-instance launch survives waiting; hold keeps authored speed");
        }
        // Event dispatch has no native ammo speed override, even for the same definition.
        GeneratedProjectile.SpawnRuntimeEntity(data, entity.Id, owner, owner.GetSource_ItemUse(item.Item),
            Vector2.Zero, Vector2.UnitX, 1, 1, requestedCount: 1);
        var child = hosts[^1];
        Equal((byte)4, ReviewExtra(child)[0], "event child does not inherit native root snapshot");
        for (int update = 0; update < 3; update++) child.AI();
        Equal(Vector2.UnitX * 8f, child.Projectile.velocity, "event child keeps authored initial speed");
        entity.Spawn.OverTarget.DelayTicks = 0;
        Equal(true, item.CanUseItem(owner), "zero-delay shot admitted");
        item.Shoot(owner, new EntitySource_ItemUse_WithAmmo(owner, item.Item, ItemID.WoodenArrow),
            Vector2.Zero, Vector2.UnitX * 19f, 0, 30, 2f);
        var immediate = hosts[^1];
        Equal((byte)4, ReviewExtra(immediate)[0], "zero-delay native shot needs no launch extension");
        immediate.AI(); Equal(Vector2.UnitX * 19f, immediate.Projectile.velocity, "zero-delay native motion stays unchanged");
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


}
