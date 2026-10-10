using System;
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
    private static GeneratedItemData ChildCombatFixture(bool targeting = false)
    {
        var data = SwarmGameplayFixture();
        var parent = data.RuntimeProgram.TryGetEntity("root")!;
        var child = JsonSerializer.Deserialize<RuntimeEntitySpec>(JsonSerializer.Serialize(parent))!;
        child.Id = "child";
        child.Kind = RuntimeEntityKind.ChildProjectile;
        child.Visual.Role = child.VisualRole = "child_projectile";
        child.Damage.Damage = 23;
        child.Damage.Knockback = 2.5f;
        child.Damage.DamageClass = "magic";
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(child).ToArray();
        parent.Events = new[] { new RuntimeEventActionSpec {
            Id = "child_event", Event = RuntimeEventKind.OnHit,
            Action = "spawn_entity_on_event", ActionCode = RuntimeEventActionCode.SpawnEntity,
            EntityId = "child", Count = 1, DamageMultiplier = 0.5f,
            DamageBasis = RuntimeChildCombatBasis.LiveParent,
            KnockbackBasis = RuntimeChildCombatBasis.LiveParent,
        } };
        if (targeting)
        {
            parent.Kind = RuntimeEntityKind.StationaryProjectile;
            parent.Visual.Role = parent.VisualRole = "deployed_entity";
            parent.Controller.Name = "target_and_fire";
            parent.Controller.Code = RuntimeControllerCode.TargetAndFire;
            parent.Targeting = new RuntimeTargetingSpec {
                ShotEntityId = "child", IntervalTicks = 6, RangeTiles = 20,
                DamageBasis = RuntimeChildCombatBasis.LiveParent,
                KnockbackBasis = RuntimeChildCombatBasis.LiveParent, DamageMultiplier = 0.5f,
            };
        }
        return SwarmWire(data);
    }

    private static void ChildCombatSavedWireIsStrictAndPreservesAbsence()
    {
        using var scope = new SwarmRuntimeScope();
        var data = ChildCombatFixture(targeting: true);
        var raw = JsonNode.Parse(data.ToNetworkJson())!;
        var parent = raw["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "root")!;
        var action = parent["events"]![0]!.AsObject();
        var targeting = parent["targeting"]!.AsObject();
        action.Remove("damageBasis"); action.Remove("knockbackBasis");
        targeting.Remove("damageBasis"); targeting.Remove("knockbackBasis"); targeting.Remove("damageMultiplier");
        var saved = GeneratedItemData.FromJson(raw.ToJsonString())
            ?? throw new InvalidOperationException("historical child-combat absence rejected");
        foreach (string payload in new[] { saved.ToJson(), saved.ToNetworkJson() })
        {
            var copy = JsonNode.Parse(payload)!;
            var copyParent = copy["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "root")!;
            Equal(false, copyParent["events"]![0]!.AsObject().ContainsKey("damageBasis"), "old event selector absence retained");
            Equal(false, copyParent["targeting"]!.AsObject().ContainsKey("knockbackBasis"), "old targeting selector absence retained");
            Equal(false, copyParent["targeting"]!.AsObject().ContainsKey("damageMultiplier"), "old targeting multiplier absence retained");
        }
        foreach (string field in new[] { "damageBasis", "knockbackBasis" })
        foreach (string invalid in new[] { "null", "true", "0", "{}", "\"Live_Parent\"", "\" live_parent\"", "\"parent\"" })
        foreach (bool onTargeting in new[] { false, true })
        {
            var candidate = JsonNode.Parse(raw.ToJsonString())!;
            var candidateParent = candidate["runtimeProgram"]!["entities"]!.AsArray().Single(row => (string?)row!["id"] == "root")!;
            var component = onTargeting ? candidateParent["targeting"]! : candidateParent["events"]![0]!;
            component[field] = JsonNode.Parse(invalid);
            Equal(true, GeneratedItemData.FromJson(candidate.ToJsonString()) is null, "present invalid child basis rejected: " + invalid);
        }
        foreach (string invalid in new[] { "null", "true", "\"1\"", "-0.01", "4.01" })
        {
            targeting["damageMultiplier"] = JsonNode.Parse(invalid);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "present targeting multiplier rejected: " + invalid);
        }
        var inactive = ChildCombatFixture();
        var inactiveParent = inactive.RuntimeProgram.TryGetEntity("root")!;
        inactiveParent.Targeting.DamageBasis = RuntimeChildCombatBasis.LiveParent;
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        Equal(true, GeneratedItemData.FromJson(JsonSerializer.Serialize(inactive, options)) is null, "targeting basis without target_and_fire rejected");
        inactive = ChildCombatFixture(); inactiveParent = inactive.RuntimeProgram.TryGetEntity("root")!;
        inactiveParent.Events[0].ActionCode = RuntimeEventActionCode.DamageArea;
        inactiveParent.Events[0].Action = "damage_area_on_event";
        Equal(true, GeneratedItemData.FromJson(JsonSerializer.Serialize(inactive, options)) is null, "non-spawn event cannot consume child bases");
        inactive = ChildCombatFixture(); inactiveParent = inactive.RuntimeProgram.TryGetEntity("root")!;
        var body = inactive.RuntimeProgram.TryGetEntity(inactive.RuntimeProgram.ItemEntityId)!;
        body.Events = inactiveParent.Events;
        body.Events[0].Event = RuntimeEventKind.Periodic; body.Events[0].PeriodTicks = 6;
        inactiveParent.Events = Array.Empty<RuntimeEventActionSpec>();
        Equal(true, GeneratedItemData.FromJson(JsonSerializer.Serialize(inactive, options)) is null, "item body cannot claim a projectile parent");
    }

    private static void InvokeChildCombatEvent(GeneratedProjectile parent, string eventName, int damageDone = 1)
        => typeof(GeneratedProjectile).GetMethod("RunRuntimeEvent", RootPrivate)!
            .Invoke(parent, new object?[] { eventName, null, damageDone });

    // Observe the canonical NewProjectileDirect entry, then stop before an
    // unregistered game spawn. No fake projectile or success count is returned.
    private static bool ObserveChildCombatBoundary(Action invoke, Projectile parent, int damage, float knockback)
    {
        bool observed = false;
        using var observer = RootCombatSpawnObserver((source, actualDamage, actualKnockback) => {
            observed = true;
            Equal(damage, actualDamage, "selected final damage reaches native child spawn once");
            Equal(knockback, actualKnockback, "selected final knockback reaches native child spawn once");
            Equal(true, source is EntitySource_Parent origin && ReferenceEquals(parent, origin.Entity), "exact parent source retained");
            var inherited = new Projectile(); inherited.ApplyStatsFromSource(source);
            Equal(parent.CritChance, inherited.CritChance, "existing parent source crit remains intact");
            Equal(parent.ArmorPenetration, inherited.ArmorPenetration, "existing parent source armor remains intact");
        });
        try { invoke(); }
        catch (Exception error) when (RootCombatBoundary(error)) { }
        return observed;
    }

    private static void ChildCombatImmediateEventsSelectLiveOrAuthoredStatsExactlyOnce()
    {
        foreach (var role in SwarmRoles)
        foreach (bool liveDamage in new[] { false, true })
        foreach (bool liveKnockback in new[] { false, true })
        foreach (string eventName in new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit, RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = ChildCombatFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var action = entity.Events[0]; action.Event = eventName;
            action.DamageBasis = liveDamage ? RuntimeChildCombatBasis.LiveParent : RuntimeChildCombatBasis.AuthoredChild;
            action.KnockbackBasis = liveKnockback ? RuntimeChildCombatBasis.LiveParent : RuntimeChildCombatBasis.AuthoredChild;
            var generated = SwarmHost(data, entity, damage: 137, knockback: 7.25f);
            generated.Projectile.originalDamage = 9; // distinct from current final/native/charge state
            generated.Projectile.CritChance = 31; generated.Projectile.ArmorPenetration = 7;
            if (eventName is RuntimeEventKind.OnKill or RuntimeEventKind.OnExpire) generated.Projectile.active = false;
            int queries = 0;
            using var damageQuery = new Hook(typeof(Player).GetMethod(nameof(Player.GetWeaponDamage), new[] { typeof(Item), typeof(bool) })!,
                (Func<Func<Player, Item, bool, int>, Player, Item, bool, int>)((orig, owner, item, tooltip) => { queries++; return orig(owner, item, tooltip); }));
            using var knockbackQuery = new Hook(typeof(Player).GetMethod(nameof(Player.GetWeaponKnockback), new[] { typeof(Item), typeof(float) })!,
                (Func<Func<Player, Item, float, float>, Player, Item, float, float>)((orig, owner, item, kb) => { queries++; return orig(owner, item, kb); }));
            bool observed = ObserveChildCombatBoundary(() => InvokeChildCombatEvent(generated, eventName, damageDone: 997),
                generated.Projectile, liveDamage ? 68 : 12, liveKnockback ? 7.25f : 2.5f);
            Equal(role.Name is "SP" or "owner-client", observed, "only owner authority emits the child");
            Equal(0, queries, "child inheritance never queries player/class modifiers again");
        }
        foreach (bool enabled in new[] { false, true })
        foreach (int parentDamage in new[] { 0, 137 })
        foreach (float multiplier in new[] { 0f, 1f })
        {
            using var scope = new SwarmRuntimeScope();
            var data = ChildCombatFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var child = data.RuntimeProgram.TryGetEntity("child")!; child.Damage.Enabled = enabled;
            entity.Events[0].DamageMultiplier = multiplier;
            var generated = SwarmHost(data, entity, damage: parentDamage, knockback: 0f);
            int expected = enabled && multiplier == 1f ? parentDamage : 0;
            Equal(true, ObserveChildCombatBoundary(() => InvokeChildCombatEvent(generated, RuntimeEventKind.OnHit), generated.Projectile, expected, 0f), "zero/disabled damage keeps child emission");
            var configured = SwarmHost(data, child, slot: 1, damage: expected, knockback: 0f);
            Equal(expected, configured.Projectile.damage, "Configure preserves final inherited zero/native damage");
            Equal(true, ReferenceEquals(Terraria.ModLoader.DamageClass.Magic, configured.Projectile.DamageType), "child keeps its explicitly authored damage class");
        }
    }

    private static void ChildCombatDelayedAndChargeEventsCaptureAtAdmission()
    {
        foreach (bool terminal in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = ChildCombatFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var action = entity.Events[0]; action.DelayTicks = 2;
            action.Event = terminal ? RuntimeEventKind.OnKill : RuntimeEventKind.OnHit;
            var generated = SwarmHost(data, entity, damage: 137, knockback: 7.25f);
            if (terminal) generated.Projectile.active = false;
            InvokeChildCombatEvent(generated, action.Event);
            Equal(1, PendingActions(), "exact child action queued");
            generated.Projectile.damage = 999; generated.Projectile.knockBack = 30;
            AdvanceRuntimeWorldTick();
            Equal(true, ObserveChildCombatBoundary(AdvanceRuntimeWorldTick, generated.Projectile, 68, 7.25f), "delayed child uses admission snapshot after parent changes");
            Equal(0, PendingActions(), "delayed action dispatches once");
        }
        foreach (bool full in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = ChildCombatFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Controller.Name = "charge_then_release"; entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
            entity.Controller.Params.ChargeTicks = 4; entity.Controller.Params.PowerMultiplier = 2;
            entity.Events[0].Event = RuntimeEventKind.OnRelease; entity.Events[0].DelayTicks = 1;
            var generated = SwarmHost(data, entity, damage: 200, knockback: 8);
            typeof(GeneratedProjectile).GetField("_chargeTicks", RootPrivate)!.SetValue(generated, full ? 3 : 0);
            Terraria.Main.player[0].channel = false;
            generated.AI();
            Equal(full ? 400 : 250, generated.Projectile.damage, "canonical partial/full release scales parent before event");
            Equal(1, PendingActions(), "release action captures its charged parent");
            generated.Projectile.damage = 1000; generated.Projectile.knockBack = 40;
            Equal(true, ObserveChildCombatBoundary(AdvanceRuntimeWorldTick, generated.Projectile, full ? 200 : 125, full ? 16f : 10f), "release child inherits the actual charged snapshot once");
            generated.AI();
            Equal(0, PendingActions(), "released controller does not enqueue the same child again");
        }
    }

    private static void ChildCombatSentryUsesCurrentParentAndRefusalsRefundBudget()
    {
        foreach (bool live in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = ChildCombatFixture(targeting: true); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Targeting.DamageBasis = entity.Targeting.KnockbackBasis = live ? RuntimeChildCombatBasis.LiveParent : RuntimeChildCombatBasis.AuthoredChild;
            var generated = SwarmHost(data, entity, damage: 137, knockback: 7.25f);
            var npc = Terraria.Main.npc[0]; npc.SetDefaults(NPCID.BlueSlime); npc.active = true; npc.Center = generated.Projectile.Center + new Vector2(64, 0);
            typeof(GeneratedProjectile).GetField("_controllerTimer", RootPrivate)!.SetValue(generated, 5);
            Equal(true, ObserveChildCombatBoundary(() => typeof(GeneratedProjectile).GetMethod("ApplyTargetAndFire", RootPrivate)!.Invoke(generated, null),
                generated.Projectile, live ? 68 : 12, live ? 7.25f : 2.5f), "actual target acquisition/firing consumes selected combat bases");
        }
        using var refusalScope = new SwarmRuntimeScope();
        var rejected = ChildCombatFixture(); var parent = rejected.RuntimeProgram.TryGetEntity("root")!;
        var rejectedAction = parent.Events[0]; var owner = Terraria.Main.player[0];
        var budget = new RuntimeSpawnBudget(5);
        var itemSource = new EntitySource_ItemUse(owner, new Item { type = ItemID.CopperShortsword, stack = 1 });
        RuntimeProgramExecutor.ExecuteAction(rejected, parent, rejectedAction, owner, itemSource, Vector2.Zero, Vector2.UnitX, null, 1, 0, budget);
        Equal(5, budget.Remaining, "missing immediate projectile basis does not reserve budget");
        rejectedAction.DelayTicks = 2;
        Equal(false, RuntimeDelayedActionScheduler.TrySchedule(rejected, parent, rejectedAction, owner, itemSource, Vector2.Zero, Vector2.UnitX, null, 1, 0, budget), "missing delayed projectile basis fails before admission");
        Equal(5, budget.Remaining, "missing delayed basis does not reserve budget");
        var generatedParent = SwarmHost(rejected, parent, damage: int.MaxValue);
        rejectedAction.DamageMultiplier = 4;
        RuntimeProgramExecutor.ExecuteAction(rejected, parent, rejectedAction, owner, generatedParent.Projectile.GetSource_FromThis(), Vector2.Zero, Vector2.UnitX, null, 1, 0, budget);
        Equal(5, budget.Remaining, "unrepresentable final damage is refused without authored fallback");
        rejectedAction.DamageMultiplier = 0.5f;
        generatedParent.Projectile.damage = 137; generatedParent.Projectile.knockBack = 7.25f;
        Equal(true, RuntimeDelayedActionScheduler.TrySchedule(rejected, parent, rejectedAction, owner, generatedParent.Projectile.GetSource_FromThis(), Vector2.Zero, Vector2.UnitX, null, 1, 0, budget), "valid source reserves one child");
        Equal(4, budget.Remaining, "valid child reservation");
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(generatedParent.Projectile, Attach(generatedParent.Projectile));
        AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
        Equal(5, budget.Remaining, "recycled parent generation returns its snapshot's reservation");
        Equal(0, PendingActions(), "stale snapshot cannot emit a child");
    }
}
