using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using MonoMod.Cil;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void RootBindingSpawnCapacityRespectsAuthoredCountAndIndependentEventLedger()
    {
        // Saved full recipe and network DTO really accept zero (player-save payload
        // stores only an identity reference, not the runtime program).
        foreach (int eventAllowance in new[] { 0, 7 })
        foreach (int authoredCount in new[] { 1, 4, InfiniRuntimeLimits.MaxRuntimeSpawnCount })
        {
            var data = RootSpawnFixture(eventAllowance, authoredCount);
            var saved = GeneratedItemData.FromJson(data.ToJson())
                ?? throw new InvalidOperationException("saved root fixture rejected");
            var wire = GeneratedItemData.FromJson(data.ToNetworkJson())
                ?? throw new InvalidOperationException("wire root fixture rejected");
            foreach (var (variant, copy) in new[] { ("saved", saved), ("wire", wire) })
            {
                Equal(eventAllowance, copy.RuntimeProgram.Limits.MaxEventSpawnsPerActivation, variant + " event limit");
                var entity = copy.RuntimeProgram.TryGetEntity("root")!;
                Equal(authoredCount, entity.Spawn.Count, variant + " root count");
                Equal(authoredCount, GeneratedItem.RootBindingSpawnCapacity(entity), variant + " root allowance ignores event limit");
                var ledger = new RuntimeSpawnBudget(copy.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
                var child = Attach(new Projectile { owner = 0, active = true });
                child.Configure(copy, entity, 0, ledger.Remaining, Vector2.UnitX, activationBudget: ledger);
                Equal(eventAllowance, ledger.Remaining, variant + " free root does not spend event ledger");
                Equal(eventAllowance == 0 ? 0 : 1, ledger.Reserve(1), variant + " child event uses only ledger");
            }
        }
        var raw = new RuntimeEntitySpec { Spawn = new RuntimeSpawnSpec { Enabled = true, Count = int.MaxValue } };
        Equal(InfiniRuntimeLimits.MaxRuntimeSpawnCount, GeneratedItem.RootBindingSpawnCapacity(raw), "global root spawn ceiling");
        RootSpawnPreflightRetainsDepthAndOwnerCaps();
        RootHooksReachUnregisteredSpawnBoundary();
    }

    private static GeneratedItemData RootSpawnFixture(int eventAllowance, int count)
    {
        var data = GeneratedItemData.Placeholder();
        data.RuntimeProgram.PrimaryEntityId = "root";
        data.RuntimeProgram.PrimaryOwner = RuntimeProgramSpec.ProjectileOwner;
        data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = eventAllowance;
        data.RuntimeProgram.ItemUse.Configured = true;
        data.RuntimeProgram.Entities = new[] {
            data.RuntimeProgram.Entities[0],
            new RuntimeEntitySpec {
                Id = "root", Kind = RuntimeEntityKind.StationaryProjectile,
                VisualRole = "deployed_entity",
                Visual = new RuntimeEntityVisualSpec { Role = "deployed_entity", AssetMode = "no_asset" },
                Spawn = new RuntimeSpawnSpec { Enabled = true, Count = count, Aim = "facing" },
            },
        };
        data.RuntimeProgram.Bindings = new[] {
            new RuntimeBindingSpec {
                Id = "use_root", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec {
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.SpawnEntity, TargetId = "root" },
                },
            },
            new RuntimeBindingSpec {
                Id = "hold_root", Input = RuntimeInputKind.Hold, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec {
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.SpawnEntity, TargetId = "root" },
                },
            },
        };
        return data;
    }

    private static void RootSpawnPreflightRetainsDepthAndOwnerCaps()
    {
        using var actorState = new NativeActorState();

        Projectile[] oldProjectiles = Terraria.Main.projectile;
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.myPlayer = 0;
        var owner = Terraria.Main.player[0] = new Player { active = true, whoAmI = 0 };
        var data = RootSpawnFixture(0, 4);
        var source = owner.GetSource_Misc("RootSpawnHeadlessPreflight");
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
            Vector2.Zero, Vector2.UnitX, data.RuntimeProgram.Limits.MaxChildDepth + 1,
            GeneratedItem.RootBindingSpawnCapacity(data.RuntimeProgram.TryGetEntity("root")!)), "depth cap remains active");
        Terraria.Main.projectile = new Projectile[oldProjectiles.Length];
        for (int i = 0; i < Terraria.Main.projectile.Length; i++)
        {
            var projectile = Terraria.Main.projectile[i] = new Projectile {
                active = i < InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner,
                owner = 0, whoAmI = i,
            };
            if (!projectile.active) continue;
            var generated = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        }
        // One remaining global slot must not silently clip a four-shot weapon
        // to one projectile, even with no explicit per-entity maxActive.
        Terraria.Main.projectile[InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner - 1].active = false;
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
            Vector2.Zero, Vector2.UnitX, 0,
            GeneratedItem.RootBindingSpawnCapacity(data.RuntimeProgram.TryGetEntity("root")!)), "owner limit refuses entire volley with one free slot");
        Terraria.Main.projectile[InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner - 1].active = true;
        Equal(0, GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
            Vector2.Zero, Vector2.UnitX, 0,
            GeneratedItem.RootBindingSpawnCapacity(data.RuntimeProgram.TryGetEntity("root")!)), "owner projectile cap remains active");
    }

    private static void RootHooksReachUnregisteredSpawnBoundary()
    {
        using var actorState = new NativeActorState();

        Projectile[] oldProjectiles = Terraria.Main.projectile;
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.myPlayer = 0;
        var owner = Terraria.Main.player[0] = new Player { active = true, whoAmI = 0, direction = 1 };
        Terraria.Main.projectile = Enumerable.Range(0, oldProjectiles.Length)
            .Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
        // Stop precisely at the real NewProjectileDirect entry. Never return a
        // projectile or claim a game spawn in this unregistered headless process.
        // Observe the allowance actually delivered by each item hook. A helper
        // token in its IL neither proves the returned value is used nor survives
        // a behavior-preserving helper extraction/inlining. Keep the real spawn
        // implementation running through the native registration boundary below.
        int? deliveredAllowance = null;
        int allowanceCalls = 0;
        bool underfillAllowance = false;
        using var allowanceObserver = new ILHook(typeof(GeneratedProjectile).GetMethod(
            "SpawnRuntimeEntity", BindingFlags.Static | BindingFlags.NonPublic)!, il => {
            var cursor = new MonoMod.Cil.ILCursor(il);
            cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg, il.Method.Parameters[7]);
            cursor.EmitDelegate<Func<int, int>>(value => {
                int delivered = underfillAllowance ? 1 : value;
                deliveredAllowance = delivered; allowanceCalls++;
                return delivered;
            });
            cursor.Emit(Mono.Cecil.Cil.OpCodes.Starg, il.Method.Parameters[7]);
        });
        using var intercept = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                InterceptUnregisteredRootSpawn);
        void CheckAllowance(int count, string label)
        {
            Equal<int?>(count, deliveredAllowance, label + " full authored root allowance independently of event budget");
            Equal(1, allowanceCalls, label + " enters the spawn owner exactly once");
        }
        Equal(0, ModContent.ProjectileType<GeneratedProjectile>(), "generated projectile is not registered in headless check");
        foreach (int eventAllowance in new[] { 0, 7 })
        foreach (int count in new[] { 1, 4 })
        {
            var data = GeneratedItemData.FromJson(RootSpawnFixture(eventAllowance, count).ToNetworkJson())!;
            var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var generated = new GeneratedItem();
            AttachItem(generated, item, data);
            Equal(true, generated.CanUseItem(owner), "root use binding accepted");
            var ledger = (RuntimeSpawnBudget)typeof(GeneratedItem).GetField("_itemEventBudget",
                BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(generated)!;
            Equal(eventAllowance, ledger.Remaining, "root use starts with authored event ledger");
            var source = new EntitySource_ItemUse_WithAmmo(owner, item, ItemID.MusketBall, "root test");
            deliveredAllowance = null; allowanceCalls = 0;
            ExpectUnregisteredRootSpawn(() => generated.Shoot(owner, source, Vector2.Zero,
                Vector2.UnitX, 0, 0, 0f), "Shoot event budget=" + eventAllowance + " count=" + count);
            CheckAllowance(count, "Shoot");
            Equal(eventAllowance, ledger.Remaining, "free root Shoot does not spend event ledger");
            deliveredAllowance = null; allowanceCalls = 0;
            ExpectUnregisteredRootSpawn(() => generated.HoldItem(owner), "HoldItem event budget=" + eventAllowance + " count=" + count);
            CheckAllowance(count, "HoldItem");
            if (count == 4 && eventAllowance == 0)
            {
                // Sensitivity control: inject a real undersized allowance at
                // the spawn boundary. Batch admission must refuse it, and the
                // same allowance oracle must reject the wrong delivered value.
                underfillAllowance = true; deliveredAllowance = null; allowanceCalls = 0;
                try
                {
                    _rootIntercepts = 0;
                    generated.Shoot(owner, source, Vector2.Zero, Vector2.UnitX, 0, 0, 0f);
                    Equal(0, _rootIntercepts, "underfilled allowance cannot spawn a partial native volley");
                    Equal<int?>(1, deliveredAllowance, "control reached actual spawn owner with wrong allowance");
                    bool rejected = false;
                    try { CheckAllowance(count, "underfilled allowance control"); }
                    catch (InvalidOperationException) { rejected = true; }
                    Equal(true, rejected, "allowance oracle rejects the actual underfilled argument");
                }
                finally { underfillAllowance = false; }
            }
        }
    }

    private static void ExpectUnregisteredRootSpawn(Action hook, string label)
    {
        _rootIntercepts = 0;
        try { hook(); }
        catch (RootSpawnRegistrationBoundary)
        {
            Equal(1, _rootIntercepts, label + " reached exactly one registration boundary");
            return;
        }
        throw new InvalidOperationException(label + " did not reach NewProjectileDirect");
    }

    private sealed class RootSpawnRegistrationBoundary : Exception { }
    private static int _rootIntercepts;
    private static Projectile InterceptUnregisteredRootSpawn(IEntitySource source, Vector2 position,
        Vector2 velocity, int type, int damage, float knockback, int owner,
        float ai0, float ai1, float ai2)
    {
        _rootIntercepts++;
        throw new RootSpawnRegistrationBoundary();
    }
}
