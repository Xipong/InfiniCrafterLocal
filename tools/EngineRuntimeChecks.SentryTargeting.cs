using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
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
    private const BindingFlags SentryPrivate = BindingFlags.NonPublic | BindingFlags.Instance;

    private static GeneratedItemData SentryTargetingFixture()
    {
        var data = RootSpawnFixture(12, 1);
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Controller = new RuntimeControllerSpec { Name = "target_and_fire", Code = RuntimeControllerCode.TargetAndFire };
        root.Targeting = new RuntimeTargetingSpec { ShotEntityId = "shot", IntervalTicks = 6, RangeTiles = 10,
            SameTargetBias = 0.9f, Count = 4, SpreadRadians = 0.6, TargetPolicy = "player_assigned_first",
            RequireLineOfSight = true, HardRange = true };
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(new RuntimeEntitySpec {
            Id = "shot", Kind = RuntimeEntityKind.ChildProjectile, VisualRole = "child_projectile",
            Visual = new RuntimeEntityVisualSpec { Role = "child_projectile", AssetMode = "no_asset" },
            Spawn = new RuntimeSpawnSpec { Enabled = true, Count = 9, SpreadRadians = 2f,
                Placement = "item_use_origin", Aim = "velocity", SpeedPxPerTick = 10f },
            Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 },
        }).ToArray();
        return data;
    }

    private sealed class SentryTargetScope : IDisposable
    {
        private readonly int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        private readonly NPC[] oldNpcs = Terraria.Main.npc;
        private readonly Projectile[] oldProjectiles = Terraria.Main.projectile;
        private readonly Player oldOwner = Terraria.Main.player[0];
        internal readonly Player Owner;
        internal SentryTargetScope()
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            Owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, direction = 1 };
            Owner.MinionAttackTargetNPC = -1;
            Terraria.Main.npc = Enumerable.Range(0, oldNpcs.Length).Select(i => new NPC { whoAmI = i, active = false }).ToArray();
            Terraria.Main.projectile = Enumerable.Range(0, oldProjectiles.Length).Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
        }
        internal NPC Target(int index, float distance)
        {
            var npc = Terraria.Main.npc[index] = new NPC { whoAmI = index, active = true, life = 100, lifeMax = 100,
                width = 20, height = 20, Center = new Vector2(1600f + distance, 1600f) };
            Equal(true, npc.CanBeChasedBy(), "native target fixture is chaseable");
            return npc;
        }
        public void Dispose()
        {
            Terraria.Main.npc = oldNpcs; Terraria.Main.projectile = oldProjectiles; Terraria.Main.player[0] = oldOwner;
            Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal;
        }
    }

    private static void SentryTargetPolicyUsesExactAssignedNpcAndFilters()
    {
        using var state = new SentryTargetScope();
        var projectile = new Projectile { owner = 0, active = true, width = 30, height = 40, Center = new Vector2(1600f, 1600f) };
        var generated = Attach(projectile);
        NPC near = state.Target(0, 30f), assigned = state.Target(1, 120f), outside = state.Target(2, 300f);
        var target = SentryTargetingFixture().RuntimeProgram.TryGetEntity("root")!.Targeting;
        MethodInfo find = typeof(GeneratedProjectile).GetMethod("FindFiringTarget", SentryPrivate)!;
        FieldInfo last = typeof(GeneratedProjectile).GetField("_lastTarget", SentryPrivate)!;
        NPC? Pick() => (NPC?)find.Invoke(generated, new object[] { 160f, target });
        var blocked = new HashSet<Vector2>();
        int losCalls = 0;
        using var los = new Hook(typeof(Collision).GetMethod(nameof(Collision.CanHit),
            new[] { typeof(Vector2), typeof(int), typeof(int), typeof(Vector2), typeof(int), typeof(int) })!,
            (Func<Vector2, int, int, Vector2, int, int, bool>)((from, width, height, to, targetWidth, targetHeight) => {
                Equal(projectile.position, from, "LOS starts at projectile hitbox");
                Equal(30, width, "LOS uses actual projectile width"); Equal(40, height, "LOS uses actual projectile height");
                Equal(20, targetWidth, "LOS uses NPC width"); Equal(20, targetHeight, "LOS uses NPC height");
                losCalls++; return !blocked.Contains(to);
            }));
        state.Owner.MinionAttackTargetNPC = assigned.whoAmI;
        Equal(true, ReferenceEquals(assigned, Pick()), "exact assigned NPC wins over nearer candidate");
        blocked.Add(assigned.position);
        Equal(true, ReferenceEquals(near, Pick()), "blocked assigned NPC falls through same LOS filter");
        blocked.Add(near.position);
        Equal(true, Pick() is null, "all in-range blocked targets refuse firing");
        blocked.Clear();
        state.Owner.MinionAttackTargetNPC = outside.whoAmI;
        last.SetValue(generated, outside.whoAmI);
        Equal(true, ReferenceEquals(near, Pick()), "assigned and previous bias cannot bypass hard geometric radius");
        near.active = false;
        assigned.active = false;
        Equal(true, Pick() is null, "previous target outside hard radius remains refused");
        target.HardRange = false;
        Equal(true, ReferenceEquals(outside, Pick()), "retained soft-score mode admits discounted previous target");
        target.HardRange = true;
        outside.Center = projectile.Center + Vector2.UnitX * 160f;
        Equal(true, ReferenceEquals(outside, Pick()), "hard range includes exact geometric boundary");
        target.TargetPolicy = "distance_score"; near.active = true; assigned.active = true;
        state.Owner.MinionAttackTargetNPC = assigned.whoAmI;
        last.SetValue(generated, -1);
        Equal(true, ReferenceEquals(near, Pick()), "distance-score policy ignores assigned preference");
        target.RequireLineOfSight = false; blocked.Add(near.position); int before = losCalls;
        Equal(true, ReferenceEquals(near, Pick()), "explicit no-LOS mode preserves wall-independent selection");
        Equal(before, losCalls, "disabled LOS makes no native geometry call");
    }

    private static void SentryVolleyUsesAuthoredCountAndSpreadAtNativeBoundary()
    {
        using var state = new SentryTargetScope();
        state.Target(0, 100f);
        var data = SentryTargetingFixture(); var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Targeting.RequireLineOfSight = false;
        var projectile = new Projectile { owner = 0, active = true };
        var generated = Attach(projectile); var budget = new RuntimeSpawnBudget(12);
        generated.Configure(data, root, 0, 12, Vector2.UnitX, activationBudget: budget);
        projectile.Center = new Vector2(1600f, 1600f);
        var observed = new List<Vector2>();
        // Observe real canonical spawn-loop arguments. Return an unregistered
        // projectile, so no successful game spawn is claimed by this CPU check.
        using var native = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
            new[] { typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, ai0, ai1, ai2) => {
                Equal(projectile.Center, position, "child item_use_origin uses firing center");
                Equal(0, owner, "owner authority is retained"); observed.Add(velocity); return new Projectile();
            }));
        MethodInfo fire = typeof(GeneratedProjectile).GetMethod("ApplyTargetAndFire", SentryPrivate)!;
        FieldInfo timer = typeof(GeneratedProjectile).GetField("_controllerTimer", SentryPrivate)!;
        void Volley() { timer.SetValue(generated, 5); fire.Invoke(generated, null); }
        Volley();
        Equal(4, observed.Count, "controller count overrides independently authored child count nine");
        for (int i = 0; i < observed.Count; i++) {
            float expected = -0.3f + i * 0.2f;
            Equal(true, Math.Abs(observed[i].ToRotation() - expected) < 1e-5f, "exact symmetric volley angle " + i);
            Equal(true, Math.Abs(observed[i].Length() - 10f) < 1e-5f, "child authored launch speed remains literal");
        }
        Equal(12, budget.Remaining, "unregistered native results refund unused reservation");
        observed.Clear(); root.Targeting.Count = 1; Volley();
        Equal(1, observed.Count, "single-shot mode stays single"); Equal(0f, observed[0].ToRotation(), "single shot has no fan offset");
        observed.Clear(); Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1; Volley();
        Equal(0, observed.Count, "remote projectile cannot fire or acquire owner-local budget");
        Equal(12, budget.Remaining, "remote peer preserves owner ledger");
    }

    private static void SentryTargetingDtoPreservesChoicesAndRejectsInvalidPresence()
    {
        var data = SentryTargetingFixture();
        foreach (string json in new[] { data.ToJson(), data.ToNetworkJson() }) {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("targeting fixture rejected");
            var target = copy.RuntimeProgram.TryGetEntity("root")!.Targeting;
            Equal(4, target.Count, "count survives serialized DTO"); Equal(0.6, target.SpreadRadians, "spread survives serialized DTO");
            Equal("player_assigned_first", target.TargetPolicy, "assigned policy survives serialized DTO");
            Equal(true, target.RequireLineOfSight && target.HardRange, "filters survive serialized DTO");
        }
        var raw = JsonNode.Parse(data.ToJson())!.AsObject(); var fields = raw["runtimeProgram"]!["entities"]![1]!["targeting"]!.AsObject();
        foreach (string name in new[] { "count", "spreadRadians", "targetPolicy", "requireLineOfSight", "hardRange" }) fields.Remove(name);
        var legacy = GeneratedItemData.FromJson(raw.ToJsonString()) ?? throw new InvalidOperationException("retained wire absence rejected");
        var kept = legacy.RuntimeProgram.TryGetEntity("root")!.Targeting;
        Equal(1, kept.Count, "retained count defaults to former one shot"); Equal(0d, kept.SpreadRadians, "retained spread neutral");
        Equal("distance_score", kept.TargetPolicy, "retained target policy"); Equal(false, kept.RequireLineOfSight || kept.HardRange, "retained soft score and no LOS");
        foreach (var (key, value) in new[] { ("count", "0"), ("count", "5"), ("count", "null"), ("count", "true"),
            ("spreadRadians", "-0.1"), ("spreadRadians", "0.8"), ("spreadRadians", "1e-50"), ("spreadRadians", "null"),
            ("targetPolicy", "\"nearest\""), ("targetPolicy", "null"), ("requireLineOfSight", "null"), ("hardRange", "1") }) {
            fields[key] = JsonNode.Parse(value);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid explicit targeting refused " + key + "=" + value);
            fields.Remove(key);
        }
    }
}
