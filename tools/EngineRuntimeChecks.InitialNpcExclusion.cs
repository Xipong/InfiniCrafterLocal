#nullable enable
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeInitialNpcExclusion InitialNpcState(GeneratedProjectile generated)
        => (RuntimeInitialNpcExclusion)typeof(GeneratedProjectile).GetField("_initialNpcExclusion",
            BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(generated)!;

    private static void InitialNpcExclusionUsesExactIncarnationAndCounter()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var data = SwarmWire(SwarmGameplayFixture());
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        NPC original = Rt01Npc(0), other = Rt01Npc(1);
        Equal(false, RuntimeInitialNpcExclusion.TryCapture(original, 10, out _), "unknown generation refuses exclusion");
        Equal(true, RuntimeInitialNpcExclusion.TryCapture(null, 0, out var empty), "explicit zero needs no NPC");
        Equal(RuntimeInitialNpcExclusion.None, empty, "zero is canonical absence");
        foreach (int invalid in new[] { -1, 601, int.MaxValue })
            Equal(false, RuntimeInitialNpcExclusion.TryCapture(original, invalid, out _), "out-of-contract counter refuses");
        Rt01ReceiveToken(original, 41); Rt01ReceiveToken(other, 42);
        foreach (int counter in new[] { 1, 2, 10, 600 })
        {
            Equal(true, RuntimeInitialNpcExclusion.TryCapture(original, counter, out var captured), "capture exact NPC");
            var generated = SwarmHost(data, entity);
            generated.SetInitialNpcExclusion(captured);
            Equal((bool?)false, generated.CanHitNPC(original), "suppression starts before first AI");
            Equal((bool?)null, generated.CanHitNPC(other), "unrelated NPC remains native");
            // Actual AI decrements exactly once per native update, independent of
            // the world clock and extraUpdates. No copied countdown arithmetic.
            for (int update = 1; update <= counter; update++)
            {
                generated.AI();
                Equal(update == counter ? (bool?)null : false, generated.CanHitNPC(original),
                    "counter decrements before collision update=" + update);
            }
            Equal(RuntimeInitialNpcExclusion.None, InitialNpcState(generated), "exhausted snapshot canonicalizes to none");
        }
        Equal(true, RuntimeInitialNpcExclusion.TryCapture(original, 10, out var stable), "capture reused-slot probe");
        var host = SwarmHost(data, entity); host.SetInitialNpcExclusion(stable);
        original.Transform(NPCID.BlueSlime);
        Equal((bool?)false, host.CanHitNPC(original), "Transform keeps incarnation exclusion");
        Rt01ReceiveToken(original, 43);
        Equal((bool?)null, host.CanHitNPC(original), "same object and slot with new generation is not excluded");
        Equal(false, stable.CanApply, "stale exclusion cannot be admitted by another spawn");
        Rt01ReceiveToken(original, 41);
        Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
        Equal((bool?)null, host.CanHitNPC(Terraria.Main.npc[0]), "slot replacement is not same physical NPC");
        Equal(false, stable.CanApply, "slot replacement prevents fresh protected spawn");
        host.Configure(data, entity, 0, 8, Vector2.UnitX);
        Equal(RuntimeInitialNpcExclusion.None, InitialNpcState(host), "fresh configuration resets instance exclusion");
    }

    private static void InitialNpcExclusionExtraAiPreservesRemainingAndOldAbsence()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var property = typeof(InfiniMod).GetProperty("GeneratedItems")!;
        var previous = property.GetValue(null);
        using var registry = new GeneratedItemRegistryService();
        try
        {
            var data = SwarmWire(SwarmGameplayFixture()); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            property.SetValue(null, registry); GeneratedItemRegistryService.StampCurrentWorld(data);
            ((IDictionary)registry.GetType().GetField("_byId", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(registry)!)[data.Id] = data;
            NPC npc = Rt01Npc(0); Rt01ReceiveToken(npc, 51);
            RuntimeInitialNpcExclusion.TryCapture(npc, 10, out var exclusion);
            var owner = SwarmHost(data, entity); owner.SetInitialNpcExclusion(exclusion);
            owner.AI(); owner.AI();
            byte[] payload = ReviewExtra(owner);
            Equal((byte)4, payload[0], "extended ExtraAI version");
            foreach (var role in SwarmRoles)
            {
                Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                var projectile = new Projectile { owner = 0, active = true, timeLeft = 80, damage = 100, width = 12, height = 12 };
                var peer = Attach(projectile);
                peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
                Equal(true, peer.Matches(data.Id, entity.Id), "real decoder hydrates metadata " + role.Name);
                Equal(8, InitialNpcState(peer).RemainingUpdates, "wire carries remaining countdown " + role.Name);
                Equal((bool?)false, peer.CanHitNPC(npc), "peer uses same exact exclusion " + role.Name);
                Equal(true, typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(peer) is null,
                    "snapshot never creates owner spawn authority " + role.Name);
                peer.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
                Equal(8, InitialNpcState(peer).RemainingUpdates, "metadata hydration does not reset duration " + role.Name);
                // v2 carries no exclusion. Same known old prefix is accepted,
                // while a new physical host receives no invented exclusion.
                byte[] v3 = payload[..^1]; v3[0] = 3;
                var v3Peer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80 });
                v3Peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(v3)));
                Equal(true, v3Peer.Matches(data.Id, entity.Id), "v3 remains readable " + role.Name);
                Equal(8, InitialNpcState(v3Peer).RemainingUpdates, "v3 retains exact counter " + role.Name);
                byte[] oldPayload = payload[..^9]; oldPayload[0] = 2;
                var oldPeer = Attach(new Projectile { owner = 0, active = true, timeLeft = 80 });
                oldPeer.ReceiveExtraAI(new BinaryReader(new MemoryStream(oldPayload)));
                Equal(true, oldPeer.Matches(data.Id, entity.Id), "v2 remains readable " + role.Name);
                Equal(RuntimeInitialNpcExclusion.None, InitialNpcState(oldPeer), "v2 absence remains empty " + role.Name);
            }
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            owner.AI(); Equal(7, InitialNpcState(owner).RemainingUpdates, "local owner advanced after capture");
            owner.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
            Equal(7, InitialNpcState(owner).RemainingUpdates, "same-source observation cannot extend local counter");
            byte[] invalid = (byte[])payload.Clone(); Array.Clear(invalid, invalid.Length - 7, 4);
            var rejected = Attach(new Projectile { owner = 0, active = true, friendly = true, timeLeft = 90, velocity = Vector2.UnitX });
            rejected.ReceiveExtraAI(new BinaryReader(new MemoryStream(invalid)));
            Equal(false, rejected.Projectile.friendly, "zero generation with positive counter fails closed");
            Equal(Vector2.Zero, rejected.Projectile.velocity, "malformed snapshot disables motion");
            Equal(false, rejected.Matches(data.Id, entity.Id), "malformed snapshot cannot hydrate as GREEN");
            rejected.AI();
            Equal(false, rejected.Matches(data.Id, entity.Id), "later registry hydration cannot erase malformed exclusion");
            Equal(false, rejected.Projectile.friendly, "rejected transport remains inert on later AI");
            rejected.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
            Equal(true, rejected.Matches(data.Id, entity.Id), "new complete valid payload can restore this host");
        }
        finally { property.SetValue(null, previous); }
    }

    private static void ExplicitSpawnTransformRejectsInvalidBeforeNativeBoundary()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var data = SwarmWire(SwarmGameplayFixture());
        Player owner = Terraria.Main.player[0]; var source = owner.GetSource_Misc("initial-transform-check");
        foreach (var invalid in new[] {
            new RuntimeSpawnTransform(Vector2.Zero, Vector2.Zero),
            new RuntimeSpawnTransform(new Vector2(float.NaN, 0), Vector2.UnitX),
            new RuntimeSpawnTransform(Vector2.Zero, new Vector2(float.PositiveInfinity, 1)),
        })
            Equal(0, GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
                Vector2.Zero, Vector2.UnitX, 1, 8, initialTransform: invalid), "invalid transform refuses before real spawn boundary");
        var transform = new RuntimeSpawnTransform(new Vector2(128, 160), Vector2.UnitY);
        Equal(true, transform.IsValid, "explicit finite transform accepted");
        using var intercept = new MonoMod.RuntimeDetour.Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
            new[] { typeof(Terraria.DataStructures.IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int),
                typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<Terraria.DataStructures.IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                ((src, position, velocity, type, damage, kb, who, a, b, c) => {
                    Equal(transform.Position, position, "adapter transform reaches exact native position");
                    Equal(transform.Direction * data.RuntimeProgram.TryGetEntity("root")!.Spawn.SpeedPxPerTick, velocity,
                        "adapter transform retains authored child speed");
                    throw new InvalidOperationException("observed initial transform native boundary");
                }));
        bool observed = false;
        var budget = new RuntimeSpawnBudget(8);
        Equal(8, budget.Reserve(8), "caller transfers the explicit child reservation");
        try { GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
            Vector2.Zero, Vector2.UnitX, 1, 8, activationBudget: budget, initialTransform: transform); }
        catch (InvalidOperationException error) when (error.Message == "observed initial transform native boundary") { observed = true; }
        Equal(true, observed, "real production spawn reached native boundary without synthesizing a projectile");
        Equal(8, budget.Remaining, "native exception returns the transferred child reservation exactly once");
        try { GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
            Vector2.Zero, Vector2.UnitX, 0, 8, activationBudget: budget, initialTransform: transform); }
        catch (InvalidOperationException error) when (error.Message == "observed initial transform native boundary") { }
        Equal(8, budget.Remaining, "root admission never invents an event-budget refund");
    }
}
