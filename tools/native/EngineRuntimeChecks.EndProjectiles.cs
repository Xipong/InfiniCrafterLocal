#nullable enable
using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData EndProjectileFixture(bool terminalEvents = false)
    {
        var data = RootSpawnFixture(8, 1);
        data.Id = "remote_projectile_fixture";
        var body = data.RuntimeProgram.Entities[0];
        var target = data.RuntimeProgram.TryGetEntity("root")!;
        target.LifetimeTicks = 120;
        body.Events = new[] { new RuntimeEventActionSpec {
            Id = "remote_end", Event = RuntimeEventKind.OnUse, UseInput = RuntimeInputKind.AlternateUse,
            Action = "end_projectiles", ActionCode = RuntimeEventActionCode.EndProjectiles, EntityId = target.Id,
        } };
        data.RuntimeProgram.Bindings[1] = new RuntimeBindingSpec {
            Id = "remote_input", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Secondary,
            UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.UseItemBody, TargetId = body.Id,
            } },
        };
        if (terminalEvents)
        {
            var fragment = new RuntimeEntitySpec {
                Id = "fragment", Kind = RuntimeEntityKind.StationaryProjectile, LifetimeTicks = 60,
                VisualRole = "deployed_entity",
                Visual = new RuntimeEntityVisualSpec { Role = "deployed_entity", AssetMode = "no_asset" },
                Spawn = new RuntimeSpawnSpec { Enabled = true, Count = 1, Aim = "facing" },
            };
            data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(fragment).ToArray();
            target.Events = new[] { RuntimeEventKind.OnKill, RuntimeEventKind.OnExpire }
                .Select(ev => new RuntimeEventActionSpec {
                    Id = ev + "_fragment", Event = ev, Action = "spawn_entity_on_event",
                    ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = fragment.Id,
                    Count = 1, DelayTicks = 2,
                    DamageBasis = RuntimeChildCombatBasis.AuthoredChild,
                    KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
                }).ToArray();
        }
        return data;
    }

    private static void ExecuteEndProjectiles(GeneratedItemData data, RuntimeSpawnBudget? budget = null)
    {
        var owner = Terraria.Main.player[0];
        var body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
        var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
        RuntimeProgramExecutor.ExecuteAction(data, body, body.Events[0], owner,
            owner.GetSource_ItemUse(item), owner.Center, Vector2.UnitX, null, 0, 0,
            budget ?? new RuntimeSpawnBudget(0));
    }

    private static void EndProjectilesStrictAdmission()
    {
        var wire = JsonNode.Parse(EndProjectileFixture(terminalEvents: true).ToNetworkJson())!;
        Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is not null,
            "two-input item and terminal child path survive native wire admission");
        foreach (Action<JsonObject> mutate in new Action<JsonObject>[] {
            row => row["entityId"] = "missing", row => row["entityId"] = " root ",
            row => row["delayTicks"] = 1, row => row["count"] = 2,
            row => row["rangeTiles"] = 4, row => row["mode"] = "all",
            row => row["event"] = "On_Use",
        })
        {
            var malformed = wire.DeepClone();
            mutate(malformed["runtimeProgram"]!["entities"]![0]!["events"]![0]!.AsObject());
            Equal(true, GeneratedItemData.FromJson(malformed.ToJsonString()) is null,
                "missing/altered target, delayed or foreign command controls are refused");
        }
        var wrongSource = wire.DeepClone();
        var moved = wrongSource["runtimeProgram"]!["entities"]![0]!["events"]![0]!.DeepClone();
        moved["event"] = RuntimeEventKind.OnSpawn;
        moved.AsObject().Remove("useInput");
        wrongSource["runtimeProgram"]!["entities"]![0]!["events"] = new JsonArray();
        wrongSource["runtimeProgram"]!["entities"]![1]!["events"] = new JsonArray(moved);
        Equal(true, GeneratedItemData.FromJson(wrongSource.ToJsonString()) is null,
            "a projectile cannot turn its own event into recursive remote termination");

        var orphan = wire.DeepClone();
        string bodyId = orphan["runtimeProgram"]!["itemEntityId"]!.GetValue<string>();
        var primary = orphan["runtimeProgram"]!["bindings"]![0]!;
        primary["role"] = RuntimeEntityRole.Secondary;
        primary["usePolicy"]!["action"]!["kind"] = RuntimeBindingAction.UseItemBody;
        primary["usePolicy"]!["action"]!["targetId"] = bodyId;
        Equal(true, GeneratedItemData.FromJson(orphan.ToJsonString()) is null,
            "a remote target reference does not itself create a spawn path");
        orphan["runtimeProgram"]!["entities"]![0]!["events"] = new JsonArray();
        Equal(true, GeneratedItemData.FromJson(orphan.ToJsonString()) is not null,
            "control without the unusable command remains an ordinary admitted item");
    }

    private static void EndProjectilesRetiresExactInstancesThroughNativeKill()
    {
        using var scope = new SwarmRuntimeScope();
        var data = EndProjectileFixture(terminalEvents: true);
        var target = data.RuntimeProgram.TryGetEntity("root")!;
        var first = SwarmHost(data, target, slot: 0);
        var second = SwarmHost(data, target, slot: 1);
        var sameDefinition = EndProjectileFixture(terminalEvents: true);
        var copy = SwarmHost(sameDefinition, sameDefinition.RuntimeProgram.TryGetEntity("root")!, slot: 2);
        var otherOwner = SwarmHost(data, target, slot: 3, owner: 1);
        var otherDefinition = EndProjectileFixture(); otherDefinition.Id = "other_definition";
        var otherItem = SwarmHost(otherDefinition, otherDefinition.RuntimeProgram.TryGetEntity("root")!, slot: 4);
        var otherEntity = SwarmHost(data, data.RuntimeProgram.TryGetEntity("fragment")!, slot: 5);
        var native = Terraria.Main.projectile[6] = new Projectile { whoAmI = 6, owner = 0, active = true };
        var pending = Terraria.Main.projectile[7] = new Projectile { whoAmI = 7, owner = 0, active = true };
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(pending, Attach(pending));
        var inactive = SwarmHost(data, target, slot: 8); inactive.Projectile.active = false;
        var commandBudget = new RuntimeSpawnBudget(5);

        ExecuteEndProjectiles(data, commandBudget);
        Equal(false, first.Projectile.active || second.Projectile.active || copy.Projectile.active,
            "all exact owner/definition/entity instances terminate, including another inventory copy");
        Equal(true, otherOwner.Projectile.active && otherItem.Projectile.active && otherEntity.Projectile.active
            && native.active && pending.active, "foreign owners, definitions, entities, native and unhydrated projectiles survive");
        Equal(3, PendingActions(), "real native Kill invokes one on_kill per target and does not invent on_expire");
        Equal(5, commandBudget.Remaining, "termination neither spends nor replenishes the command activation budget");
        ExecuteEndProjectiles(data, commandBudget);
        Equal(3, PendingActions(), "repeating the command cannot rerun terminal effects on retired instances");
        // These are real queued authored actions. No descendant native spawn is
        // claimed: dispatch requires registered content, beyond this CPU fixture.
    }

    private static void EndProjectilesUsesAlternateInputAndOwnerAuthority()
    {
        foreach (var role in SwarmRoles)
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = EndProjectileFixture(terminalEvents: true);
            var target = data.RuntimeProgram.TryGetEntity("root")!; target.Spawn.MaxActive = 2;
            var live = SwarmHost(data, target);
            var owner = Terraria.Main.player[0];
            var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var host = AttachItem(new GeneratedItem(), item, data); owner.inventory[0] = item;
            int killPackets = 0;
            using var network = PersistenceObserveNetworkSend((message, _) => {
                if (message == MessageID.KillProjectile) killPackets++;
            });
            owner.altFunctionUse = 0;
            Equal(true, host.CanUseItem(owner), role.Name + " primary input admits with one free projectile slot");
            // Exercise accepted item-hook routing. Shoot/native spawning is a
            // separate boundary and is not manufactured by this CPU check.
            Equal(true, host.UseItem(owner) == true, role.Name + " primary use completes");
            Equal(true, live.Projectile.active, role.Name + " primary use does not issue the alternate command");
            target.Spawn.MaxActive = 1;
            owner.altFunctionUse = 2;
            Equal(true, host.CanUseItem(owner), role.Name + " full projectile capacity does not block the alternate item-body action");
            Equal(true, host.UseItem(owner) == true, role.Name + " alternate use completes");
            bool authorized = role.Name is "SP" or "owner-client";
            Equal(!authorized, live.Projectile.active, role.Name + " native retirement follows owner authority");
            Equal(authorized ? 1 : 0, PendingActions(), role.Name + " terminal authored action has one producer");
            Equal(role.Name == "owner-client" ? 1 : 0, killPackets,
                role.Name + " native Kill owns its existing projectile synchronization");
            host.UseItem(owner);
            Equal(authorized ? 1 : 0, PendingActions(), role.Name + " repeated input does not replay the dead entity");
        }
    }

    private static void EndProjectilesSnapshotPreservesNewIncarnations()
    {
        using var scope = new SwarmRuntimeScope(NetmodeID.MultiplayerClient, 0);
        var data = EndProjectileFixture(); var target = data.RuntimeProgram.TryGetEntity("root")!;
        var original = Enumerable.Range(0, 5).Select(slot => SwarmHost(data, target, slot)).ToArray();
        GeneratedProjectile? newEntity = null, replacedSlot = null;
        bool mutated = false;
        int killPackets = 0;
        // Inject concurrent lifecycle changes at the network I/O boundary. The
        // command, native Kill, and GeneratedProjectile.OnKill all run unchanged.
        // These are configured host objects, not claims of real native spawns.
        using var network = PersistenceObserveNetworkSend((message, _) => {
            if (message != MessageID.KillProjectile) return;
            killPackets++;
            if (mutated) return;
            mutated = true;
            newEntity = SwarmHost(data, target, slot: 10);
            replacedSlot = SwarmHost(data, target, slot: 1);
            original[2].Projectile.identity++;
            var reused = original[3].Projectile;
            var replacement = Attach(reused);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(reused, replacement);
            replacement.Configure(data, target, 0, 8, Vector2.UnitX);
        });
        ExecuteEndProjectiles(data);
        Equal(true, mutated, "actual native Kill reached the transport boundary");
        Equal(false, original[0].Projectile.active || original[4].Projectile.active,
            "unchanged snapshot members still terminate");
        Equal(true, newEntity!.Projectile.active && replacedSlot!.Projectile.active,
            "new matching entities and recycled slots are outside the captured command");
        Equal(true, original[1].Projectile.active && original[2].Projectile.active && original[3].Projectile.active,
            "detached native object, changed network identity and new ModProjectile instance are not killed");
        Equal(2, killPackets, "only the two unchanged snapshot incarnations reach native Kill");
    }

    private static void EndProjectilesReleasesOccupancyWithoutRefillingLifetime()
    {
        using var scope = new SwarmRuntimeScope();
        var data = EndProjectileFixture(terminalEvents: true);
        var target = data.RuntimeProgram.TryGetEntity("root")!; target.Spawn.MaxActive = 1;
        var lifetime = new RuntimeSpawnBudget(3);
        var concurrent = new RuntimeSpawnBudget(1, concurrent: true, parent: lifetime);
        Equal(1, concurrent.Reserve(1), "one successful descendant reservation");
        var live = SwarmHost(data, target);
        live.Configure(data, target, 1, concurrent.Remaining, Vector2.UnitX,
            activationBudget: concurrent, ownsSpawnReservation: true);
        Equal(0, concurrent.Remaining, "living target occupies the concurrent slot");
        Equal(2, lifetime.Remaining, "successful spawn spends the ancestor lifetime allowance");
        ExecuteEndProjectiles(data);
        Equal(false, live.Projectile.active, "the command uses native retirement");
        Equal(1, PendingActions(), "on_kill can reserve its replacement after releasing live occupancy");
        Equal(0, concurrent.Remaining, "queued replacement owns the released concurrent slot");
        Equal(1, lifetime.Remaining, "replacement spends lifetime allowance; death does not refund it");
        Equal(true, GeneratedProjectile.CanAdmitEntityBatch(data, target, 0, 1), "native retirement also releases the per-entity live cap");
        ExecuteEndProjectiles(data);
        Equal(1, lifetime.Remaining, "repeated termination cannot replenish or spend the dead target's ledger");
        RuntimeDelayedActionScheduler.Clear();
        Equal(1, concurrent.Remaining, "cancelling the queued replacement returns only its pending occupancy");
        Equal(2, lifetime.Remaining, "cancel refunds unused replacement, not the already spent original spawn");
    }
}
