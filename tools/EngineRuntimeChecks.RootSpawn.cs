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
        AssertRootHookCallsCapacity(nameof(GeneratedItem.HoldItem));
        AssertRootHookCallsCapacity(nameof(GeneratedItem.Shoot));
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

    // Examine the compiled canonical hooks, not copied arithmetic in this test.
    // Full NewProjectileDirect is unavailable without registered mod/world content.
    private static void AssertRootHookCallsCapacity(string hook)
    {
        MethodInfo helper = typeof(GeneratedItem).GetMethod("RootBindingSpawnCapacity", BindingFlags.NonPublic | BindingFlags.Static)!;
        MethodInfo method = typeof(GeneratedItem).GetMethod(hook)!;
        byte[] il = method.GetMethodBody()!.GetILAsByteArray()!;
        byte[] token = BitConverter.GetBytes(helper.MetadataToken);
        Equal(true, Enumerable.Range(0, il.Length - token.Length).Any(i => il[i] == 0x28
            && il.AsSpan(i + 1, token.Length).SequenceEqual(token)), hook + " calls root capacity helper");
    }

    private static void RootSpawnPreflightRetainsDepthAndOwnerCaps()
    {
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        Player oldOwner = Terraria.Main.player[0];
        Projectile[] oldProjectiles = Terraria.Main.projectile;
        try
        {
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
            Equal(0, GeneratedProjectile.SpawnRuntimeEntity(data, "root", owner, source,
                Vector2.Zero, Vector2.UnitX, 0,
                GeneratedItem.RootBindingSpawnCapacity(data.RuntimeProgram.TryGetEntity("root")!)), "owner projectile cap remains active");
        }
        finally
        {
            Terraria.Main.projectile = oldProjectiles;
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.myPlayer = oldLocal;
            Terraria.Main.netMode = oldMode;
        }
    }

    private static void RootHooksReachUnregisteredSpawnBoundary()
    {
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        Player oldOwner = Terraria.Main.player[0];
        Projectile[] oldProjectiles = Terraria.Main.projectile;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            var owner = Terraria.Main.player[0] = new Player { active = true, whoAmI = 0, direction = 1 };
            Terraria.Main.projectile = Enumerable.Range(0, oldProjectiles.Length)
                .Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
            // Stop precisely at the real NewProjectileDirect entry. Never return a
            // projectile or claim a game spawn in this unregistered headless process.
            using var intercept = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectileDirect),
                new[] { typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int),
                    typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!,
                (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                    InterceptUnregisteredRootSpawn);
            Equal(0, ModContent.ProjectileType<GeneratedProjectile>(), "generated projectile is not registered in headless check");
            foreach (int eventAllowance in new[] { 0, 7 })
            foreach (int count in new[] { 1, 4 })
            {
                var data = GeneratedItemData.FromJson(RootSpawnFixture(eventAllowance, count).ToNetworkJson())!;
                var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
                var generated = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance)!
                    .SetValue(generated, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                Equal(true, generated.CanUseItem(owner), "root use binding accepted");
                var ledger = (RuntimeSpawnBudget)typeof(GeneratedItem).GetField("_itemEventBudget",
                    BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(generated)!;
                Equal(eventAllowance, ledger.Remaining, "root use starts with authored event ledger");
                var source = new EntitySource_ItemUse_WithAmmo(owner, item, ItemID.MusketBall, "root test");
                ExpectUnregisteredRootSpawn(() => generated.Shoot(owner, source, Vector2.Zero,
                    Vector2.UnitX, 0, 0, 0f), "Shoot event budget=" + eventAllowance + " count=" + count);
                Equal(eventAllowance, ledger.Remaining, "free root Shoot does not spend event ledger");
                ExpectUnregisteredRootSpawn(() => generated.HoldItem(owner), "HoldItem event budget=" + eventAllowance + " count=" + count);
            }
        }
        finally
        {
            Terraria.Main.projectile = oldProjectiles;
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.myPlayer = oldLocal;
            Terraria.Main.netMode = oldMode;
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
