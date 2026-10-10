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
        Equal(false, LaunchRoot(legacy)["spawn"]!.AsObject().ContainsKey("velocityDistribution"), "old constant wire gains no distribution");
        foreach (string kind in new[] { "fan_speed", "radial", "disk", "cone" })
        {
            var data = SampledLaunchFixture(kind);
            Equal(kind, data.RuntimeProgram.TryGetEntity("root")!.Spawn.VelocityDistribution!.Kind, "exact distribution survives strict DTO");
            var valid = JsonNode.Parse(data.ToNetworkJson())!;
            foreach (string invalid in new[] { "null", "{}", "{\"kind\":\"RADIAL\",\"minSpeedPxPerUpdate\":4,\"maxSpeedPxPerUpdate\":8}",
                "{\"kind\":\"radial\",\"maxSpeedPxPerUpdate\":8}", "{\"kind\":\"radial\",\"minSpeedPxPerUpdate\":9,\"maxSpeedPxPerUpdate\":8}",
                "{\"kind\":\"disk\",\"minSpeedPxPerUpdate\":0,\"maxSpeedPxPerUpdate\":8}", "{\"kind\":\"disk\",\"maxSpeedPxPerUpdate\":null}",
                "{\"kind\":\"disk\",\"maxSpeedPxPerUpdate\":81}", "{\"kind\":\"cone\",\"minSpeedPxPerUpdate\":4,\"maxSpeedPxPerUpdate\":8}" })
            {
                var candidate = JsonNode.Parse(valid.ToJsonString())!;
                LaunchRoot(candidate)["spawn"]!["velocityDistribution"] = JsonNode.Parse(invalid);
                Equal(true, GeneratedItemData.FromJson(candidate.ToJsonString()) is null, "incomplete or competing sampled variant refuses");
            }
            var competing = JsonNode.Parse(valid.ToJsonString())!;
            LaunchRoot(competing)["spawn"]!["speedPxPerTick"] = 2;
            Equal(true, GeneratedItemData.FromJson(competing.ToJsonString()) is null, "sampled branch cannot hide a second speed");
        }
        foreach (string mutation in new[] { "missing-aim", "missing-offset", "missing-placement", "case-aim", "case-placement", "negative-over", "null-over", "case-event", "wrong-event", "missing-geometry" })
        {
            var raw = JsonNode.Parse(HitTargetLaunchFixture().ToNetworkJson())!;
            var child = raw["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "child")!;
            var spawn = child["spawn"]!.AsObject(); var action = LaunchRoot(raw)["events"]![0]!;
            switch (mutation)
            {
                case "missing-aim": spawn.Remove("aim"); break;
                case "missing-offset": spawn.Remove("offsetPx"); break;
                case "missing-placement": spawn.Remove("placement"); break;
                case "case-aim": spawn["aim"] = "VELOCITY"; break;
                case "case-placement": spawn["placement"] = "ITEM_USE_ORIGIN"; break;
                case "negative-over": spawn["overTarget"]!["heightTiles"] = -1; break;
                case "null-over": spawn["overTarget"] = null; break;
                case "case-event": action["event"] = "ON_HIT"; break;
                case "wrong-event": action["event"] = "on_expire"; break;
                case "missing-geometry": action["hitTargetSpawn"]!.AsObject().Remove("clearancePx"); break;
            }
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "new target adapter rejects before legacy normalization: " + mutation);
        }
        foreach (string field in new[] { "count", "spreadRadians", "damageMultiplier", "delayTicks" })
        {
            var raw = JsonNode.Parse(HitTargetLaunchFixture().ToNetworkJson())!;
            LaunchRoot(raw)["events"]![0]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "new geometry cannot inherit a missing action default " + field);
        }
        foreach (float spread in new[] { -0.5f, 0.5f })
        {
            var raw = JsonNode.Parse(HitTargetLaunchFixture().ToNetworkJson())!;
            var child = raw["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "child")!;
            child["spawn"]!["velocityDistribution"] = JsonNode.Parse("{\"kind\":\"radial\",\"minSpeedPxPerUpdate\":4,\"maxSpeedPxPerUpdate\":8}");
            LaunchRoot(raw)["events"]![0]!["spreadRadians"] = spread;
            LaunchRoot(raw)["events"]![0]!.AsObject().Remove("hitTargetSpawn");
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "ordinary event radial spread refuses before clamping");
        }
    }

    private static void SampledVelocityRawNumericDomainAndRoundTrips()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        foreach ((string field, string outside, string valid) in new[] {
            ("minSpeedPxPerUpdate", "-1e-50", "0"),
            ("minSpeedPxPerUpdate", "1e-46", "1e-40"),
            ("maxSpeedPxPerUpdate", "80.000000000000000000000000001", "79.999999999999999999999999999"),
            ("maxSpeedPxPerUpdate", "80.00000000000001", "80"),
            ("halfAngleRadians", "3.1415926535897930000000000001", "3.141592653589793"),
            ("halfAngleRadians", "1e-46", "0"),
        })
        {
            var raw = JsonNode.Parse(SampledLaunchFixture("cone").ToNetworkJson())!;
            var spec = LaunchRoot(raw)["spawn"]!["velocityDistribution"]!.AsObject();
            spec[field] = "RAW_VELOCITY_NUMBER";
            string document = raw.ToJsonString();
            Equal(true, GeneratedItemData.FromJson(document.Replace("\"RAW_VELOCITY_NUMBER\"", outside, StringComparison.Ordinal)) is null,
                "raw distribution domain refuses before narrowing " + field + "=" + outside);
            var accepted = GeneratedItemData.FromJson(document.Replace("\"RAW_VELOCITY_NUMBER\"", valid, StringComparison.Ordinal))
                ?? throw new InvalidOperationException("valid raw distribution refused " + field);
            foreach (string payload in new[] { accepted.ToJson(), accepted.ToNetworkJson() })
                Equal(true, GeneratedItemData.FromJson(payload) is not null, "distribution rounded endpoint retains roundtrip " + field);
        }
    }

    private static void SampledVelocitySeededGeometryAndAreaMoments()
    {
        foreach (string kind in new[] { "fan_speed", "radial", "disk", "cone" })
        {
            var spawn = new RuntimeSpawnSpec { SpeedPxPerTick = 0, Aim = "velocity", VelocityDistribution = LaunchDistribution(kind) };
            var first = new UnifiedRandom(817);
            var replay = new UnifiedRandom(817);
            double squaredSum = 0; int left = 0, right = 0, above = 0, below = 0;
            for (int i = 0; i < 4096; i++)
            {
                Equal(true, RuntimeSpawnVelocity.TrySample(spawn, Vector2.UnitX, first, out var velocity), "bounded sample accepted");
                Equal(true, RuntimeSpawnVelocity.TrySample(spawn, Vector2.UnitX, replay, out var repeated), "same seed accepted");
                Equal(velocity, repeated, "same owner seed yields exact vector sequence");
                float speed = velocity.Length();
                Equal(true, speed <= 8.00001f && speed >= (kind == "disk" ? 0f : 3.99999f), "sampled magnitude stays in the selected interval");
                if (kind == "fan_speed") Equal(0f, velocity.Y, "fan speed preserves the supplied ray");
                if (kind == "cone") Equal(true, Math.Abs(Math.Atan2(velocity.Y, velocity.X)) <= 0.200001, "cone stays inside authored half-angle");
                squaredSum += velocity.LengthSquared();
                if (velocity.X < 0) left++; else right++;
                if (velocity.Y < 0) above++; else below++;
            }
            if (kind == "disk") Equal(true, Math.Abs(squaredSum / 4096 - 32) < 1.2, "uniform area disk has E[r squared]=R squared/2");
            if (kind is "radial" or "disk") Equal(true, new[] { left, right, above, below }.All(count => count > 1800), "full-circle support is not a deterministic fan");
            Equal(false, RuntimeSpawnVelocity.TrySample(spawn, Vector2.UnitX, null, out _), "sampled choice has no hidden RNG fallback");
        }
        var constant = new RuntimeSpawnSpec { SpeedPxPerTick = 7.125f };
        Equal(true, RuntimeSpawnVelocity.TrySample(constant, Vector2.UnitY, null, out var exact), "old constant requires no random stream");
        Equal(new Vector2(0, 7.125f), exact, "old constant speed remains exact");
    }

    private static Hook LaunchSpawnObserver(Action<IEntitySource, Vector2, Vector2, int, float> observe)
        => new(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect), new[] {
            typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                observe(source, position, velocity, damage, knockback);
                throw new RootCombatSpawnBoundary();
            }));

    private static void SampledVelocityReachesNativeSpawnOnlyOnOwner()
    {
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

    private static void HitTargetGeometryUsesCapturedHitboxAndExactBranchEndpoints()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var npc = Rt01Npc(0); Rt01ReceiveToken(npc, 901); npc.width = 40; npc.height = 100; npc.Center = new Vector2(400, 300);
        foreach (double probability in new[] { 0d, 1d })
        {
            var spec = HitGeometry(probability);
            Equal(true, RuntimeHitTargetSpawnSnapshot.TryCapture(spec, npc, Vector2.UnitX, out var captured), "real hit target captured");
            captured = captured with { Seed = 281 };
            Equal(true, RuntimeHitTargetSpawn.TryPlan(spec, captured, 3, out var transforms, out var seeds), "exact geometry batch admitted");
            for (int i = 0; i < 3; i++)
            {
                var axis = probability == 1 ? Vector2.UnitX : Vector2.UnitX.RotatedBy((i / 2d - 0.5d) * 1.2f);
                var expected = new Vector2(400, 300) + (probability == 1 ? -Vector2.UnitX : axis) * 70f;
                Equal(true, Vector2.Distance(transforms[i].Position, expected) < 0.0001f, "max hitbox side factor plus authored clearance");
                Equal(axis, transforms[i].Direction, "before and after directions retain exact selected rule");
            }
            npc.Center += Vector2.One * 100; npc.width = 200;
            Equal(true, RuntimeHitTargetSpawn.TryPlan(spec, captured, 3, out var replay, out var replaySeeds), "later target motion does not rewrite admitted geometry");
            Equal(true, transforms.SequenceEqual(replay) && seeds.SequenceEqual(replaySeeds), "captured geometry and child velocity seeds remain exact");
            Equal(true, RuntimeHitTargetSpawn.TryPlan(spec, captured, 1, out var single, out _), "single child has a finite centre ray");
            Equal(Vector2.UnitX, single[0].Direction, "single-child fan avoids division by zero");
            npc.width = 40; npc.Center = new Vector2(400, 300);
        }
        var mixed = HitGeometry(); mixed.BeforePositionJitterRadiusPx = 8; mixed.BeforeDirectionJitterRadians = 0.2f;
        RuntimeHitTargetSpawnSnapshot.TryCapture(mixed, npc, Vector2.UnitX, out var snapshot);
        int beforeCount = 0;
        for (int seed = 0; seed < 1000; seed++)
        {
            Equal(true, RuntimeHitTargetSpawn.TryPlan(mixed, snapshot with { Seed = seed }, 12, out var batch, out _), "mixed batch");
            beforeCount += batch.Count(row => row.Position.X < snapshot.Center.X);
        }
        Equal(true, Math.Abs(beforeCount / 12000d - 0.85d) < 0.015d, "authored branch probability is per child, not one branch for the batch");
        Rt01ReceiveToken(npc, 902);
        Equal(false, RuntimeHitTargetSpawn.TryPlan(mixed, snapshot, 3, out _, out _), "reused incarnation cannot receive old exclusion");
        Equal(false, RuntimeHitTargetSpawnSnapshot.TryCapture(mixed, npc, Vector2.Zero, out _), "zero direction is not replaced by a guessed side");
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
