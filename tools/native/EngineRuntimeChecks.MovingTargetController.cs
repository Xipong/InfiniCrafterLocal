using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData MovingTargetFixture(string movement, int extra = 0)
    {
        var data = SentryTargetingFixture();
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Kind = RuntimeEntityKind.TemporaryHelper;
        root.VisualRole = root.Visual.Role = "helper";
        root.LifetimeTicks = 120;
        root.Targeting.Count = 1; root.Targeting.SpreadRadians = 0d;
        root.Targeting.RangeTiles = 60; root.Targeting.RequireLineOfSight = false;
        root.Targeting.TargetPolicy = "distance_score";
        root.Collision.ExtraUpdates = extra;
        root.Spawn.SpeedPxPerTick = 3f;
        root.Movement = movement == "" ? new RuntimeMovementSpec() : new RuntimeMovementSpec {
            Name = movement, Code = movement == "move_orbit" ? 4 : 0,
            Params = movement == "move_orbit" ? new RuntimeParamsSpec { RangeTiles = 4 } : new RuntimeParamsSpec(),
        };
        return SwarmWire(data);
    }

    private static void TargetAndFireCombinesMotionAndFiring()
    {
        foreach (var role in SwarmRoles)
        foreach (string movement in new[] { "", "move_straight", "move_orbit" })
        foreach (int extra in new[] { 0, 2 })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = MovingTargetFixture(movement, extra);
            var root = data.RuntimeProgram.TryGetEntity("root")!;
            var owner = Terraria.Main.player[0]; owner.Center = new Vector2(1600, 1600);
            var npc = Terraria.Main.npc[0]; npc.SetDefaults(Terraria.ID.NPCID.BlueSlime); npc.active = true;
            npc.Center = owner.Center + new Vector2(200, 0);
            var host = SwarmHost(data, root);
            host.Projectile.Center = owner.Center + new Vector2(64, 0);
            host.Projectile.velocity = new Vector2(3, 0);
            Vector2 initial = host.Projectile.Center;
            var origins = new List<Vector2>();
            using var native = new Hook(NativeProjectileEntry(),
                (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                ((source, position, velocity, type, damage, knockback, player, ai0, ai1, ai2) => {
                    Equal(host.Projectile.Center, position, "shot uses current native center, not cached spawn or predicted next position");
                    Equal(true, source is EntitySource_Parent parent && ReferenceEquals(parent.Entity, host.Projectile), "moving emitter retains exact parent source");
                    Equal(true, Vector2.Distance(Vector2.Normalize(npc.Center - position) * 10f, velocity) < 0.001f, "firing aim follows target independently of emitter motion");
                    origins.Add(position);
                    return new Projectile(); // Observe native entry, not a successful registered game spawn.
                }));
            int interval = 6 * (extra + 1);
            for (int update = 1; update <= interval * 2; update++)
            {
                host.AI();
                bool authority = role.Name is "SP" or "owner-client";
                Equal(authority ? update / interval : 0, origins.Count, "moving emitter keeps world-tick cadence and owner authority");
                if (movement == "") Equal(Vector2.Zero, host.Projectile.velocity, "omitted movement remains stationary");
                if (movement == "move_straight") Equal(new Vector2(3, 0), host.Projectile.velocity, "firing does not erase authored straight velocity");
                // CPU boundary witness of Terraria's position integration after AI;
                // production never performs a second integration inside the controller.
                if (host.ShouldUpdatePosition()) host.Projectile.position += host.Projectile.velocity;
            }
            Equal(movement == "", host.Projectile.Center == initial, "explicit movement actually changes the emitter position");
            if (origins.Count == 2 && movement != "") Equal(false, origins[0] == origins[1], "successive volleys follow the moving emitter");
        }
    }

    private static void TargetAndFireCancelledMovementDoesNotFire()
    {
        using var scope = new SwarmRuntimeScope();
        var data = MovingTargetFixture("move_orbit"); var root = data.RuntimeProgram.TryGetEntity("root")!;
        var host = SwarmHost(data, root);
        var owner = Terraria.Main.player[0]; owner.dead = true;
        typeof(GeneratedProjectile).GetField("_controllerTimer", RootPrivate)!.SetValue(host, 5);
        int kills = 0, shots = 0;
        using var kill = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill), Type.EmptyTypes)!,
            (Action<Projectile>)(p => { kills++; p.active = false; }));
        using var native = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, player, ai0, ai1, ai2) => { shots++; return new Projectile(); }));
        host.AI();
        Equal(1, kills, "movement owner cancellation retires helper");
        Equal(0, shots, "retired moving helper does not enter firing path");
        Equal(5, (int)typeof(GeneratedProjectile).GetField("_controllerTimer", RootPrivate)!.GetValue(host)!, "firing timer is not advanced after movement cancellation");
    }

    private static void TargetAndFireLaunchAndDelayKeepExplicitMotion()
    {
        using var scope = new SwarmRuntimeScope();
        foreach (string movement in new[] { "", "move_straight" })
        foreach (float speed in new[] { 0f, 3f })
        {
            var data = MovingTargetFixture(movement); var root = data.RuntimeProgram.TryGetEntity("root")!;
            root.Spawn.SpeedPxPerTick = speed;
            Vector2? observed = null;
            using var native = new Hook(NativeProjectileEntry(),
                (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                ((source, position, velocity, type, damage, knockback, player, ai0, ai1, ai2) => {
                    observed = velocity; return new Projectile();
                }));
            GeneratedProjectile.SpawnRuntimeEntity(data, root.Id, Terraria.Main.player[0],
                Terraria.Main.player[0].GetSource_Misc("moving target launch"), new Vector2(1600, 1600), Vector2.UnitX, 0, 1);
            Equal<Vector2?>(movement == "" ? Vector2.Zero : new Vector2(speed, 0), observed, "native launch consumes authored constant velocity only with explicit movement");
            root.Spawn.OverTarget.DelayTicks = 2;
            var host = SwarmHost(data, root); host.Projectile.velocity = new Vector2(speed, 0);
            host.AI(); host.AI();
            Equal(Vector2.Zero, host.Projectile.velocity, "activation delay suppresses motion");
            host.AI();
            Equal(movement == "" ? Vector2.Zero : new Vector2(speed, 0), host.Projectile.velocity, "first active update restores exact authored launch; zero stays zero");
            Equal(true, host.Projectile.netImportant, "moving helper retains network-important identity");
        }
    }
}
