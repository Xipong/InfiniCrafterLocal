#nullable enable
using System;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static void BothPullKeepsIndependentAuthorityAndDirectTarget()
    {
        using var actors = new NativeActorState();
        using var clock = new RuntimeWorldClockScope();
        RuntimeDelayedActionScheduler.Clear();
        Terraria.Main.myPlayer = 0;
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        owner.Center = Vector2.Zero;
        var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, width = 20, height = 20, knockBackResist = .5f };
        target.Center = new Vector2(100, 0);
        var data = GeneratedItemData.Placeholder(); data.Id = "both_pull_fixture";
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var entity = Entity(); entity.Id = "both_pull"; entity.Kind = RuntimeEntityKind.FreeProjectile;
        var action = new RuntimeEventActionSpec { Id = "both", Event = RuntimeEventKind.OnHit,
            Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull, Mode = "both",
            OwnerStrength = 1f, TargetStrength = 3f };
        action.NormalizeAndValidate();
        var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, identity = 81, owner = 0, active = true };
        var generated = Attach(projectile);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        entity.Events = new[] { action }; data.RuntimeProgram.Entities = new[] { entity };
        generated.Configure(data, entity, 0, 0, Vector2.UnitX);
        var source = new EntitySource_Parent(projectile);
        void Run(NPC? npc) => RuntimeProgramExecutor.ExecuteAction(data, entity, action, owner, source,
            target.Center, Vector2.UnitX, npc, 0, 0, new RuntimeSpawnBudget(0));
        Terraria.Main.netMode = NetmodeID.MultiplayerClient;
        Run(target);
        Equal(Vector2.UnitX, owner.velocity, "owner applies only its independent impulse");
        Equal(Vector2.Zero, target.velocity, "owner never applies NPC impulse");
        Terraria.Main.netMode = NetmodeID.Server;
        new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
        Terraria.Main.netMode = NetmodeID.MultiplayerClient;
        using var receipt = new MemoryStream();
        using (var writer = new BinaryWriter(receipt, System.Text.Encoding.UTF8, true))
            Equal(true, RuntimeHitPullBridge.TryWriteProjectileReceipt(writer, projectile, target, false), "both writes existing validated NPC hit receipt");
        Terraria.Main.netMode = NetmodeID.Server;
        receipt.Position = 0;
        using (var reader = new BinaryReader(receipt, System.Text.Encoding.UTF8, true))
            RuntimeHitPullBridge.HandlePacket(reader, 0);
        Equal(Vector2.UnitX, owner.velocity, "server never repeats owner impulse");
        Equal(new Vector2(-1.5f, 0), target.velocity, "NPC impulse uses independent strength and resistance");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
        Run(target);
        Equal(Vector2.UnitX, owner.velocity, "observer cannot pull owner");
        Equal(new Vector2(-1.5f, 0), target.velocity, "observer cannot pull NPC");
        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
        owner.velocity = target.velocity = Vector2.Zero; target.knockBackResist = 0;
        Run(target);
        Equal(Vector2.UnitX, owner.velocity, "immune boss still anchors owner pull");
        Equal(Vector2.Zero, target.velocity, "immune boss stays still");
        owner.velocity = Vector2.Zero; target.active = false; Run(target); Run(null);
        Equal(Vector2.Zero, owner.velocity, "missing target moves neither body");
        Equal(Vector2.Zero, target.velocity, "missing target never becomes NPC search");
        target.active = true; target.knockBackResist = 1; action.DelayTicks = 2;
        new RuntimeHitNpcGeneration().OnSpawn(target, owner.GetSource_Misc("spawn"));
        Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source,
            target.Center, Vector2.UnitX, target, 0, 0, new RuntimeSpawnBudget(0)), "delayed both admitted");
        Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, knockBackResist = 1, position = target.position };
        AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
        Equal(Vector2.Zero, owner.velocity, "recycled target cancels delayed owner impulse");
        Equal(Vector2.Zero, Terraria.Main.npc[0].velocity, "recycled target cancels delayed NPC impulse");
        bool refused = false;
        try { new RuntimeEventActionSpec { Id = "bad", Action = "pull_on_event", ActionCode = 5,
            Event = "on_hit", Mode = "both", OwnerStrength = 1 }.NormalizeAndValidate(); }
        catch (InvalidDataException) { refused = true; }
        Equal(true, refused, "both cannot infer the missing target impulse");
        foreach (Action<RuntimeEventActionSpec> mutate in new Action<RuntimeEventActionSpec>[]
        {
            row => row.Count = 2, row => row.DamageMultiplier = 2f, row => row.EntityId = "foreign",
            row => row.SpreadRadians = 1f, row => row.PeriodTicks = 1, row => row.DurationTicks = 1,
            row => row.RadiusPx = 16, row => row.RangeTiles = 1f, row => row.DamageFraction = 0.5f,
            row => row.MaxHeal = 1, row => row.CooldownTicks = 1, row => row.SafeTileOnly = false,
            row => row.DelayTicks = 601,
        })
        {
            var malformed = new RuntimeEventActionSpec { Id = "foreign", Action = "pull_on_event", ActionCode = 5,
                Event = "on_hit", Mode = "both", OwnerStrength = 1f, TargetStrength = 2f };
            mutate(malformed);
            refused = false;
            try { malformed.NormalizeAndValidate(); }
            catch (InvalidDataException) { refused = true; }
            Equal(true, refused, "both rejects foreign action fields before normalization");
        }
    }

    private static void NearbyDamageRanksNearestWithDeterministicCap()
    {
        using var actors = new NativeActorState();
        for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i };
        for (int i = 0; i < 18; i++)
        {
            var npc = Terraria.Main.npc[i] = new NPC { whoAmI = i, active = true, life = 1000, lifeMax = 1000, width = 20, height = 20 };
            npc.Center = new Vector2(100 - i, 0);
        }
        // Equal-distance tie is slot order, not an unstable sort accident.
        Terraria.Main.npc[17].Center = new Vector2(1, 0);
        Terraria.Main.npc[16].Center = new Vector2(-1, 0);
        var nearest = RuntimeProgramExecutor.SelectNearbyDamageTargets(Vector2.Zero, 100, 3, null);
        Equal(3, nearest.Count, "authored target limit");
        Equal(16, nearest[0].whoAmI, "deterministic equal-distance first slot");
        Equal(17, nearest[1].whoAmI, "deterministic equal-distance second slot");
        Equal(15, nearest[2].whoAmI, "distance wins over native slot order");
        Equal(16, RuntimeProgramExecutor.SelectNearbyDamageTargets(Vector2.Zero, 100, 16, null).Count, "common technical cap 16");
        Equal(17, RuntimeProgramExecutor.SelectNearbyDamageTargets(Vector2.Zero, 1, 16, Terraria.Main.npc[16])[0].whoAmI,
            "inclusive radius and exact direct-target exclusion");
        var action = new RuntimeEventActionSpec { Id = "nearby", Action = "damage_nearby_on_event", ActionCode = 10,
            Event = "on_expire", RadiusPx = 960, DamageMultiplier = 4, MaxTargets = 16 };
        action.NormalizeAndValidate();
        Equal(16, action.MaxTargets!.Value, "new native target bound is not old nearest cap12");
        bool refused = false;
        try { action.MaxTargets = 17; } catch (InvalidDataException) { refused = true; }
        Equal(true, refused, "new native bound rejects rather than silently clamps");
        Terraria.Main.SceneMetrics = new SceneMetrics();
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
        foreach (string eventName in new[] { "on_hit", "on_expire" })
        foreach (int count in new[] { 3, 16 })
        {
            using var scope = new SwarmRuntimeScope();
            Vector2 center = new(1600, 1600);
            for (int i = 0; i < 18; i++) Terraria.Main.npc[i] = EventDomainNpc(i, center, 100 - i);
            var data = SwarmGameplayFixture();
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var owner = Terraria.Main.player[0];
            var hit = new RuntimeEventActionSpec { Id = "nearby_damage", Action = "damage_nearby_on_event",
                ActionCode = RuntimeEventActionCode.DamageNearby, Event = eventName,
                RadiusPx = 960, DamageMultiplier = .5f, MaxTargets = count };
            hit.NormalizeAndValidate();
            var direct = Terraria.Main.npc[17];
            RuntimeProgramExecutor.ExecuteAction(data, entity, hit, owner, owner.GetSource_Misc("nearby_probe"),
                center, Vector2.UnitX, direct, 777, 0, new RuntimeSpawnBudget(0));
            int damaged = 0;
            for (int i = 0; i < 18; i++)
            {
                bool expected = eventName == "on_hit" ? i >= 17 - count && i < 17 : i >= 18 - count;
                Equal(expected, Terraria.Main.npc[i].life < 1000, $"{eventName} nearest {count} damage reaches NPC {i}");
                if (Terraria.Main.npc[i].life < 1000) damaged++;
            }
            Equal(count, damaged, "real damage consumer honors count including targets 13..16");
        }
    }
}
