using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static readonly Dictionary<string, string> TimedModifierExamples = new()
    {
        ["turnModifier"] = "{\"turnRadiansPerUpdate\":0.1}",
        ["speedModifier"] = "{\"speedMultiplierPerUpdate\":1.1,\"maxSpeed\":20}",
        ["homingModifier"] = "{\"rangeTiles\":10,\"maxTurnRadiansPerUpdate\":0.1,\"requireLineOfSight\":false}",
        ["npcAttraction"] = "{\"rangeTiles\":10,\"strengthPerUpdate\":2,\"falloff\":\"constant\",\"maxTargets\":1}"
    };

    private static JsonObject TimedModifierWire(string member, bool scalars, bool window)
    {
        var root = MotionAdmissionWire("opacity");
        var body = FrontHandEntity(root);
        body.Remove("opacity");
        var value = JsonNode.Parse(TimedModifierExamples[member])!.AsObject();
        if (scalars) { value["startDelayTicks"] = 2; value["durationTicks"] = 3; }
        if (window) value["window"] = JsonNode.Parse("{\"phase\":\"always\"}");
        body[member] = value;
        return root;
    }

    private static void ModifierTimingAdmissionAndRoundtrip()
    {
        foreach (string member in TimedModifierExamples.Keys)
        {
            foreach (var shape in new[] { (Scalars: true, Window: false), (Scalars: false, Window: true), (Scalars: true, Window: true) })
            {
                var root = TimedModifierWire(member, shape.Scalars, shape.Window);
                MotionAdmits(root, member + " exact timing variant " + shape);
                var data = GeneratedItemData.FromJson(root.ToJsonString())!;
                var saved = JsonNode.Parse(data.ToJson())!.AsObject();
                var value = FrontHandEntity(saved)[member]!.AsObject();
                Equal(shape.Scalars, value.ContainsKey("startDelayTicks"), member + " scalar presence survives roundtrip");
                Equal(shape.Scalars, value.ContainsKey("durationTicks"), member + " no synthetic duration");
                Equal(shape.Window, value.ContainsKey("window"), member + " window presence survives roundtrip");
                if (shape.Scalars) {
                    Equal(2, value["startDelayTicks"]!.GetValue<int>(), member + " exact delay survives");
                    Equal(3, value["durationTicks"]!.GetValue<int>(), member + " exact duration survives");
                }
                MotionAdmits(saved, member + " serialized timing reads again");
            }
            var finite = TimedModifierWire(member, false, true);
            FrontHandEntity(finite)[member]!["window"] = JsonNode.Parse("{\"phase\":\"always\",\"clock\":\"active\",\"startDelayTicks\":2,\"durationTicks\":3}");
            MotionAdmits(finite, member + " finite window alone admits");
            var finiteData = GeneratedItemData.FromJson(finite.ToJsonString())!;
            var finiteSaved = JsonNode.Parse(finiteData.ToJson())!.AsObject();
            Equal(true, JsonNode.DeepEquals(FrontHandEntity(finite)[member], FrontHandEntity(finiteSaved)[member]), member + " finite window exact component roundtrip");
            foreach (string field in new[] { "phase", "clock", "startDelayTicks", "durationTicks" }) {
                var partialWindow = finite.DeepClone().AsObject();
                FrontHandEntity(partialWindow)[member]!["window"]!.AsObject().Remove(field);
                MotionRefuses(partialWindow, member + " partial explicit window refuses " + field);
                var nullLeaf = finite.DeepClone().AsObject();
                FrontHandEntity(nullLeaf)[member]!["window"]![field] = null;
                MotionRefuses(nullLeaf, member + " null window leaf refuses " + field);
            }
            MotionRefuses(TimedModifierWire(member, false, false), member + " missing entire timing refuses");
            foreach (string field in new[] { "startDelayTicks", "durationTicks" })
            {
                foreach (bool window in new[] { false, true }) {
                    var partial = TimedModifierWire(member, true, window);
                    FrontHandEntity(partial)[member]!.AsObject().Remove(field);
                    MotionRefuses(partial, member + " partial scalar pair does not fall back to window");
                }
                var presentNull = TimedModifierWire(member, false, true);
                FrontHandEntity(presentNull)[member]![field] = null;
                MotionRefuses(presentNull, member + " present null scalar is not omission");
                foreach (string invalid in new[] { "-1", "21601", "0.5", "true", "\"2\"" }) {
                    var bad = TimedModifierWire(member, true, true);
                    FrontHandEntity(bad)[member]![field] = JsonNode.Parse(invalid);
                    MotionRefuses(bad, member + " invalid scalar " + field + "=" + invalid);
                }
            }
            var zeroDuration = TimedModifierWire(member, true, true);
            FrontHandEntity(zeroDuration)[member]!["durationTicks"] = 0;
            MotionRefuses(zeroDuration, member + " zero scalar duration refuses");
            var nullWindow = TimedModifierWire(member, false, true);
            FrontHandEntity(nullWindow)[member]!["window"] = null;
            MotionRefuses(nullWindow, member + " null window refuses");
            var noLatch = TimedModifierWire(member, false, true);
            FrontHandEntity(noLatch)[member]!["window"]!["phase"] = "released";
            MotionRefuses(noLatch, member + " released timing requires its existing latch producer");
        }
    }

    private static RuntimeMotionWindowSpec ModifierWindow(string clock = "active", string phase = "always", int delay = 2, int duration = 3)
        => new() { Phase = phase, Clock = clock, StartDelayTicks = delay, DurationTicks = duration };

    private static (GeneratedProjectile Host, Projectile Body) TimedModifierActor(int updates,
        RuntimeTurnModifierSpec turn, RuntimeSpeedModifierSpec speed)
    {
        var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
        spec.TurnModifier = turn; spec.SpeedModifier = speed;
        var body = new Projectile { active = true, velocity = Vector2.UnitX * 5f, owner = 0, damage = 20 };
        var host = Attach(body); host.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
        return (host, body);
    }

    private static void ModifierUnifiedTimingEquivalentAndIntersection()
    {
        using var actors = new NativeActorState();
        foreach (int updates in new[] { 1, 3, 6 })
        {
            var legacy = TimedModifierActor(updates,
                new() { TurnRadiansPerUpdate = .1f, StartDelayTicks = 2, DurationTicks = 3 },
                new() { SpeedMultiplierPerUpdate = 1.1f, MaxSpeed = 20, StartDelayTicks = 2, DurationTicks = 3 });
            var unified = TimedModifierActor(updates,
                new() { TurnRadiansPerUpdate = .1f, Window = ModifierWindow() },
                new() { SpeedMultiplierPerUpdate = 1.1f, MaxSpeed = 20, Window = ModifierWindow() });
            var intersection = TimedModifierActor(updates,
                new() { TurnRadiansPerUpdate = .1f, StartDelayTicks = 2, DurationTicks = 3, Window = ModifierWindow(delay: 4, duration: 3) },
                new() { SpeedMultiplierPerUpdate = 1.1f, MaxSpeed = 20, StartDelayTicks = 2, DurationTicks = 3, Window = ModifierWindow(delay: 4, duration: 3) });
            for (int age = 1; age <= 8 * updates; age++)
            {
                foreach (var actor in new[] { legacy, unified, intersection }) {
                    actor.Body.velocity = Vector2.UnitX * 5f;
                    ModifierAge(actor.Host, age); InvokeModifier(actor.Host, "ApplyActiveModifiers");
                }
                AssertVfxNear(legacy.Body.velocity, unified.Body.velocity, "old pair equals selected active window at each subupdate");
                bool active = age > 4 * updates && age <= 5 * updates;
                ModifierNear(active ? 5.5f : 5f, intersection.Body.velocity.Length(), "explicit pair/window intersection retains scalar cutoff");
                ModifierNear(active ? .1f : 0f, intersection.Body.velocity.ToRotation(), "explicit pair/window intersection retains scalar delay");
            }
        }
    }

    private static void ModifierUnifiedTimingLateRelativeAndPhaseOnly()
    {
        using var actors = new NativeActorState();
        foreach (int updates in new[] { 1, 3, 6 })
        foreach (string clock in new[] { "since_release", "since_return" })
        {
            string phase = clock == "since_release" ? "released" : "returning";
            var actor = TimedModifierActor(updates,
                new() { TurnRadiansPerUpdate = .1f, Window = ModifierWindow(clock, phase, delay: 0, duration: 2) },
                new() { SpeedMultiplierPerUpdate = 1.1f, MaxSpeed = 20, Window = new() { Phase = phase } });
            int latch = 30000 * updates; // A late transition must not meet an invented 21600-tick ceiling.
            string flag = clock == "since_release" ? "_released" : "_returning";
            string stamp = clock == "since_release" ? "_releaseAge" : "_returnAge";
            typeof(GeneratedProjectile).GetField(stamp, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(actor.Host, latch);
            foreach (int offset in new[] { -1, 0, 1, 2 * updates - 1, 2 * updates, 40000 * updates })
            {
                typeof(GeneratedProjectile).GetField(flag, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(actor.Host, offset >= 0);
                ModifierAge(actor.Host, latch + offset); actor.Body.velocity = Vector2.UnitX * 5;
                InvokeModifier(actor.Host, "ApplyActiveModifiers");
                bool timed = offset >= 0 && offset < 2 * updates;
                ModifierNear(timed ? .1f : 0, actor.Body.velocity.ToRotation(), clock + " keeps all first/last relative subupdates");
                ModifierNear(offset >= 0 ? 5.5f : 5, actor.Body.velocity.Length(), "phase-only modifier has no fabricated lifetime");
            }
        }
    }

    private static void ModifierUnifiedTimingNpcConsumers()
    {
        using var actors = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
        Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
        var spec = Entity(); spec.Kind = "free_projectile";
        spec.HomingModifier = new() { RangeTiles = 10, MaxTurnRadiansPerUpdate = .1f, RequireLineOfSight = false, Window = ModifierWindow(delay: 1, duration: 2) };
        spec.NpcAttraction = new() { RangeTiles = 10, StrengthPerUpdate = 2, Falloff = "constant", MaxTargets = 1, Window = ModifierWindow(delay: 1, duration: 2) };
        var body = new Projectile { active = true, owner = 0, damage = 20, Center = new Vector2(500, 500), velocity = Vector2.UnitX * 6 };
        var host = Attach(body); host.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
        Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0, life = 100, lifeMax = 100, damage = 1,
            friendly = false, dontTakeDamage = false, knockBackResist = .5f, width = 10, height = 10, Center = body.Center + new Vector2(0, 80) };
        foreach (int age in new[] { 1, 2, 3, 4, 30000 }) {
            body.velocity = Vector2.UnitX * 6; Terraria.Main.npc[0].velocity = Vector2.Zero; ModifierAge(host, age);
            InvokeModifier(host, "ApplyHomingModifier"); InvokeModifier(host, "ApplyNpcAttraction");
            bool active = age is 2 or 3;
            ModifierNear(active ? .1f : 0, body.velocity.ToRotation(), "homing consumes window-only interval");
            ModifierNear(active ? -1f : 0, Terraria.Main.npc[0].velocity.Y, "attraction consumes window-only interval");
        }
    }
}
