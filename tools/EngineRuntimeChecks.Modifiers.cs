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
    private static void InvokeModifier(GeneratedProjectile generated, string method)
        => typeof(GeneratedProjectile).GetMethod(method, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(generated, null);
    private static void ModifierAge(GeneratedProjectile generated, int age)
        => typeof(GeneratedProjectile).GetField("_age", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(generated, age);
    private static void ModifierNear(float expected, float actual, string label)
    {
        if (!float.IsFinite(actual) || !float.IsFinite(expected) || MathF.Abs(expected - actual) > .0005f)
            throw new InvalidOperationException(label + ": " + expected + " != " + actual);
    }

    private static void ModifierActualTurnSpeedPhaseAndVisualHydration()
    {
        foreach (int updates in new[] { 1, 3, 6 })
        {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.TurnModifier = new() { TurnRadiansPerUpdate = .1f, StartDelayTicks = 2, DurationTicks = 3 };
            spec.SpeedModifier = new() { SpeedMultiplierPerUpdate = 1.1f, MaxSpeed = 20f, StartDelayTicks = 2, DurationTicks = 3 };
            var projectile = new Projectile { active = true, velocity = Vector2.UnitX * 5f, owner = 0, damage = 20 };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            foreach (int age in new[] { 1, 2 * updates, 2 * updates + 1, 5 * updates, 5 * updates + 1 })
            {
                projectile.velocity = Vector2.UnitX * 5f; ModifierAge(generated, age);
                InvokeModifier(generated, "ApplyActiveModifiers");
                bool active = age > 2 * updates && age <= 5 * updates;
                ModifierNear(active ? 5.5f : 5f, projectile.velocity.Length(), "simultaneous speed and phase");
                ModifierNear(active ? .1f : 0f, projectile.velocity.ToRotation(), "simultaneous turn and phase");
            }
            ModifierAge(generated, 2 * updates + 1); projectile.velocity = Vector2.UnitX * 19f;
            InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(20f, projectile.velocity.Length(), "post-multiplier cap");
            projectile.velocity = Vector2.Zero; InvokeModifier(generated, "ApplyActiveModifiers");
            Equal(Vector2.Zero, projectile.velocity, "modifiers never invent velocity for zero input");
            spec.SpeedModifier.SpeedMultiplierPerUpdate = .8f; projectile.velocity = Vector2.UnitX * 5f;
            InvokeModifier(generated, "ApplyActiveModifiers"); ModifierNear(4f, projectile.velocity.Length(), "explicit independent drag");

            spec.Hitbox.DrawScale = 2f; spec.Visual.Scale = 3f;
            spec.VisualScaleCurve = new() { StartScale = 1, EndScale = 4, Curve = "exponential", StartDelayTicks = 5, DurationTicks = 60 };
            ModifierAge(generated, 35 * updates);
            generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            ModifierNear(12f, projectile.scale, "visual curve late hydration from original base");
            Rectangle rectangle = projectile.Hitbox; generated.ModifyDamageHitbox(ref rectangle);
            Equal(projectile.Hitbox.Width, rectangle.Width, "visual curve does not grow damage rectangle");
        }
    }

    private static void ModifierNpcAttractionAuthorityFalloffAndBounds()
    {
        NPC[] oldNpcs = Terraria.Main.npc;
        int oldMode = Terraria.Main.netMode;
        int oldPlayer = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
            var spec = Entity(); spec.Kind = "free_projectile";
            spec.NpcAttraction = new() { RangeTiles = 10, StrengthPerUpdate = 2, Falloff = "linear", MaxTargets = 1, StartDelayTicks = 1, DurationTicks = 2 };
            var projectile = new Projectile { active = true, owner = 0, damage = 20, Center = new Vector2(500, 500), velocity = new Vector2(3, 4) };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            for (int i = 0; i < 3; i++)
                Terraria.Main.npc[i] = new NPC { whoAmI = i, active = true, life = 100, lifeMax = 100, damage = 1,
                    friendly = false, dontTakeDamage = false, knockBackResist = .5f, width = 10, height = 10,
                    Center = projectile.Center + new Vector2(i == 2 ? 161f : 80f, 0) };
            foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.Server, NetmodeID.MultiplayerClient })
            {
                Terraria.Main.netMode = mode; Terraria.Main.myPlayer = 0;
                foreach (NPC npc in Terraria.Main.npc) { npc.velocity = Vector2.Zero; npc.netUpdate = false; }
                ModifierAge(generated, 2); InvokeModifier(generated, "ApplyNpcAttraction");
                ModifierNear(mode == NetmodeID.MultiplayerClient ? 0 : -.5f, Terraria.Main.npc[0].velocity.X, "server-only linear impulse with native resistance");
                Equal(Vector2.Zero, Terraria.Main.npc[1].velocity, "maxTargets prevents second accepted target");
                Equal(Vector2.Zero, Terraria.Main.npc[2].velocity, "hard range excludes outside target");
                Equal(new Vector2(3, 4), projectile.velocity, "attraction never adds hidden projectile drag");
            }
            Terraria.Main.netMode = NetmodeID.Server;
            spec.NpcAttraction.Falloff = "constant"; Terraria.Main.npc[0].velocity = Vector2.Zero;
            ModifierAge(generated, 2); InvokeModifier(generated, "ApplyNpcAttraction");
            ModifierNear(-1f, Terraria.Main.npc[0].velocity.X, "constant falloff is a distinct explicit law");
            foreach (int age in new[] { 1, 4 })
            {
                Terraria.Main.npc[0].velocity = Vector2.Zero; ModifierAge(generated, age);
                InvokeModifier(generated, "ApplyNpcAttraction"); Equal(Vector2.Zero, Terraria.Main.npc[0].velocity, "outside phase has no impulse");
            }
        }
        finally { Terraria.Main.npc = oldNpcs; Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldPlayer; }
    }

    private static void ModifierHomingOwnerSelectionAndSpeedPreservation()
    {
        NPC[] oldNpcs = Terraria.Main.npc; int oldMode = Terraria.Main.netMode, oldPlayer = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
            var spec = Entity(); spec.Kind = "free_projectile";
            spec.HomingModifier = new() { RangeTiles = 10, MaxTurnRadiansPerUpdate = .1f, RequireLineOfSight = false, StartDelayTicks = 0, DurationTicks = 20 };
            var projectile = new Projectile { active = true, owner = 0, damage = 10, Center = new Vector2(500, 500), velocity = Vector2.UnitX * 6f };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0, life = 100, lifeMax = 100, damage = 1, Center = projectile.Center + new Vector2(0, 80) };
            Terraria.Main.npc[1] = new NPC { active = true, whoAmI = 1, life = 100, lifeMax = 100, damage = 1, Center = projectile.Center + new Vector2(0, -80) };
            foreach ((int mode, int player, bool runs) in new[] { (0, 0, true), (1, 0, true), (1, 1, false), (2, 255, false) })
            {
                Terraria.Main.netMode = mode; Terraria.Main.myPlayer = player;
                projectile.velocity = Vector2.UnitX * 6f; projectile.netUpdate = false; ModifierAge(generated, 1);
                InvokeModifier(generated, "ApplyHomingModifier");
                ModifierNear(6f, projectile.velocity.Length(), "homing preserves actual speed");
                ModifierNear(runs ? .1f : 0f, projectile.velocity.ToRotation(), "owner-only nearest target, stable slot tie");
                Equal(runs, projectile.netUpdate, "owner steered velocity is synchronized");
            }
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.npc[0].Center = projectile.Center + new Vector2(0, 161); Terraria.Main.npc[1].active = false;
            projectile.velocity = Vector2.UnitX * 6f; InvokeModifier(generated, "ApplyHomingModifier");
            Equal(Vector2.UnitX * 6f, projectile.velocity, "out-of-range candidate cannot steer");
        }
        finally { Terraria.Main.npc = oldNpcs; Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldPlayer; }
    }

    private static void ModifierWhipGravityUsesTheSameCollisionPolyline()
    {
        WithPlayer((owner, _) =>
        {
            Player oldOwner = Terraria.Main.player[0];
            try
            {
                owner.active = true; owner.whoAmI = 0; owner.direction = 1; owner.itemAnimationMax = 20; owner.itemAnimation = 5;
                Terraria.Main.player[0] = owner;
                var spec = Entity(); spec.Kind = "owner_attached_projectile";
                spec.Movement.Name = "move_whip_lash"; spec.Movement.Code = 18; spec.Movement.Params.RangeTiles = 10; spec.Movement.Params.Segments = 12;
                spec.WhipUsesOwnerGravity = true;
                var projectile = new Projectile { active = true, owner = 0, damage = 100 };
                var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
                owner.gravDir = 1; generated.AI();
                var points = (List<Vector2>)typeof(GeneratedProjectile).GetField("_whipPoints", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!;
                Vector2[] normal = points.Select(point => point - owner.MountedCenter).ToArray();
                owner.gravDir = -1; generated.AI();
                for (int i = 0; i < points.Count; i++)
                {
                    Vector2 inverse = points[i] - owner.MountedCenter;
                    ModifierNear(normal[i].X, inverse.X, "whip mirrored x"); ModifierNear(-normal[i].Y, inverse.Y, "whip mirrored y");
                }
                Equal(points[^1], projectile.Center, "actual whip tip follows mirrored polyline");
                Vector2 tip = points[^1];
                Equal(true, generated.Colliding(new Rectangle(), new Rectangle((int)tip.X - 3, (int)tip.Y - 3, 6, 6)) == true, "collision consumes mirrored points");
            }
            finally { Terraria.Main.player[0] = oldOwner; }
        });
    }

    private static void ModifierStrictDtoPresenceAndOldAbsence()
    {
        var raw = JsonNode.Parse(RootSpawnFixture(8, 1).ToJson())!.AsObject();
        JsonObject entity = raw["runtimeProgram"]!["entities"]![1]!.AsObject();
        foreach ((string member, string json) in new[] {
            ("turnModifier", "{\"turnRadiansPerUpdate\":0.1,\"startDelayTicks\":0,\"durationTicks\":60}"),
            ("speedModifier", "{\"speedMultiplierPerUpdate\":1.01,\"maxSpeed\":20,\"startDelayTicks\":0,\"durationTicks\":60}"),
            ("homingModifier", "{\"rangeTiles\":10,\"maxTurnRadiansPerUpdate\":0.1,\"requireLineOfSight\":true,\"startDelayTicks\":0,\"durationTicks\":60}"),
            ("npcAttraction", "{\"rangeTiles\":10,\"strengthPerUpdate\":2,\"falloff\":\"linear\",\"maxTargets\":4,\"startDelayTicks\":0,\"durationTicks\":60}"),
            ("visualScaleCurve", "{\"startScale\":1,\"endScale\":4,\"curve\":\"exponential\",\"startDelayTicks\":0,\"durationTicks\":60}"),
        })
        {
            JsonObject spec = JsonNode.Parse(json)!.AsObject(); entity[member] = spec;
            var parsed = GeneratedItemData.FromJson(raw.ToJsonString()) ?? throw new InvalidOperationException("valid " + member + " rejected");
            Equal(true, GeneratedItemData.FromJson(parsed.ToNetworkJson()) is not null, "network roundtrip " + member);
            foreach (string leaf in spec.Select(pair => pair.Key).ToArray())
            {
                JsonNode? saved = spec[leaf]?.DeepClone(); spec.Remove(leaf);
                Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "required " + member + "." + leaf);
                spec[leaf] = saved;
            }
            spec["durationTicks"] = 0; Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid duration cannot clamp"); spec["durationTicks"] = 60;
            spec["unknown"] = 1; Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "unknown modifier choice"); spec.Remove("unknown");
            entity[member] = null; Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "explicit null modifier"); entity.Remove(member);
        }
        var legacy = GeneratedItemData.FromJson(raw.ToJsonString()) ?? throw new InvalidOperationException("old absence rejected");
        Equal(false, legacy.ToJson().Contains("turnModifier", StringComparison.Ordinal), "old absence remains absent");
        entity["whipUsesOwnerGravity"] = true;
        Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "gravity marker needs actual whip driver");
    }
}
