using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Globalization;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData MovingFiringCompositionFixture(string kind)
    {
        var data = SentryTargetingFixture();
        data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = 32;
        var root = data.RuntimeProgram.TryGetEntity("root")!;
        root.Targeting.Count = 1;
        root.Targeting.SpreadRadians = 0;
        root.Targeting.RequireLineOfSight = false;
        var shot = data.RuntimeProgram.TryGetEntity("shot")!;
        shot.Spawn.Count = 1;
        shot.Spawn.SpreadRadians = 0;
        RuntimeEntitySpec moving;
        if (kind == RuntimeEntityKind.FreeProjectile)
        {
            moving = root;
            moving.Kind = kind;
            moving.VisualRole = moving.Visual.Role = "projectile";
        }
        else
        {
            // Keep a legal producer graph: stationary root -> moving child -> leaf.
            // The child is never smuggled through an item spawn binding.
            moving = shot;
            moving.Controller = new RuntimeControllerSpec { Name = "target_and_fire", Code = RuntimeControllerCode.TargetAndFire };
            moving.Targeting = new RuntimeTargetingSpec { ShotEntityId = "leaf", IntervalTicks = 6,
                RangeTiles = 10, Count = 1, SpreadRadians = 0, TargetPolicy = "distance_score",
                RequireLineOfSight = false, HardRange = true,
                DamageBasis = RuntimeChildCombatBasis.AuthoredChild,
                KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild, DamageMultiplier = 1f };
            data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(new RuntimeEntitySpec {
                Id = "leaf", Kind = RuntimeEntityKind.ChildProjectile, VisualRole = "child_projectile",
                Visual = new RuntimeEntityVisualSpec { Role = "child_projectile", AssetMode = "no_asset" },
                Spawn = new RuntimeSpawnSpec { Enabled = true, Count = 1, Aim = "velocity", SpeedPxPerTick = 10f },
                Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 },
            }).ToArray();
        }
        moving.LifetimeTicks = 90;
        moving.Movement = new RuntimeMovementSpec { Name = "move_gravity_arc", Code = 2,
            Params = new RuntimeParamsSpec { GravityPerTick = .25f } };
        moving.SpeedModifier = new RuntimeSpeedModifierSpec { SpeedMultiplierPerUpdate = .8f,
            MaxSpeed = 20f, StartDelayTicks = 0, DurationTicks = 60 };
        return data;
    }

    private static void TargetAndFireAdmitsAndExecutesFreeAndChildMotion()
    {
        foreach (string kind in new[] { RuntimeEntityKind.FreeProjectile, RuntimeEntityKind.ChildProjectile })
        foreach (var role in SwarmRoles)
        {
            using var actors = new SwarmRuntimeScope(role.Mode, role.Local);
            var authored = MovingFiringCompositionFixture(kind);
            // Exercise production serialization AND ingress before invoking any AI.
            var data = GeneratedItemData.FromJson(authored.ToNetworkJson())
                ?? throw new InvalidOperationException("moving firing composition rejected by native DTO");
            string id = kind == RuntimeEntityKind.FreeProjectile ? "root" : "shot";
            var entity = data.RuntimeProgram.TryGetEntity(id)!;
            Equal(kind, entity.Kind, "accepted moving firing kind retained");
            Equal(RuntimeControllerCode.TargetAndFire, entity.Controller.Code, "controller survives strict ingress");
            var generated = SwarmHost(data, entity);
            generated.Projectile.velocity = new Vector2(4, 0);
            generated.AI(); generated.AI();
            ModifierNear(2.56f, generated.Projectile.velocity.X, role.Name + " authored speed modifier executes once per update");
            ModifierNear(.36f, generated.Projectile.velocity.Y, role.Name + " gravity precedes speed modifier each update");

            var wire = System.Text.Json.Nodes.JsonNode.Parse(data.ToNetworkJson())!;
            var entities = wire["runtimeProgram"]!["entities"]!.AsArray();
            var invalid = entities.First(e => e!["id"]!.GetValue<string>() == id)!;
            invalid["movement"] = new System.Text.Json.Nodes.JsonObject();
            Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is null,
                "free/child firing modifier cannot invent an absent movement driver");
            invalid.AsObject().Remove("speedModifier");
            Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is null,
                "free/child firing without modifiers still requires explicit movement");
        }
    }

    private static void GeneratedCombatBuffLifecycleAndWire()
    {
        using var f = new QuickUtilityPeers(cost: 0);
        f.Mode(2);
        var combat = new GeneratedCombatBuffSpec { DefensePoints = 8, AttackSpeedPercent = 20,
            CritChancePoints = 5, DamagePercent = 30, DamageClass = "magic" };
        var buff = new GeneratedBuffSpec { DurationTicks = 3, Combat = combat };
        var dto = ExhaustionData("combat-wire", null);
        dto.Gameplay.GeneratedBuff = buff;
        var decoded = GeneratedItemData.FromJson(dto.ToNetworkJson())
            ?? throw new InvalidOperationException("combat-only buff rejected by native DTO");
        Equal(combat, decoded.Gameplay.GeneratedBuff.Combat!, "native JSON roundtrip retains all combat choices");
        Equal(true, ExhaustionApply(f.ServerBuff, buff, null), "combat-only buff activates");
        Equal(true, ExhaustionApply(f.ServerBuff, buff, null), "equal combat effect refreshes");
        Equal(1, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "refresh does not stack identical effect");
        Equal(8, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Current.Defense, "aggregate retains authored defense");
        // A native frame initializes DefenseStat's multiplicative factor to one.
        // The packet-only peer fixture otherwise leaves this struct zero-initialized.
        f.Server.statDefense = new Player.DefenseStat();
        var effects = typeof(InfiniCraftPlayer).GetMethod("ApplyGeneratedUtilityBuffEffects", MobilityConsumptionFlags)!;
        int defense = (int)f.Server.statDefense;
        float speed = f.Server.GetAttackSpeed(DamageClass.Generic), crit = f.Server.GetCritChance(DamageClass.Generic);
        float magic = f.Server.GetDamage(DamageClass.Magic).Additive, ranged = f.Server.GetDamage(DamageClass.Ranged).Additive;
        effects.Invoke(f.ServerBuff, null);
        Equal(defense + 8, (int)f.Server.statDefense, "defense reaches Player");
        Equal(speed + .2f, f.Server.GetAttackSpeed(DamageClass.Generic), "percentage speed conversion once");
        Equal(crit + 5, f.Server.GetCritChance(DamageClass.Generic), "crit uses percentage points");
        Equal(magic + .3f, f.Server.GetDamage(DamageClass.Magic).Additive, "damage reaches selected class");
        Equal(ranged, f.Server.GetDamage(DamageClass.Ranged).Additive, "unselected damage class unchanged");
        byte[] bytes = ExhaustionSnapshot(f.ServerBuff);
        var packet = new byte[bytes.Length + 1]; packet[0] = InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff; bytes.CopyTo(packet, 1);
        f.Mode(3); f.Peers.Receive(packet, 256);
        var presentation = f.RemoteBuff.CaptureGeneratedUtilityBuffPresentation();
        Equal(8, presentation.Current.Defense, "network decode rebuilds combat aggregate");
        Equal(30f, presentation.Current.DamageBonuses!["magic"], "network preserves exact class and percentage");
        Equal(4, GeneratedUtilityBuffStatusView.Build(presentation, CultureInfo.InvariantCulture).Count, "HUD shows four combat contributions");
        for (int i = 0; i < 3; i++) ExhaustionBuffTick(f.RemoteBuff);
        Equal(0, f.RemoteBuff.CaptureGeneratedUtilityBuffPresentation().Current.Defense, "expiry removes combat aggregate");
        Equal(0, GeneratedUtilityBuffStatusView.Build(f.RemoteBuff.CaptureGeneratedUtilityBuffPresentation(), CultureInfo.InvariantCulture).Count, "expiry removes combat HUD");
        f.Mode(2);
        ExhaustionApply(f.ServerBuff, new GeneratedBuffSpec { DurationTicks = 20, JumpBoost = 1 }, null);
        ExhaustionApply(f.ServerBuff, new GeneratedBuffSpec { DurationTicks = 20, JumpBoost = 1,
            Combat = new GeneratedCombatBuffSpec { DamageClass = "magic" } }, null);
        Equal(2, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "explicit zero combat refreshes the same utility effect as absent combat");
        foreach (string damageClass in new[] { "magic", "ranged" })
            ExhaustionApply(f.ServerBuff, new GeneratedBuffSpec { DurationTicks = 20,
                Combat = new GeneratedCombatBuffSpec { DefensePoints = 2, DamageClass = damageClass } }, null);
        Equal(3, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "inactive damage class cannot multiply the same defense effect");
        using var stream = new MemoryStream();
        combat.Write(new BinaryWriter(stream)); stream.Position = stream.Length - 1; stream.WriteByte(255); stream.Position = 0;
        bool rejected = false; try { GeneratedCombatBuffSpec.Read(new BinaryReader(stream)); } catch (InvalidDataException) { rejected = true; }
        Equal(true, rejected, "unknown combat class rejected before applying snapshot");
    }
}
