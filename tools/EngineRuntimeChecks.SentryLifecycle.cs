using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
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
    private const BindingFlags SentryLifePrivate = BindingFlags.Instance | BindingFlags.NonPublic;

    private sealed class SentryLifeScope : IDisposable
    {
        private readonly int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
        private readonly Player owner = Terraria.Main.player[0];
        private readonly Projectile[] projectiles = Terraria.Main.projectile;
        internal readonly Player Owner;
        internal SentryLifeScope()
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            Owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, direction = 1 };
            Terraria.Main.projectile = Enumerable.Range(0, projectiles.Length).Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
        }
        public void Dispose()
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.projectile = projectiles; Terraria.Main.player[0] = owner;
            Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local;
        }
    }

    private static GeneratedProjectile SentryLifeHost(GeneratedItemData data, RuntimeEntitySpec entity,
        RuntimeSpawnBudget? incoming = null, int depth = 0, bool reserved = false, int slot = 0)
    {
        var projectile = Terraria.Main.projectile[slot] = new Projectile { whoAmI = slot, owner = 0, active = true, identity = slot + 100 };
        var generated = Attach(projectile);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        generated.Configure(data, entity, depth, incoming?.Remaining ?? 32, Vector2.UnitX,
            activationBudget: incoming, ownsSpawnReservation: reserved);
        return generated;
    }

    private static RuntimeSpawnBudget SentryLifeBudget(GeneratedProjectile generated)
        => (RuntimeSpawnBudget)typeof(GeneratedProjectile).GetField("_activationSpawnBudget", SentryLifePrivate)!.GetValue(generated)!;

    private static void SentryLifecycleDtoAndNativeProjection()
    {
        using var state = new SentryLifeScope();
        var data = RootSpawnFixture(32, 1); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.NativeSentry = true; entity.Spawn.DescendantMaxActive = 3; entity.Spawn.Placement = "native_resting_spot";
        entity.LifetimeTicks = 7200; entity.Hitbox.WidthPx = 26; entity.Hitbox.HeightPx = 42;
        foreach (string json in new[] { data.ToJson(), data.ToNetworkJson() }) {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("native lifecycle fixture rejected");
            var root = copy.RuntimeProgram.TryGetEntity("root")!;
            Equal(true, root.NativeSentry == true, "native flag survives wire");
            Equal(3, root.Spawn.DescendantMaxActive ?? -1, "descendant cap survives wire");
            Equal("native_resting_spot", root.Spawn.Placement, "native anchor survives wire");
        }
        var generated = SentryLifeHost(data, entity);
        Equal(true, generated.Projectile.sentry, "Configure installs explicit native sentry flag");
        Equal(7200, generated.Projectile.timeLeft, "native registration keeps authored lifetime");
        Equal(42, generated.Projectile.height, "native registration keeps authored hitbox");
        var item = new Item(); data.ApplyToItem(item); Equal(true, item.sentry, "exact native binding projects Item.sentry");
        var host = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
        var active = data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse)!;
        typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", SentryLifePrivate)!.Invoke(host, new object[] { active });
        Equal(true, item.sentry, "active binding projects native registration");
        entity.NativeSentry = false;
        typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", SentryLifePrivate)!.Invoke(host, new object[] { active });
        Equal(false, item.sentry, "explicit disabled registration survives input projection");
        generated.Configure(data, entity, 0, 32, Vector2.UnitX);
        Equal(false, generated.Projectile.sentry, "metadata update clears explicit disabled flag");
        var raw = JsonNode.Parse(data.ToJson())!.AsObject(); var row = raw["runtimeProgram"]!["entities"]![1]!.AsObject();
        row.Remove("nativeSentry"); row["spawn"]!.AsObject().Remove("descendantMaxActive");
        var legacy = GeneratedItemData.FromJson(raw.ToJsonString())!;
        Equal(false, legacy.ToJson().Contains("nativeSentry", StringComparison.Ordinal), "retained native omission stays absent");
        Equal(false, legacy.ToNetworkJson().Contains("descendantMaxActive", StringComparison.Ordinal), "retained pool omission stays absent");
        foreach (string value in new[] { "null", "0", "\"true\"" }) {
            row["nativeSentry"] = JsonNode.Parse(value);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid native boolean rejected " + value);
        }
        row.Remove("nativeSentry");
        foreach (string value in new[] { "null", "0", "97", "true", "1.5", "\"3\"" }) {
            row["spawn"]!["descendantMaxActive"] = JsonNode.Parse(value);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid descendant cap rejected " + value);
        }
    }

    private delegate void SentryRestingHook(Player owner, int type, out int x, out int y, out int push);
    private static void SentryNativeRestingSpotAndTurretCap()
    {
        using var state = new SentryLifeScope();
        var data = RootSpawnFixture(32, 1); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.NativeSentry = true; entity.Spawn.Placement = "native_resting_spot"; entity.Hitbox.HeightPx = 42;
        int restCalls = 0, turretCalls = 0, spawns = 0;
        using (var resting = new Hook(typeof(Player).GetMethod(nameof(Player.FindSentryRestingSpot))!,
            (SentryRestingHook)((Player owner, int type, out int x, out int y, out int push) => {
                Equal(true, ReferenceEquals(state.Owner, owner), "native resting spot uses exact owner");
                Equal(ModContent.ProjectileType<GeneratedProjectile>(), type, "native resting spot uses generated projectile type");
                restCalls++; x = 1200; y = 2400; push = 999;
            })))
        using (var turrets = new Hook(typeof(Player).GetMethod(nameof(Player.UpdateMaxTurrets))!, (Action<Player>)(owner => {
            Equal(true, ReferenceEquals(state.Owner, owner), "native cap uses exact owner");
            Equal(true, Terraria.Main.projectile[spawns - 1].sentry, "native cap sees hydrated sentry flag"); turretCalls++;
        })))
        using (var native = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
            new[] { typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                Equal(new Vector2(1200, 2379), position, "native ground minus half authored height; pushYUp ignored");
                var projectile = Terraria.Main.projectile[spawns] = new Projectile { whoAmI = spawns++, owner = owner, active = true, Center = position };
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, Attach(projectile));
                return projectile; // isolated host; no game-world registration claimed
            }))) {
            Equal(1, GeneratedProjectile.SpawnRuntimeEntity(data, "root", state.Owner,
                state.Owner.GetSource_Misc("native sentry"), Vector2.Zero, Vector2.UnitX, 0, 1), "native spawn boundary delivers one host");
            Equal(1, restCalls, "explicit anchor reaches native resting method"); Equal(1, turretCalls, "native cap runs after successful configuration");
        }
        // Exercise the real tML cap separately from the boundary observers.
        foreach (Projectile projectile in Terraria.Main.projectile) projectile.active = false;
        var old = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = true, owner = 0, sentry = true, timeLeft = 300 };
        var fresh = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1, active = true, owner = 0, sentry = true, timeLeft = 600 };
        var ordinary = Terraria.Main.projectile[2] = new Projectile { whoAmI = 2, active = true, owner = 0, sentry = false, timeLeft = 100 };
        state.Owner.maxTurrets = 1; state.Owner.UpdateMaxTurrets();
        Equal(false, old.active, "native maxTurrets retires oldest registered sentry");
        Equal(true, fresh.active && ordinary.active, "native cap retains newest and ignores ordinary stationary projectile");
    }

    private static void SentryDescendantPoolRetiresAndSustainsBeyond32()
    {
        using var state = new SentryLifeScope();
        var data = RootSpawnFixture(32, 1); var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Spawn.DescendantMaxActive = 2;
        var rootHost = SentryLifeHost(data, root, new RuntimeSpawnBudget(32));
        RuntimeSpawnBudget pool = SentryLifeBudget(rootHost);
        var child = Entity(); child.Id = "child";
        for (int i = 0; i < 100; i++) {
            Equal(1, pool.Reserve(1), "live pool admits shot after earlier retirement " + i);
            var host = SentryLifeHost(data, child, pool, 1, true, 1);
            Equal(1, pool.Remaining, "successful descendant occupies one slot");
            if (i % 2 == 0) {
                host.OnKill(50); host.OnKill(50);
                Equal(2, pool.Remaining, "terminal hook returns occupancy exactly once");
            } else {
                host.Projectile.active = false;
                Equal(2, pool.Reserve(2), "native active=false is reaped without requiring OnKill"); pool.Return(2);
            }
        }
        Equal(2, pool.Remaining, "one hundred sequential descendants retain full capacity");
        Equal(1, pool.Reserve(1), "reserve for incarnation retirement");
        var stale = SentryLifeHost(data, child, pool, 1, true, 1);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(stale.Projectile, Attach(stale.Projectile));
        Equal(2, pool.Reserve(2), "host incarnation replacement releases stale occupancy"); pool.Return(2);
        var lifetime = new RuntimeSpawnBudget(32);
        for (int i = 0; i < 32; i++) {
            Equal(1, lifetime.Reserve(1), "retained lifetime admits initial allowance");
            SentryLifeHost(data, child, lifetime, 1, true, 1).OnKill(50);
        }
        Equal(0, lifetime.Reserve(1), "retained lifetime is not refilled by death");
    }

    private static void SentryDescendantPoolsPreserveEveryAncestor()
    {
        using var state = new SentryLifeScope();
        var ancestor = new RuntimeSpawnBudget(2, concurrent: true);
        var nested = new RuntimeSpawnBudget(9, concurrent: true, parent: ancestor);
        Equal(2, nested.Reserve(4), "larger nested cap cannot exceed ancestor");
        var a = new Projectile { active = true }; var b = new Projectile { active = true };
        var first = nested.TrackLive(a, () => true); var second = nested.TrackLive(b, () => true);
        Equal(0, ancestor.Remaining, "grandchildren occupy ancestor capacity");
        Equal(0, nested.Reserve(1), "ancestor saturation fences all nested producers");
        first.Release(); first.Release();
        Equal(1, ancestor.Remaining, "nested retirement refunds ancestor once"); Equal(8, nested.Remaining, "nested retirement refunds own pool once");
        second.Release(); Equal(2, ancestor.Remaining, "all retired descendant capacity restored");
        var lifetime = new RuntimeSpawnBudget(2); var bounded = new RuntimeSpawnBudget(9, concurrent: true, parent: lifetime);
        Equal(2, bounded.Reserve(2), "nested explicit pool reserves lifetime ancestor");
        bounded.TrackLive(a, () => true).Release(); bounded.TrackLive(b, () => true).Release();
        Equal(9, bounded.Remaining, "nested concurrent capacity refills"); Equal(0, lifetime.Remaining, "ancestor lifetime capacity does not refill");
        Equal(0, bounded.Reserve(1), "nested declaration cannot restart exhausted lifetime ancestor");
        var data = RootSpawnFixture(32, 1); var child = Entity(); child.Spawn.DescendantMaxActive = 9;
        ancestor = new RuntimeSpawnBudget(2, concurrent: true); ancestor.Reserve(1);
        var host = SentryLifeHost(data, child, ancestor, 1, true);
        Equal(1, SentryLifeBudget(host).Reserve(3), "actual Configure retains incoming ancestry when creating nested pool");
        Equal(0, ancestor.Remaining, "physical nested source and its child both occupy ancestor");
    }

    private static void SentryDescendantPoolPendingAndHydration()
    {
        using var state = new SentryLifeScope(); using var clock = new RuntimeWorldClockScope();
        var data = RootSpawnFixture(32, 1); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Spawn.DescendantMaxActive = 2;
        var host = SentryLifeHost(data, entity); var pool = SentryLifeBudget(host);
        var action = new RuntimeEventActionSpec { Id = "pending_pool", Event = RuntimeEventKind.Periodic,
            ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = "root", Count = 2, DelayTicks = 2 };
        var source = new EntitySource_Misc("InfiniRuntimePeriodic");
        bool Schedule() => RuntimeDelayedActionScheduler.TrySchedule(data, data.RuntimeProgram.Entities[0], action,
            state.Owner, source, Vector2.Zero, Vector2.UnitX, null, 0, data.RuntimeProgram.Limits.MaxChildDepth, pool);
        Equal(true, Schedule(), "pending descendant request admitted"); Equal(0, pool.Remaining, "pending reserves live pool capacity");
        Equal(false, Schedule(), "pending saturation blocks another admission");
        AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
        Equal(2, pool.Remaining, "actual late depth refusal refunds reservation");
        Equal(true, Schedule(), "pool reopens after refused delayed spawn"); RuntimeDelayedActionScheduler.Clear(); RuntimeDelayedActionScheduler.Clear();
        Equal(2, pool.Remaining, "scheduler cancellation refunds once");
        pool.Reserve(1);
        host.Configure(data, entity, 0, 96, Vector2.UnitX, preserveSyncedState: true);
        Equal(true, ReferenceEquals(pool, SentryLifeBudget(host)), "owner hydration retains exact pool identity");
        Equal(1, pool.Remaining, "owner hydration cannot refill consumed reservation");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
        var remote = SentryLifeHost(data, entity, slot: 1);
        var field = typeof(GeneratedProjectile).GetField("_activationSpawnBudget", SentryLifePrivate)!;
        Equal(true, field.GetValue(remote) is null, "fresh remote metadata creates no pool");
        remote.Configure(data, entity, 0, 80, Vector2.UnitX, preserveSyncedState: true);
        Equal(true, field.GetValue(remote) is null, "remote hydration never turns observation into authority");
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) remote.SendExtraAI(writer);
        stream.Position = 0; using var reader = new BinaryReader(stream);
        reader.ReadByte(); reader.ReadString(); reader.ReadString(); reader.ReadByte();
        Equal((byte)80, reader.ReadByte(), "concurrent-cap peer snapshot retains admitted observational range");
    }

    private sealed class SentrySpawnProbeFailure : Exception { }
    private static void SentryDescendantPoolNativeFailureRefundsUnusedSlots()
    {
        using var state = new SentryLifeScope();
        var data = RootSpawnFixture(32, 1); int attempts = 0;
        var pool = new RuntimeSpawnBudget(3, concurrent: true); Equal(3, pool.Reserve(3), "reserve native batch");
        using var native = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
            new[] { typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                if (++attempts == 2) throw new SentrySpawnProbeFailure();
                var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = true, owner = owner, Center = position };
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, Attach(projectile));
                return projectile;
            }));
        try {
            GeneratedProjectile.SpawnRuntimeEntity(data, "root", state.Owner, state.Owner.GetSource_Misc("native failure"),
                Vector2.Zero, Vector2.UnitX, 1, 3, requestedCount: 3, activationBudget: pool);
            throw new InvalidOperationException("native probe failure was hidden");
        }
        catch (SentrySpawnProbeFailure) { }
        Equal(2, pool.Remaining, "exception refunds two unused reservations while first host remains live");
        ((GeneratedProjectile)Terraria.Main.projectile[0].ModProjectile).OnKill(50);
        Equal(3, pool.Remaining, "successful first host owns the remaining exact lease");
    }
}
