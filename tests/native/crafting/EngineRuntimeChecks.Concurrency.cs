using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
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
    private static GeneratedItemData ConcurrencyFixture(int? maximum, int count = 1)
    {
        var source = RootSpawnFixture(7, count);
        source.Id = "concurrency_definition";
        var raw = JsonNode.Parse(source.ToJson())!.AsObject();
        if (maximum.HasValue) raw["runtimeProgram"]!["entities"]![1]!["spawn"]!["maxActive"] = maximum.Value;
        return GeneratedItemData.FromJson(raw.ToJsonString())
            ?? throw new InvalidOperationException("explicit maxActive wire rejected");
    }

    private static void ExplicitConcurrencyFencesAllSpawnProducersWithoutChangingLegacy()
    {
        using var actorState = new NativeActorState();

        WithPlayer((owner, _) => {
        Projectile[] oldProjectiles = Terraria.Main.projectile;
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
        Terraria.Main.dedServ = true; // Admission regression is CPU-only; do not draw feedback chat.
        owner.active = true; owner.whoAmI = 0; owner.direction = 1;
        Terraria.Main.player[0] = owner;
        void Reset() => Terraria.Main.projectile = Enumerable.Range(0, oldProjectiles.Length)
            .Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
        void Live(GeneratedItemData data, int slot, int player = 0, string entityId = "root", int depth = 0)
        {
            var projectile = Terraria.Main.projectile[slot]; projectile.active = true; projectile.owner = player;
            var generated = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
            generated.Configure(data, data.RuntimeProgram.TryGetEntity(entityId)!, depth, 7, Vector2.UnitX);
        }
        GeneratedItem Host(GeneratedItemData data)
        {
            var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
            var generated = new GeneratedItem();
            AttachItem(generated, item, data);
            return generated;
        }
        using var intercept = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)InterceptUnregisteredRootSpawn);
        Reset();
        var capped = ConcurrencyFixture(1); var host = Host(capped);
        Equal(true, host.CanUseItem(owner), "first capped use admitted");
        Live(capped, 0);
        Equal(false, host.CanUseItem(owner), "second use refused while matching instance active");
        Equal(false, Host(ConcurrencyFixture(1)).CanUseItem(owner), "another inventory copy shares definition/entity cap");
        var alternate = new RuntimeBindingSpec {
            Id = "alternate_root", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.SpawnEntity, TargetId = "root",
            } },
        };
        capped.RuntimeProgram.Bindings = capped.RuntimeProgram.Bindings.Append(alternate).ToArray();
        owner.altFunctionUse = 2;
        Equal(false, host.CanUseItem(owner), "alternate input shares same entity live cap");
        owner.altFunctionUse = 0;
        var source = new EntitySource_ItemUse_WithAmmo(owner, host.Item, ItemID.MusketBall, "concurrency test");
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(capped, "root", owner, source, Vector2.Zero, Vector2.UnitX, 0, 12), "direct producer cannot bypass cap");
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(capped, "root", owner, source, Vector2.Zero, Vector2.UnitX, 1, 12), "child producer cannot bypass cap");
        _rootIntercepts = 0;
        Equal(false, host.Shoot(owner, source, Vector2.Zero, Vector2.UnitX, 0, 0, 0f), "shoot remains native veto");
        host.HoldItem(owner); Equal(0, _rootIntercepts, "shoot/hold cap refuses before native spawn boundary");
        Terraria.Main.projectile[0].active = false;
        Equal(true, host.CanUseItem(owner), "retirement releases capacity without a timer/cache");
        ExpectUnregisteredRootSpawn(() => host.Shoot(owner, source, Vector2.Zero, Vector2.UnitX, 0, 0, 0f), "retired cap permits native spawn entry");
        Reset(); Live(capped, 0, player: 1);
        Equal(true, host.CanUseItem(owner), "other owner does not occupy slots");
        Reset(); var other = ConcurrencyFixture(1); other.Id = "other_definition"; Live(other, 0);
        Equal(true, host.CanUseItem(owner), "other definition does not occupy slots");
        Reset(); other = ConcurrencyFixture(1); var second = System.Text.Json.JsonSerializer.Deserialize<RuntimeEntitySpec>(System.Text.Json.JsonSerializer.Serialize(other.RuntimeProgram.Entities[1]))!;
        second.Id = "second"; other.RuntimeProgram.Entities = other.RuntimeProgram.Entities.Append(second).ToArray(); Live(other, 0, entityId: "second");
        Equal(true, host.CanUseItem(owner), "other entity does not occupy slots");
        Reset(); Live(capped, 0, depth: 1);
        Equal(false, host.CanUseItem(owner), "matching descendant occupies same entity capacity");
        Reset(); var legacy = ConcurrencyFixture(null); Live(legacy, 0); Live(legacy, 1);
        Equal(true, Host(legacy).CanUseItem(owner), "saved absence keeps repeated use semantics");
        Reset(); var multiple = ConcurrencyFixture(3); var multiHost = Host(multiple); Live(multiple, 0); Live(multiple, 1);
        Equal(true, multiHost.CanUseItem(owner), "explicit cap greater than one admits remaining slot");
        Live(multiple, 2); Equal(false, multiHost.CanUseItem(owner), "explicit greater-than-one full cap refused");
        Reset(); var batch = ConcurrencyFixture(3, 2); Live(batch, 0); Live(batch, 1);
        Equal(false, Host(batch).CanUseItem(owner), "whole root batch refused, not clipped to one");
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(batch, "root", owner, source, Vector2.Zero, Vector2.UnitX, 1, 12, requestedCount: 2), "whole event batch refused, not clipped");
        Terraria.Main.projectile[1].active = false;
        ExpectUnregisteredRootSpawn(() => GeneratedProjectile.SpawnRuntimeEntity(batch, "root", owner, source, Vector2.Zero, Vector2.UnitX, 1, 12, requestedCount: 2), "whole event batch fits available slots");
        // Immediate and delayed event producers share the same late admission;
        // pending work is not a live instance and a refused dispatch refunds its ledger.
        Reset();
        var action = new InfiniCrafterLocal.Common.Models.RuntimeEventActionSpec {
            Event = RuntimeEventKind.OnUse, ActionCode = RuntimeEventActionCode.SpawnEntity,
            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
            EntityId = "root", Count = 1, DelayTicks = 2,
        };
        var ledger = new InfiniCrafterLocal.Common.Runtime.RuntimeSpawnBudget(3);
        using var clock = new RuntimeWorldClockScope();
        InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
        Equal(true, InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.TrySchedule(capped,
            capped.RuntimeProgram.Entities[0], action, owner, source, Vector2.Zero, Vector2.UnitX, null, 0, 0, ledger), "delayed spawn reserves event budget");
        Equal(2, ledger.Remaining, "pending event reserves only event ledger");
        Equal(true, host.CanUseItem(owner), "pending event is not a live concurrent instance");
        Live(capped, 0);
        AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
        Equal(0, PendingActions(), "full-cap delayed action retires without replay");
        Equal(3, ledger.Remaining, "full-cap delayed spawn returns unused event budget");
        action.DelayTicks = 0;
        _rootIntercepts = 0;
        InfiniCrafterLocal.Common.Runtime.RuntimeProgramExecutor.ExecuteAction(capped,
            capped.RuntimeProgram.Entities[0], action, owner, source, Vector2.Zero, Vector2.UnitX, null, 0, 0, ledger);
        Equal(0, _rootIntercepts, "immediate action refuses full cap before native spawn");
        Equal(3, ledger.Remaining, "immediate cap refusal returns event budget");
        });
    }
}
