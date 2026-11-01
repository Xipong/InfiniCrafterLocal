#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeEventActionSpec EndProjectilesAction() => JsonSerializer.Deserialize<RuntimeEventActionSpec>("""
        {"Id":"end","Event":"on_use","Action":"end_projectiles","ActionCode":12,
         "EntityId":"root","UseInput":"primary_use","DelayTicks":0}
        """)!;

    private static GeneratedItemData EndProjectilesData(string id = "end_projectiles_fixture", bool terminalSpawn = false)
    {
        var data = RootSpawnFixture(8, 1);
        data.Id = id;
        data.RuntimeProgram.Entities[0].Events = new[] { EndProjectilesAction() };
        if (terminalSpawn)
        {
            data.RuntimeProgram.TryGetEntity("root")!.Events = new[] {
                new RuntimeEventActionSpec { Id = "fragment", Event = RuntimeEventKind.OnKill,
                    Action = "spawn_entity_on_event", ActionCode = RuntimeEventActionCode.SpawnEntity,
                    EntityId = "fragment", Count = 1, DelayTicks = 2,
                    DamageBasis = RuntimeChildCombatBasis.AuthoredChild,
                    KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild },
            };
            data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(new RuntimeEntitySpec {
                Id = "fragment", Kind = RuntimeEntityKind.StationaryProjectile,
                VisualRole = "deployed_entity",
                Visual = new RuntimeEntityVisualSpec { Role = "deployed_entity", AssetMode = "no_asset" },
                Spawn = new RuntimeSpawnSpec { Enabled = true, Count = 1, Aim = "facing" },
            }).ToArray();
        }
        return data;
    }

    private static Player EndProjectilesOwner()
    {
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.myPlayer = 0;
        Terraria.Main.getGoodWorld = false;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
        RuntimeDelayedActionScheduler.Clear();
        Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.projectile.Length)
            .Select(slot => new Projectile { whoAmI = slot, active = false }).ToArray();
        return Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
    }

    private static Projectile EndProjectilesHost(GeneratedItemData data, int slot, string entityId = "root",
        int owner = 0, Projectile? reused = null, RuntimeSpawnBudget? budget = null)
    {
        var projectile = reused ?? new Projectile();
        projectile.whoAmI = slot; projectile.identity = 100 + slot; projectile.owner = owner;
        projectile.active = true; projectile.type = ProjectileID.None;
        projectile.position = new Vector2(1600, 1600);
        Terraria.Main.projectile[slot] = projectile;
        var generated = Attach(projectile);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        generated.Configure(data, data.RuntimeProgram.TryGetEntity(entityId)!, 0, 8, Vector2.UnitX,
            activationBudget: budget);
        projectile.timeLeft = 60;
        return projectile;
    }

    private static void ExecuteEndProjectiles(GeneratedItemData data, Player owner)
    {
        var body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
        RuntimeProgramExecutor.ExecuteAction(data, body, body.Events[0], owner,
            owner.GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 }),
            owner.Center, Vector2.UnitX, null, 0, 0, new RuntimeSpawnBudget(0));
    }

    private static void EndProjectilesStrictAdmission()
    {
        var data = EndProjectilesData(terminalSpawn: true);
        data.RuntimeProgram.NormalizeAndValidate();
        var restored = GeneratedItemData.FromJson(data.ToNetworkJson())
            ?? throw new InvalidOperationException("end_projectiles network definition refused");
        var accepted = restored.RuntimeProgram.Entities[0].Events[0];
        Equal(RuntimeEventActionCode.EndProjectiles, accepted.ActionCode, "new action survives strict network DTO");
        Equal("root", accepted.EntityId, "exact existing projectile reference survives");
        Equal(RuntimeInputKind.PrimaryUse, accepted.UseInput, "input scope survives");

        foreach (Action<RuntimeEventActionSpec> mutate in new Action<RuntimeEventActionSpec>[] {
            action => action.Action = "spawn_entity_on_event",
            action => action.Event = RuntimeEventKind.OnKill,
            action => action.EntityId = "",
            action => action.EntityId = " root ",
            action => action.DelayTicks = -1,
            action => action.DelayTicks = 601,
            action => action.Count = 2,
        })
        {
            var malformed = EndProjectilesAction(); mutate(malformed);
            EndProjectilesRefuses(malformed.NormalizeAndValidate, "malformed control action must fail before normalization");
        }
        foreach (string target in new[] { "missing", data.RuntimeProgram.ItemEntityId })
        {
            var malformed = EndProjectilesData();
            malformed.RuntimeProgram.Entities[0].Events[0].EntityId = target;
            EndProjectilesRefuses(malformed.RuntimeProgram.NormalizeAndValidate, "control requires an existing projectile target");
        }
        var descendant = EndProjectilesData(terminalSpawn: true);
        descendant.RuntimeProgram.Entities[0].Events[0].EntityId = "fragment";
        descendant.RuntimeProgram.NormalizeAndValidate();
        descendant.RuntimeProgram.TryGetEntity("root")!.Events = Array.Empty<RuntimeEventActionSpec>();
        EndProjectilesRefuses(descendant.RuntimeProgram.NormalizeAndValidate,
            "control reference alone cannot make a never-spawned target reachable");
        var wrongProducer = EndProjectilesData();
        wrongProducer.RuntimeProgram.TryGetEntity("root")!.Events = wrongProducer.RuntimeProgram.Entities[0].Events;
        wrongProducer.RuntimeProgram.Entities[0].Events = Array.Empty<RuntimeEventActionSpec>();
        EndProjectilesRefuses(wrongProducer.RuntimeProgram.NormalizeAndValidate, "projectile cannot produce an item-use control action");
        var delayed = EndProjectilesAction(); delayed.DelayTicks = 600; delayed.NormalizeAndValidate();
        Equal(600, delayed.DelayTicks, "existing bounded event delay remains available");
    }

    private static void EndProjectilesRefuses(Action admit, string label)
    {
        bool refused = false;
        try { admit(); }
        catch (InvalidDataException) { refused = true; }
        Equal(true, refused, label);
    }

    private static void EndProjectilesOwnerIsolationAndNativeKill()
    {
        using var actors = new NativeActorState();
        var owner = EndProjectilesOwner();
        Terraria.Main.player[1] = new Player { whoAmI = 1, active = true };
        var data = EndProjectilesData(terminalSpawn: true);
        var originalBudget = new RuntimeSpawnBudget(2);
        var first = EndProjectilesHost(data, 0, budget: originalBudget);
        var second = EndProjectilesHost(data, 1, budget: originalBudget);
        var otherOwner = EndProjectilesHost(data, 2, owner: 1);
        var otherDefinition = EndProjectilesHost(EndProjectilesData("another_recipe"), 3);
        var otherEntity = EndProjectilesHost(data, 4, "fragment");
        var vanilla = Terraria.Main.projectile[5] = new Projectile { whoAmI = 5, owner = 0, active = true };
        var unconfigured = Terraria.Main.projectile[6] = new Projectile { whoAmI = 6, owner = 0, active = true };
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(unconfigured, Attach(unconfigured));

        Terraria.Main.netMode = NetmodeID.Server;
        ExecuteEndProjectiles(data, owner);
        Equal(true, first.active && second.active, "server cannot replay owner input");
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
        ExecuteEndProjectiles(data, owner);
        Equal(true, first.active && second.active, "nonowner observer cannot terminate projectiles");
        Terraria.Main.myPlayer = 0; owner.active = false;
        ExecuteEndProjectiles(data, owner);
        Equal(true, first.active && second.active, "inactive input owner cannot terminate projectiles");

        owner.active = true;
        int killPackets = 0;
        using var network = PersistenceObserveNetworkSend((message, _) => {
            if (message == MessageID.KillProjectile) killPackets++;
        });
        ExecuteEndProjectiles(data, owner);
        Equal(false, first.active || second.active, "owner command reaches real Projectile.Kill for every match");
        Equal(2, killPackets, "native kill emits one synchronization packet per projectile");
        Equal(2, PendingActions(), "real native OnKill schedules each authored child once");
        Equal(0, originalBudget.Remaining, "terminal payload spends the original activation budget");
        foreach (var unrelated in new[] { otherOwner, otherDefinition, otherEntity, vanilla, unconfigured })
            Equal(true, unrelated.active, "owner, recipe, entity and generated identity remain isolated");
        ExecuteEndProjectiles(data, owner);
        Equal(2, PendingActions(), "empty repeated command cannot replay terminal payloads");
        Equal(2, killPackets, "empty repeated command cannot replay native kill packets");
    }

    private static void EndProjectilesSnapshotSurvivesNativeCallbacks()
    {
        foreach (bool reuseSameObject in new[] { false, true })
        {
            using var actors = new NativeActorState();
            var owner = EndProjectilesOwner();
            var data = EndProjectilesData();
            var first = EndProjectilesHost(data, 0);
            var oldSecond = EndProjectilesHost(data, 1);
            Projectile? replacement = null, newChild = null;
            int callbacks = 0;
            // Keep the real native kill and generated OnKill running. At the
            // native callback boundary another mod can allocate a child or
            // recycle a later selected slot, including the same host object.
            using var observer = new Hook(typeof(ProjectileLoader).GetMethod(nameof(ProjectileLoader.OnKill))!,
                (Action<Action<Projectile, int>, Projectile, int>)((original, projectile, timeLeft) => {
                    original(projectile, timeLeft); callbacks++;
                    if (!ReferenceEquals(projectile, first)) return;
                    replacement = EndProjectilesHost(data, 1, reused: reuseSameObject ? oldSecond : null);
                    newChild = EndProjectilesHost(data, 2);
                }));
            ExecuteEndProjectiles(data, owner);
            Equal(false, first.active, "original selected projectile is killed");
            Equal(true, replacement!.active, "recycled slot generation is outside the captured set");
            Equal(true, newChild!.active, "new matching child is outside the captured set");
            Equal(1, callbacks, "callback changes cannot enlarge or replace the captured set");
        }
    }

    private static void EndProjectilesDelaySelectsAtExecution()
    {
        using var actors = new NativeActorState();
        using var clock = new RuntimeWorldClockScope();
        var owner = EndProjectilesOwner();
        var data = EndProjectilesData();
        var body = data.RuntimeProgram.Entities[0];
        body.Events[0].DelayTicks = 2;
        var old = EndProjectilesHost(data, 0);
        var source = new EntitySource_ItemUse(owner, new Item { type = ItemID.CopperShortsword, stack = 1 });
        Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, body, body.Events[0], owner, source,
            owner.Center, Vector2.UnitX, null, 0, 0, new RuntimeSpawnBudget(0)), "delayed command uses normal item-source scheduler");
        old.active = false;
        AdvanceRuntimeWorldTick();
        var current = EndProjectilesHost(data, 0);
        var later = EndProjectilesHost(data, 1);
        Equal(true, current.active && later.active, "command does not execute before its due tick");
        AdvanceRuntimeWorldTick();
        Equal(false, current.active || later.active, "due command selects projectiles alive at execution");
        Equal(60, old.timeLeft, "retired admission-time projectile is not replayed");
        Equal(0, PendingActions(), "executed command retires without a spawn reservation");
    }
}
