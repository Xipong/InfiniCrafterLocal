#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private const string TargetEmissionBoundary = "observed target emission native entry";

    private static RuntimeEventActionSpec TargetEmissionAction(string anchor = "previous_target", string repeats = "allow_revisits",
        bool los = false, int count = 2, int delay = 0, int ignore = 10, string eventName = "on_hit")
        => new() { Id = "hop_action", Event = eventName, Action = "select_targets_and_emit_on_event",
            ActionCode = RuntimeEventActionCode.SelectTargetsAndEmit, EntityId = "hop", StepCount = count,
            StepRangeTiles = 22.5, SelectionAnchor = anchor, RepeatPolicy = repeats,
            RequireLineOfSight = los, InitialIgnoreCountdownUpdates = ignore, DelayTicks = delay };

    private static GeneratedItemData TargetEmissionFixture(int delay = 0, string eventName = "on_hit")
    {
        var data = SwarmGameplayFixture();
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        var child = JsonSerializer.Deserialize<RuntimeEntitySpec>(JsonSerializer.Serialize(root))!;
        child.Id = "hop"; child.Kind = RuntimeEntityKind.ChildProjectile;
        child.Visual.Role = child.VisualRole = "child_projectile";
        child.Spawn.Placement = "item_use_origin"; child.Spawn.Aim = "velocity"; child.Spawn.OffsetPx = 0;
        child.Spawn.Count = 4; child.Spawn.SpreadRadians = 0.7f; child.Spawn.SpeedPxPerTick = 7;
        child.Damage.Damage = 17; child.Damage.Knockback = 2.5f;
        root.Events = new[] { TargetEmissionAction(delay: delay, eventName: eventName) };
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(child).ToArray();
        return SwarmWire(data);
    }

    private static NPC TargetEmissionNpc(int slot, float x, float y = 0)
    {
        NPC npc = Rt01Npc(slot); npc.Center = new Vector2(x, y);
        Rt01ReceiveToken(npc, (uint)(slot + 71));
        return npc;
    }

    private static Hook TargetEmissionEntry(Action<IEntitySource, Vector2, Vector2, int, float> inspect)
        => new(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect), new[] {
            typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float),
            typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                inspect(source, position, velocity, damage, knockback);
                // Observe the production boundary; never return a synthetic
                // projectile in place of native registered world creation.
                throw new InvalidOperationException(TargetEmissionBoundary);
            }));

    private static bool ObserveTargetEmission(Action dispatch)
    {
        try { dispatch(); return false; }
        catch (InvalidOperationException error) when (error.Message == TargetEmissionBoundary) { return true; }
    }

    private static void TargetEmissionWireIsStrictAndOldOpcodesStayAbsent()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        var data = TargetEmissionFixture();
        foreach (string json in new[] { data.ToJson(), data.ToNetworkJson(), JsonSerializer.Serialize(data) })
        {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("explicit target emission roundtrip refused");
            var action = copy.RuntimeProgram.TryGetEntity("root")!.Events.Single();
            Equal(2, action.StepCount!.Value, "explicit count roundtrip");
            Equal(22.5, action.StepRangeTiles!.Value, "float64 range roundtrip");
            Equal("previous_target", action.SelectionAnchor!, "anchor roundtrip");
            Equal("allow_revisits", action.RepeatPolicy!, "repeat policy roundtrip");
            Equal(false, action.RequireLineOfSight!.Value, "explicit false roundtrip");
            Equal(10, action.InitialIgnoreCountdownUpdates!.Value, "counter roundtrip");
            Equal(0, action.DelayTicks, "explicit zero delay roundtrip");
        }
        string pristine = data.ToJson();
        foreach (string field in new[] { "event", "entityId", "stepCount", "stepRangeTiles", "selectionAnchor",
            "repeatPolicy", "requireLineOfSight", "initialIgnoreCountdownUpdates", "delayTicks" })
        {
            var raw = JsonNode.Parse(pristine)!;
            raw["runtimeProgram"]!["entities"]![1]!["events"]![0]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "missing explicit field refused " + field);
        }
        foreach (var invalid in new (string Field, string Json)[] {
            ("stepCount", "null"), ("stepCount", "0"), ("stepCount", "13"), ("stepCount", "2.0"), ("stepCount", "true"),
            ("stepRangeTiles", "0.9999999999999999"), ("stepRangeTiles", "60.00000000000001"), ("stepRangeTiles", "null"),
            ("selectionAnchor", "\"closest\""), ("repeatPolicy", "null"), ("requireLineOfSight", "0"),
            ("initialIgnoreCountdownUpdates", "601"), ("initialIgnoreCountdownUpdates", "-1"), ("delayTicks", "601"),
            ("event", "\"on_kill\""), ("event", "\"ON_HIT\""), ("entityId", "\"HOP\""),
            ("damageMultiplier", "0.75"), ("count", "2"), ("actionCode", "4"), ("action", "\"chain_damage_on_event\""),
        })
        {
            var raw = JsonNode.Parse(pristine)!;
            raw["runtimeProgram"]!["entities"]![1]!["events"]![0]![invalid.Field] = JsonNode.Parse(invalid.Json);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "present invalid target emission refused " + invalid);
        }
        var old = SwarmGameplayFixture();
        old.RuntimeProgram.TryGetEntity("root")!.Events = new[] { new RuntimeEventActionSpec {
            Id = "old_radial", Event = "on_hit", Action = "chain_damage_on_event", ActionCode = RuntimeEventActionCode.ChainDamage,
            Count = 2, RangeTiles = 22.5f, DamageMultiplier = 0.5f, DelayTicks = 0,
        } };
        string oldJson = SwarmWire(old).ToJson();
        Equal(false, oldJson.Contains("stepCount", StringComparison.Ordinal), "legacy action has no invented new fields");
        var oldRaw = JsonNode.Parse(oldJson)!;
        oldRaw["runtimeProgram"]!["entities"]![1]!["events"]![0]!["stepCount"] = 1;
        Equal(true, GeneratedItemData.FromJson(oldRaw.ToJsonString()) is null, "new fields cannot attach to another opcode");
        var incompatible = JsonNode.Parse(pristine)!;
        incompatible["runtimeProgram"]!["entities"]![2]!["spawn"]!["aim"] = "cursor";
        Equal(true, GeneratedItemData.FromJson(incompatible.ToJsonString()) is null, "referenced child has exact initial geometry contract");
        foreach (string field in new[] { "aim", "placement", "offsetPx" })
        {
            var missing = JsonNode.Parse(pristine)!;
            missing["runtimeProgram"]!["entities"]![2]!["spawn"]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(missing.ToJsonString()) is null, "missing referenced origin choice cannot use retained defaults " + field);
        }
        foreach (var change in new (string Field, string Json)[] { ("aim", "\"VELOCITY\""),
            ("placement", "\"ITEM_USE_ORIGIN\""), ("offsetPx", "null"), ("overTarget", "{\"heightTiles\":-1,\"delayTicks\":0}") })
        {
            var raw = JsonNode.Parse(pristine)!;
            raw["runtimeProgram"]!["entities"]![2]!["spawn"]![change.Field] = JsonNode.Parse(change.Json);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid referenced origin refuses before retained normalization " + change.Field);
        }
    }

    private static void TargetEmissionPlannerUsesExplicitAnchorsAndRepeatPolicy()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        NPC a = TargetEmissionNpc(0, 0), b = TargetEmissionNpc(1, 300), c = TargetEmissionNpc(2, 550);
        int[] health = { a.life, b.life, c.life };
        foreach (string anchor in new[] { "previous_target", "event_target" })
        foreach (string repeats in new[] { "allow_revisits", "exclude_visited" })
        {
            var action = TargetEmissionAction(anchor, repeats, count: 4);
            action.NormalizeAndValidate();
            var steps = RuntimeProgramExecutor.PlanTargetEmissions(action, a, 4);
            int[] expected = anchor == "event_target"
                ? repeats == "allow_revisits" ? new[] { 1, 1, 1, 1 } : new[] { 1 }
                : repeats == "allow_revisits" ? new[] { 1, 2, 1, 2 } : new[] { 1, 2 };
            Equal(string.Join(",", expected), string.Join(",", steps.Select(step => step.TargetNpcSlot)), "actual planner " + anchor + "/" + repeats);
            Equal(a.Center, steps[0].Transform.Position, "first emission starts at event NPC");
            if (steps.Count > 1)
                Equal(anchor == "previous_target" ? b.Center : a.Center, steps[1].Transform.Position, "selected origin advances only when authored");
            Equal(0, steps[0].Exclusion.NpcSlot, "exact first emission-anchor exclusion");
            Equal(10, steps[0].Exclusion.RemainingUpdates, "explicit initial countdown");
            Equal(1, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1).Count, "shared remaining budget bounds planned links");
        }
        Equal(string.Join(",", health), string.Join(",", new[] { a.life, b.life, c.life }), "planning does not apply radial damage");
        a.active = false;
        Equal(2, RuntimeProgramExecutor.PlanTargetEmissions(TargetEmissionAction(), a, 2).Count,
            "immediate lethal hit may retain its exact physical anchor");
        a.active = true; Rt01ReceiveToken(a, 0);
        Equal(0, RuntimeProgramExecutor.PlanTargetEmissions(TargetEmissionAction(), a, 2).Count, "positive ignore needs known anchor incarnation");
        Equal(2, RuntimeProgramExecutor.PlanTargetEmissions(TargetEmissionAction(ignore: 0), a, 2).Count, "explicit zero has no hidden exclusion requirement");
    }

    private static void TargetEmissionPlannerUsesInclusiveRangeExactTiesAndLos()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        NPC a = TargetEmissionNpc(0, 0), b = TargetEmissionNpc(1, 360), c = TargetEmissionNpc(2, -360);
        TargetEmissionNpc(3, 0); // coincident center has no direction
        TargetEmissionNpc(4, 20).active = false;
        TargetEmissionNpc(5, 10).dontTakeDamage = true;
        var action = TargetEmissionAction(count: 1, ignore: 0);
        var steps = RuntimeProgramExecutor.PlanTargetEmissions(action, a, 12);
        Equal(1, steps[0].TargetNpcSlot, "inclusive radius and lower-slot exact-distance tie");
        b.Center = new Vector2(360.01f, 0);
        Equal(2, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1)[0].TargetNpcSlot, "outside radius excluded");
        action.StepRangeTiles = 1;
        b.Center = new Vector2(16, 0.001f); c.Center = new Vector2(16, 0);
        Equal(2, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1)[0].TargetNpcSlot,
            "original float coordinates outside radius cannot round inside or win a false tie");
        c.active = false;
        Equal(0, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1).Count, "nearby raw outside radius refused");
        c.active = true; action.StepRangeTiles = 22.5;
        b.Center = new Vector2(360, 0); c.Center = new Vector2(-360, 0);
        int calls = 0;
        using var lineOfSight = new Hook(typeof(Collision).GetMethod(nameof(Collision.CanHit),
            new[] { typeof(Vector2), typeof(int), typeof(int), typeof(Vector2), typeof(int), typeof(int) })!,
            (Func<Vector2, int, int, Vector2, int, int, bool>)((origin, width, height, target, targetWidth, targetHeight) => {
                calls++;
                Equal(a.position, origin, "LOS source uses anchor hitbox");
                Equal(a.width, width, "LOS source width"); Equal(a.height, height, "LOS source height");
                return target == c.position;
            }));
        Equal(1, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1)[0].TargetNpcSlot, "false does not request LOS");
        Equal(0, calls, "LOS flag is independent and explicit");
        action.RequireLineOfSight = true;
        Equal(2, RuntimeProgramExecutor.PlanTargetEmissions(action, a, 1)[0].TargetNpcSlot, "native CanHit decision filters the nearest candidate");
        Equal(true, calls >= 2, "actual native LOS entry examined both candidates");
    }

    private static void TargetEmissionRealHitHookKeepsAuthorityStatsAndReservation()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        NPC a = TargetEmissionNpc(0, 0); TargetEmissionNpc(1, 300); TargetEmissionNpc(2, 550);
        foreach (var role in SwarmRoles)
        foreach (string hitEvent in new[] { "on_hit", "on_crit" })
        {
            Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
            var data = TargetEmissionFixture(eventName: hitEvent); var root = data.RuntimeProgram.TryGetEntity("root")!;
            var host = SwarmHost(data, root, damage: 777, knockback: 9);
            var budget = (RuntimeSpawnBudget)typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(host)!;
            int entryCount = 0; int beforeHealth = Terraria.Main.npc[1].life;
            using var entry = TargetEmissionEntry((source, position, velocity, damage, knockback) => {
                entryCount++; Equal(true, source is EntitySource_Parent parent && ReferenceEquals(parent.Entity, host.Projectile), "exact physical hit parent preserved");
                Equal(a.Center, position, "first child starts at source NPC"); Equal(new Vector2(7, 0), velocity, "own child speed, one link axis without child spread");
                Equal(17, damage, "authored child damage independent of live parent/damageDone"); Equal(2.5f, knockback, "authored child knockback");
            });
            bool observed = ObserveTargetEmission(() => host.OnHitNPC(a, new NPC.HitInfo { Crit = hitEvent == "on_crit" }, 333));
            bool owner = role.Name is "SP" or "owner-client";
            Equal(owner, observed, "only owner hit hook reaches physical spawn " + role.Name);
            Equal(owner ? 1 : 0, entryCount, "no remote replay of child creation " + role.Name);
            Equal(8, budget.Remaining, "first native exception refunds attempted plus unattempted links exactly once");
            Equal(beforeHealth, Terraria.Main.npc[1].life, "dispatch never substitutes instant direct damage");
        }
    }

    private static void TargetEmissionNormalRefusalsReturnUnspentPlanBudget()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        NPC a = TargetEmissionNpc(0, 0); NPC b = TargetEmissionNpc(1, 300);
        var data = TargetEmissionFixture(); var root = data.RuntimeProgram.TryGetEntity("root")!;
        var child = data.RuntimeProgram.TryGetEntity("hop")!; child.Spawn.MaxActive = 1;
        var owner = Terraria.Main.player[0]; var source = owner.GetSource_Misc("target emission refusal");
        var budget = new RuntimeSpawnBudget(5);
        var occupied = SwarmHost(data, child, slot: 5);
        RuntimeProgramExecutor.ExecuteAction(data, root, root.Events[0], owner, source, a.Center, Vector2.UnitX, a, 0, 0, budget);
        Equal(5, budget.Remaining, "child concurrency refusal returns attempted and unattempted links");
        occupied.Projectile.active = false; b.active = false;
        RuntimeProgramExecutor.ExecuteAction(data, root, root.Events[0], owner, source, a.Center, Vector2.UnitX, a, 0, 0, budget);
        Equal(5, budget.Remaining, "empty target set returns entire reservation");
        b.active = true;
        int reserved = budget.Reserve(2);
        RuntimeProgramExecutor.ExecuteAction(data, root, root.Events[0], owner, source, a.Center, Vector2.UnitX, a, 0,
            data.RuntimeProgram.Limits.MaxChildDepth, budget, reserved);
        Equal(5, budget.Remaining, "child depth refusal returns already reserved delayed allowance");
        var zero = new RuntimeSpawnBudget(0);
        RuntimeProgramExecutor.ExecuteAction(data, root, root.Events[0], owner, source, a.Center, Vector2.UnitX, a, 0, 0, zero);
        Equal(0, zero.Remaining, "exhausted activation creates no physical child or new budget");
        var collider = SwarmHost(data, child, slot: 6);
        RuntimeInitialNpcExclusion.TryCapture(a, 2, out var exclusion); collider.SetInitialNpcExclusion(exclusion);
        Equal((bool?)false, collider.CanHitNPC(a), "each child owns exact initial exclusion");
        Equal((bool?)null, collider.CanHitNPC(b), "other NPC collision remains native");
        Equal((bool?)null, collider.Colliding(collider.Projectile.Hitbox, b.Hitbox), "ordinary child uses native projectile hitbox collision");
        collider.AI(); collider.AI();
        Equal((bool?)null, collider.CanHitNPC(a), "later source collision follows explicit counter expiry");
    }

    private static void TargetEmissionDelayedDispatchRequiresSameActiveNpcAndRefundsCancellation()
    {
        using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
        foreach (string transition in new[] { "same", "transform", "inactive", "reference-replacement", "setdefaults-same-type-new-token", "token-cleared" })
        {
            RuntimeDelayedActionScheduler.Clear(); MaterialClock(uint.MaxValue - 1);
            NPC a = TargetEmissionNpc(0, 0); TargetEmissionNpc(1, 300); TargetEmissionNpc(2, 550);
            var data = TargetEmissionFixture(delay: 2); var root = data.RuntimeProgram.TryGetEntity("root")!;
            var host = SwarmHost(data, root); var owner = Terraria.Main.player[0];
            var budget = new RuntimeSpawnBudget(5);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, root, root.Events[0], owner, host.Projectile.GetSource_FromThis(),
                a.Center, Vector2.UnitX, a, 777, 0, budget), "exact source admitted " + transition);
            Equal(3, budget.Remaining, "all possible children reserved at admission");
            RuntimeDelayedActionScheduler.Update(); Equal(3, budget.Remaining, "same world update does not dispatch");
            bool current = Rt01Transition(a, transition, 71);
            if (current) a.Center = new Vector2(10, 0); // geometry is sampled at dispatch
            int calls = 0;
            using var entry = TargetEmissionEntry((source, position, velocity, damage, knockback) => {
                calls++; Equal(new Vector2(10, 0), position, "delayed dispatch samples current exact anchor position");
            });
            MaterialClock(uint.MaxValue); Equal(false, ObserveTargetEmission(RuntimeDelayedActionScheduler.Update), "delay not prematurely consumed at wrap");
            MaterialClock(0); Equal(current, ObserveTargetEmission(RuntimeDelayedActionScheduler.Update), "only same active incarnation dispatches " + transition);
            Equal(current ? 1 : 0, calls, "cancelled NPC never becomes a different initial target");
            Equal(5, budget.Remaining, "cancel/refused native entry returns complete pending allowance");
        }
        RuntimeDelayedActionScheduler.Clear();
        var finalData = TargetEmissionFixture(delay: 2); var finalRoot = finalData.RuntimeProgram.TryGetEntity("root")!;
        var finalHost = SwarmHost(finalData, finalRoot); NPC unknown = TargetEmissionNpc(0, 0); Rt01ReceiveToken(unknown, 0);
        var remaining = new RuntimeSpawnBudget(5);
        Equal(false, RuntimeDelayedActionScheduler.TrySchedule(finalData, finalRoot, finalRoot.Events[0], Terraria.Main.player[0],
            finalHost.Projectile.GetSource_FromThis(), unknown.Center, Vector2.UnitX, unknown, 0, 0, remaining), "unknown initial generation refuses before reservation");
        Equal(5, remaining.Remaining, "refused admission does not leak reservation");
    }
}
