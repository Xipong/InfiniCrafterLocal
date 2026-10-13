#nullable enable
using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Utilities;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeSpawnVelocitySpec LaunchDistribution(string kind)
    {
        var spec = new RuntimeSpawnVelocitySpec { Kind = kind, MaxSpeedPxPerUpdate = 8f };
        if (kind != "disk") spec.MinSpeedPxPerUpdate = 4f;
        if (kind == "cone") spec.HalfAngleRadians = 0.2f;
        return spec;
    }

    private static GeneratedItemData SampledLaunchFixture(string kind)
    {
        var data = SwarmGameplayFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Spawn.Aim = "velocity";
        entity.Spawn.SpeedPxPerTick = 0;
        entity.Spawn.VelocityDistribution = LaunchDistribution(kind);
        entity.Spawn.SpreadRadians = 0;
        return SwarmWire(data);
    }

    private static RuntimeHitTargetSpawnSpec HitGeometry(double before = 0.85) => new() {
        BeforeProbability = before, HitboxMaxSideFactor = 0.6f, ClearancePx = 10f,
        BeforePositionJitterRadiusPx = 0f, BeforeDirectionJitterRadians = 0f,
        AfterFanSpreadRadians = 1.2f, InitialIgnoreCountdownUpdates = 10,
    };

    private static GeneratedItemData HitTargetLaunchFixture(int delay = 0)
    {
        var data = ChildCombatFixture();
        var child = data.RuntimeProgram.TryGetEntity("child")!;
        child.Spawn.Aim = "velocity"; child.Spawn.Placement = "item_use_origin"; child.Spawn.OffsetPx = 0;
        child.Spawn.OverTarget = new();
        child.Spawn.SpeedPxPerTick = 0;
        child.Spawn.VelocityDistribution = LaunchDistribution("cone");
        var action = data.RuntimeProgram.TryGetEntity("root")!.Events[0];
        action.Count = 3; action.DelayTicks = delay; action.SpreadRadians = 0;
        action.HitTargetSpawn = HitGeometry(1);
        return SwarmWire(data);
    }

    private static JsonObject LaunchRoot(JsonNode document)
        => document["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "root")!.AsObject();

    private static void SampledLaunchDtoRejectsInvalidAndPreservesOldAbsence()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var legacy = JsonNode.Parse(SwarmWire(SwarmGameplayFixture()).ToNetworkJson())!;
        Equal(false, LaunchRoot(legacy)["spawn"]!.AsObject().ContainsKey("velocityDistribution"),
            "old constant wire gains no distribution");
        var data = SampledLaunchFixture("radial");
        Equal("radial", data.RuntimeProgram.TryGetEntity("root")!.Spawn.VelocityDistribution!.Kind,
            "authored distribution survives public deserialization");
        var invalid = JsonNode.Parse(data.ToNetworkJson())!;
        LaunchRoot(invalid)["spawn"]!["velocityDistribution"]!["minSpeedPxPerUpdate"] = 9;
        Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "reversed speed interval refuses");
        var competing = JsonNode.Parse(data.ToNetworkJson())!;
        LaunchRoot(competing)["spawn"]!["speedPxPerTick"] = 2;
        Equal(true, GeneratedItemData.FromJson(competing.ToJsonString()) is null, "competing speed owners refuse");
    }

    private static Hook LaunchSpawnObserver(Action<IEntitySource, Vector2, Vector2, int, float> observe)
        => new(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                observe(source, position, velocity, damage, knockback);
                throw new RootCombatSpawnBoundary();
            }));

    private static void SampledVelocityReachesNativeSpawnOnlyOnOwner()
    {
        using (var scope = new Rt01NpcScope(NetmodeID.SinglePlayer))
        {
            var data = SampledLaunchFixture("radial");
            bool observed = false;
            using var hook = LaunchSpawnObserver((source, position, velocity, damage, knockback) => observed = true);
            int count = -1;
            try { count = GeneratedProjectile.SpawnRuntimeEntity(data, "root", Terraria.Main.player[0],
                Terraria.Main.player[0].GetSource_Misc("competing-explicit-speeds"), Vector2.Zero, Vector2.UnitX,
                0, 8, requestedCount: 1, initialVelocitySeed: 182, rootSpeedOverride: 9f); }
            catch (Exception error) when (RootCombatBoundary(error)) { }
            Equal(false, observed, "sampled distribution cannot silently discard explicit native-shot speed");
            Equal(0, count, "competing explicit speed owners refuse before native spawn");
        }
        foreach (var role in SwarmRoles)
        {
            using var scope = new Rt01NpcScope(role.Mode); Terraria.Main.myPlayer = role.Local;
            var data = SampledLaunchFixture("radial"); var spawn = data.RuntimeProgram.TryGetEntity("root")!.Spawn;
            RuntimeSpawnVelocity.TrySample(spawn, Vector2.UnitX, new UnifiedRandom(182), out var expected);
            bool observed = false;
            using var hook = LaunchSpawnObserver((source, position, velocity, damage, knockback) => {
                observed = true; Equal(expected, velocity, "actual native spawn receives chosen vector, not the inactive zero speed");
            });
            try { GeneratedProjectile.SpawnRuntimeEntity(data, "root", Terraria.Main.player[0], Terraria.Main.player[0].GetSource_Misc("sampled-launch"),
                Vector2.Zero, Vector2.UnitX, 0, 8, requestedCount: 1, initialVelocitySeed: 182); }
            catch (Exception error) when (RootCombatBoundary(error)) { }
            Equal(role.Name is "SP" or "owner-client", observed, "only firing owner samples and calls native spawn");
        }
    }

    private static void SampledVelocityDelayExtraAiAndHydrationPreserveChosenVector()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var property = typeof(InfiniMod).GetProperty("GeneratedItems")!; var previous = property.GetValue(null);
        using var registry = new GeneratedItemRegistryService();
        try
        {
            var data = SampledLaunchFixture("radial"); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Spawn.OverTarget.HeightTiles = 2; entity.Spawn.OverTarget.DelayTicks = 2; entity.Collision.ExtraUpdates = 2;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            property.SetValue(null, registry); GeneratedItemRegistryService.StampCurrentWorld(data);
            ((IDictionary)registry.GetType().GetField("_byId", RootPrivate)!.GetValue(registry)!)[data.Id] = data;
            var owner = SwarmHost(data, entity); var selected = new Vector2(3, 4);
            owner.Projectile.velocity = selected; owner.Configure(data, entity, 0, 8, selected);
            owner.AI(); Equal(Vector2.Zero, owner.Projectile.velocity, "telegraph suppresses native motion");
            byte[] payload = ReviewExtra(owner);
            Equal((byte)4, payload[0], "v4 carries sampled launch state");
            foreach (var role in SwarmRoles)
            {
                Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                var peer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80, damage = 100, velocity = Vector2.Zero });
                peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
                Equal(true, peer.Matches(data.Id, entity.Id), "real decoder hydrates sampled entity " + role.Name);
                for (int i = 0; i < 5; i++) { peer.AI(); Equal(Vector2.Zero, peer.Projectile.velocity, "remaining five native updates preserve telegraph"); }
                peer.AI(); Equal(selected, peer.Projectile.velocity, "delay restores exact captured vector " + role.Name);
                peer.Projectile.velocity = new Vector2(2, 7);
                peer.Configure(data, entity, 0, 8, selected, preserveSyncedState: true); peer.AI();
                Equal(new Vector2(2, 7), peer.Projectile.velocity, "later hydration does not relaunch an already moving projectile");
                Equal(true, typeof(GeneratedProjectile).GetField("_activationSpawnBudget", RootPrivate)!.GetValue(peer) is null, "network observation creates no event budget");
            }
            foreach (string mutation in new[] { "flag", "non-finite", "truncated", "v3-missing" })
            {
                byte[] invalid = (byte[])payload.Clone();
                if (mutation == "flag") invalid[^9] = 2;
                else if (mutation == "non-finite") Array.Copy(BitConverter.GetBytes(float.NaN), 0, invalid, invalid.Length - 8, 4);
                else if (mutation == "truncated") invalid = invalid[..^1];
                else { invalid = invalid[..^9]; invalid[0] = 3; }
                var peer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80, friendly = true, velocity = Vector2.UnitX });
                peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(invalid))); peer.AI();
                Equal(false, peer.Matches(data.Id, entity.Id), "invalid or missing sampled state cannot become GREEN " + mutation);
                Equal(false, peer.Projectile.friendly, "invalid launch remains inert " + mutation);
            }
        }
        finally { property.SetValue(null, previous); }
    }

    private static void HitTargetDelayedNativeBoundaryAndReservationOwnership()
    {
        foreach (bool delayed in new[] { false, true })
        foreach (var role in SwarmRoles)
        {
            using var scope = new Rt01NpcScope(role.Mode); Terraria.Main.myPlayer = role.Local;
            var data = HitTargetLaunchFixture(delayed ? 2 : 0); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var parent = SwarmHost(data, entity, damage: 137, knockback: 7.25f);
            var npc = Rt01Npc(0); Rt01ReceiveToken(npc, 1001); npc.width = 40; npc.height = 100; npc.Center = new Vector2(400, 300);
            var budget = (RuntimeSpawnBudget)typeof(GeneratedProjectile).GetField("_activationSpawnBudget", RootPrivate)!.GetValue(parent)!;
            bool observed = false; Vector2? expectedVelocity = null;
            using var hook = LaunchSpawnObserver((source, position, velocity, damage, knockback) => {
                observed = true;
                Equal(true, Vector2.Distance(new Vector2(330, 300), position) < 0.0001f, "native child starts from captured NPC geometry");
                if (expectedVelocity is { } expected) Equal(expected, velocity, "delayed child keeps admission seed despite changed Main.rand");
                Equal(true, velocity.Length() >= 3.99999f && velocity.Length() <= 8.00001f, "child samples authored speed; no hidden parent-speed formula");
                Equal(68, damage, "geometry adapter retains exact A9 parent damage snapshot");
                Equal(7.25f, knockback, "geometry adapter retains exact A9 parent knockback snapshot");
                Equal(true, source is EntitySource_Parent origin && ReferenceEquals(origin.Entity, parent.Projectile), "exact native source preserved");
            });
            try
            {
                typeof(GeneratedProjectile).GetMethod("RunRuntimeEvent", RootPrivate)!.Invoke(parent, new object?[] { RuntimeEventKind.OnHit, npc, 997 });
                if (delayed && role.Name is ("SP" or "owner-client"))
                {
                    Equal(5, budget.Remaining, "three delayed children reserve from one activation ledger");
                    var pending = (IList)typeof(RuntimeDelayedActionScheduler).GetField("Pending", RootPrivate)!.GetValue(null)!;
                    var record = pending[0]!;
                    var snapshot = (RuntimeHitTargetSpawnSnapshot)record.GetType().GetProperty("HitTargetSpawn")!.GetValue(record)!;
                    RuntimeHitTargetSpawn.TryPlan(entity.Events[0].HitTargetSpawn!, snapshot, 3, out var transforms, out var seeds);
                    RuntimeSpawnVelocity.TrySample(data.RuntimeProgram.TryGetEntity("child")!.Spawn, transforms[0].Direction, new UnifiedRandom(seeds[0]), out var chosen);
                    expectedVelocity = chosen;
                    npc.Center += new Vector2(300, 100); npc.width = 300;
                    parent.Projectile.damage = 999; parent.Projectile.knockBack = 40; parent.Projectile.velocity = Vector2.UnitY;
                    Terraria.Main.rand = new UnifiedRandom(99991);
                    AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
                }
            }
            catch (Exception error) when (RootCombatBoundary(error)) { }
            Equal(role.Name is "SP" or "owner-client", observed, "only owner dispatches actual target-relative child");
            Equal(8, budget.Remaining, "native failure refunds attempted one plus unattempted two exactly once");
            Equal(0, PendingActions(), "dequeued action cannot retry or reroll");
        }
        using var refusal = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var rejectedData = HitTargetLaunchFixture(2); var rejectedEntity = rejectedData.RuntimeProgram.TryGetEntity("root")!;
        var rejectedParent = SwarmHost(rejectedData, rejectedEntity); var target = Rt01Npc(0); Rt01ReceiveToken(target, 1101);
        var ledger = (RuntimeSpawnBudget)typeof(GeneratedProjectile).GetField("_activationSpawnBudget", RootPrivate)!.GetValue(rejectedParent)!;
        typeof(GeneratedProjectile).GetMethod("RunRuntimeEvent", RootPrivate)!.Invoke(rejectedParent, new object?[] { RuntimeEventKind.OnHit, target, 1 });
        Equal(5, ledger.Remaining, "pending protected batch reserved");
        Rt01ReceiveToken(target, 1102);
        AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
        Equal(8, ledger.Remaining, "reused NPC refuses emission and returns the whole reservation");
        Equal(0, PendingActions(), "stale target does not get silently retargeted");
    }
}
