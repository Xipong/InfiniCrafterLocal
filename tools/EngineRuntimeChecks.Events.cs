using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Terraria.ModLoader;
using System.Reflection;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static void EventSpawnZeroMultiplierIsNotReplacedByOne()
    {
        Equal(0f, RuntimeProgramExecutor.EventSpawnDamageMultiplier(
            new RuntimeEventActionSpec { DamageMultiplier = 0f }), "zero child damage multiplier");
        Equal(0.25f, RuntimeProgramExecutor.EventSpawnDamageMultiplier(
            new RuntimeEventActionSpec { DamageMultiplier = 0.25f }), "fractional child damage multiplier");
        ConsumedItemKeepsDelayedUseSourceSnapshot();
        ItemPeriodicDelayedActionRetainsDeclaredMiscSource();
        UnsupportedDelayedSourceFailsClosed();
        ProjectileGenerationRejectsSameIdentityReuse();
        EventSpawnSiblingsShareActivationBudget();
        DelayedEventSourceProvenance();
    }

    private static void ItemPeriodicDelayedActionRetainsDeclaredMiscSource()
    {
        Player oldOwner = Terraria.Main.player[0];
        NPC oldTarget = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode;
        try
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, position = new Vector2(64f, 0f) };
            var entity = new RuntimeEntitySpec { Id = "body_periodic", Kind = RuntimeEntityKind.ItemBody };
            var action = new RuntimeEventActionSpec {
                Event = RuntimeEventKind.Periodic, ActionCode = RuntimeEventActionCode.Pull,
                DelayTicks = 2, PeriodTicks = 6, Mode = "owner_to_target",
                Strength = 2f, RadiusTiles = 10f,
            };
            var generated = new GeneratedItem();
            var item = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generated, item);
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, GeneratedItemData.Placeholder());
            var source = owner.GetSource_Misc("InfiniRuntimePeriodic");
            typeof(GeneratedItem).GetMethod("QueueOrExecuteItemAction", BindingFlags.Instance | BindingFlags.NonPublic)!
                .Invoke(generated, new object?[] { owner, entity, action, target, target.Center,
                    Vector2.UnitX, 0, new RuntimeSpawnBudget(0), source });
            Equal(1, PendingActions(), "item periodic action with its real source is queued");
            Equal(Vector2.Zero, owner.velocity, "periodic action not run before due tick");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(true, owner.velocity.X > 0f, "item periodic action executes after delay");
            Equal(0, PendingActions(), "periodic action retires");
            var spawn = new RuntimeEventActionSpec {
                Event = RuntimeEventKind.Periodic, ActionCode = RuntimeEventActionCode.SpawnEntity,
                DelayTicks = 2, PeriodTicks = 6, Count = 1,
            };
            var budget = new RuntimeSpawnBudget(2);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(), entity,
                spawn, owner, source, target.Center, Vector2.UnitX, null, 0, 0, budget),
                "item periodic delayed spawn accepts its exact Misc source");
            Equal(1, budget.Remaining, "item periodic delayed spawn reserves exactly one");
            RuntimeDelayedActionScheduler.Clear();
            Equal(2, budget.Remaining, "clearing periodic delayed spawn returns reservation");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            Terraria.Main.netMode = oldMode;
        }
    }

    private static void UnsupportedDelayedSourceFailsClosed()
    {
        Player oldOwner = Terraria.Main.player[0];
        Projectile oldProjectile = Terraria.Main.projectile[0];
        int oldMode = Terraria.Main.netMode;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 2, active = true };
            var spawn = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.SpawnEntity, DelayTicks = 2, Count = 2 };
            var budget = new RuntimeSpawnBudget(3);
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(),
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner,
                owner.GetSource_Misc("unknown"), Vector2.Zero, Vector2.UnitX, null, 0, 0, budget),
                "unsupported Misc source rejected without reservation");
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(),
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.FreeProjectile }, spawn, owner,
                projectile.GetSource_FromThis(), Vector2.Zero, Vector2.UnitX, null, 0, 0, budget),
                "projectile without generation cannot prove same-object reuse safety");
            Equal(3, budget.Remaining, "unknown sources do not reserve slots");
            Equal(0, PendingActions(), "unknown sources never enter queue");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.projectile[0] = oldProjectile;
            Terraria.Main.netMode = oldMode;
        }
    }

    private static void ProjectileGenerationRejectsSameIdentityReuse()
    {
        Player oldOwner = Terraria.Main.player[0];
        Projectile oldProjectile = Terraria.Main.projectile[0];
        NPC oldTarget = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, position = new Vector2(100, 0) };
            var projectile = Terraria.Main.projectile[0] = new Projectile {
                whoAmI = 0, owner = 0, type = ProjectileID.WoodenArrowFriendly, identity = 93, active = true,
                CritChance = 19, ArmorPenetration = 7,
            };
            var generation = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generation);
            var source = projectile.GetSource_FromThis();
            var spawn = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.SpawnEntity, DelayTicks = 2, Count = 2 };
            var budget = new RuntimeSpawnBudget(3);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(),
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.FreeProjectile }, spawn,
                owner, source, Vector2.Zero, Vector2.UnitX, null, 0, 0, budget), "projectile generation queued");
            Equal(1, budget.Remaining, "projectile generation reserves two");
            var pull = new RuntimeEventActionSpec {
                ActionCode = RuntimeEventActionCode.Pull, DelayTicks = 2,
                Mode = "owner_to_target", Strength = 2f, RadiusTiles = 10f,
            };
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(),
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.FreeProjectile }, pull,
                owner, source, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "projectile impulse queued");
            // Installed Projectile.SetDefaults clears ModProjectile and instantiates a new one.
            // Mirror that exact same-object generation transition without loading mod content/world.
            var nextGeneration = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, nextGeneration);
            Equal(93, projectile.identity, "same-slot reuse keeps identity");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(3, budget.Remaining, "same-slot/type/identity new ModProjectile releases reservation");
            Equal(0, PendingActions(), "old projectile generation retires");
            Equal(Vector2.Zero, owner.velocity, "new generation cannot inherit old terminal impulse");
            projectile.active = false; // on_kill/on_expire may enqueue after the parent retires
            var terminalSource = projectile.GetSource_FromThis();
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(),
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.FreeProjectile }, pull,
                owner, terminalSource, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "retired original queues terminal action");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(true, owner.velocity.X > 0, "inactive same-generation projectile dispatches terminal action");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.projectile[0] = oldProjectile;
            Terraria.Main.npc[0] = oldTarget;
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
        }
    }

    private static void ConsumedItemKeepsDelayedUseSourceSnapshot()
    {
        Player oldOwner = Terraria.Main.player[0];
        NPC oldTarget = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var target = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, position = new Vector2(100, 0) };
            var item = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1,
                damage = 37, crit = 13, ArmorPenetration = 8 };
            int originalType = item.type;
            var source = new EntitySource_ItemUse(owner, item, "original delayed use");
            var immediateChild = new Projectile { damage = 5, DamageType = DamageClass.Generic };
            immediateChild.ApplyStatsFromSource(source); // installed tML consumer before stack spend
            var data = GeneratedItemData.Placeholder();
            var entity = new RuntimeEntitySpec { Id = "source_item", Kind = RuntimeEntityKind.ItemBody };
            var pull = new RuntimeEventActionSpec {
                Event = "on_use", ActionCode = RuntimeEventActionCode.Pull, DelayTicks = 2,
                Mode = "owner_to_target", Strength = 2f, RadiusTiles = 10f,
            };
            var budget = new RuntimeSpawnBudget(3);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, pull,
                owner, source, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "one-stack use queued");
            item.stack = 0; // exact ConsumeItem result at stackCost=1
            owner.inventory[0] = new Item { type = originalType, stack = 1 }; // inventory refill/reuse
            var captured = FirstDelayedSource();
            Equal(true, captured is EntitySource_ItemUse, "consumed source keeps tML subtype");
            Equal(true, captured.Context == "original delayed use", "consumed source keeps context");
            var saved = ((IEntitySource_WithStatsFromItem)captured).Item;
            Equal(originalType, saved.type, "consumed source keeps type");
            Equal(1, saved.stack, "consumed source keeps usable stack");
            Equal(13, saved.crit, "consumed source keeps crit");
            Equal(8, saved.ArmorPenetration, "consumed source keeps armor penetration");
            var delayedChild = new Projectile { damage = 5, DamageType = DamageClass.Generic };
            delayedChild.ApplyStatsFromSource(captured); // same installed tML consumer after stack spend
            Equal(immediateChild.CritChance, delayedChild.CritChance, "tML child crit parity after consumption");
            Equal(immediateChild.ArmorPenetration, delayedChild.ArmorPenetration, "tML child armor penetration parity");
            Equal(immediateChild.OriginalCritChance, delayedChild.OriginalCritChance, "tML original crit parity");
            Equal(immediateChild.OriginalArmorPenetration, delayedChild.OriginalArmorPenetration, "tML original armor penetration parity");
            Equal(immediateChild.originalDamage, delayedChild.originalDamage, "tML original damage parity");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(true, owner.velocity.X > 0, "consumed item action dispatches after slot replacement");
            Equal(0, PendingActions(), "consumed item action retires");

            owner.velocity = Vector2.Zero;
            var reused = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1,
                damage = 58, crit = 17, ArmorPenetration = 11 };
            var ammoSource = new EntitySource_ItemUse_WithAmmo(owner, reused, ItemID.MusketBall, "ammo context");
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, pull,
                owner, ammoSource, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "ammo item queued");
            reused.SetDefaults(ItemID.TinShortsword);
            captured = FirstDelayedSource();
            Equal(true, captured is EntitySource_ItemUse_WithAmmo, "ammo subtype preserved");
            Equal(ItemID.MusketBall, ((EntitySource_ItemUse_WithAmmo)captured).AmmoItemIdUsed, "ammo ID preserved");
            Equal(true, captured.Context == "ammo context", "ammo context preserved");
            saved = ((IEntitySource_WithStatsFromItem)captured).Item;
            Equal(ItemID.CopperShortsword, saved.type, "SetDefaults does not change snapshot type");
            Equal(17, saved.crit, "SetDefaults does not change snapshot crit");
            Equal(11, saved.ArmorPenetration, "SetDefaults does not change snapshot armor penetration");
            Equal(58, saved.damage, "SetDefaults does not change snapshot damage");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(true, owner.velocity.X > 0, "same-object SetDefaults does not cancel queued use");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
        }
    }

    // Exercise the canonical scheduler with real tML source objects. Spawning a
    // projectile still requires registered content/world; no NewProjectileDirect here.
    private static void DelayedEventSourceProvenance()
    {
        var oldOwner = Terraria.Main.player[0];
        var oldProjectile = Terraria.Main.projectile[0];
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var item = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
            var data = GeneratedItemData.Placeholder();
            var entity = new RuntimeEntitySpec { Id = "source_item", Kind = RuntimeEntityKind.ItemBody };
            var spawn = new RuntimeEventActionSpec {
                ActionCode = RuntimeEventActionCode.SpawnEntity, DelayTicks = 2, Count = 2,
            };
            var itemSource = owner.GetSource_ItemUse(item);
            Equal(true, itemSource is IEntitySource_WithStatsFromItem, "item source carries stat lineage");
            var budget = new RuntimeSpawnBudget(3);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, itemSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, budget), "item spawn queued");
            var queued = FirstDelayedSource();
            Equal(false, ReferenceEquals(itemSource, queued), "queued item source is a defensive snapshot");
            Equal(true, queued is EntitySource_ItemUse, "queued item source has actual tML type");
            Equal(true, ReferenceEquals(owner, ((EntitySource_Parent)queued).Entity), "queued item parent is owner");
            Equal(false, ReferenceEquals(item, ((IEntitySource_WithStatsFromItem)queued).Item), "queued item is a copy");
            Equal(1, budget.Remaining, "item delayed spawn reserves two");
            owner.inventory[0] = new Item { type = item.type, stack = 1 }; // same type, reused slot
            Equal(item.type, ((IEntitySource_WithStatsFromItem)queued).Item.type, "slot reuse leaves item source intact");
            RuntimeDelayedActionScheduler.Clear();
            Equal(3, budget.Remaining, "clearing item snapshot returns reservation");
            var mutatedItem = owner.inventory[0];
            var mutatedSource = owner.GetSource_ItemUse(mutatedItem);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, mutatedSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, budget), "item mutation snapshot queued");
            mutatedItem.type = ItemID.TinShortsword; // same reference repurposed in place
            Equal(ItemID.CopperShortsword, ((IEntitySource_WithStatsFromItem)FirstDelayedSource()).Item.type,
                "repurposed item does not alter source snapshot");
            RuntimeDelayedActionScheduler.Clear();
            Equal(3, budget.Remaining, "repurposed item clear releases delayed reservation");

            // The real item callsite must forward its already-created source,
            // rather than letting the scheduler fabricate a new one.
            var generatedItem = new GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generatedItem, owner.inventory[0]);
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(generatedItem, data);
            var itemEventSource = owner.GetSource_ItemUse(owner.inventory[0]);
            var itemEventBudget = new RuntimeSpawnBudget(2);
            typeof(GeneratedItem).GetMethod("QueueOrExecuteItemAction", BindingFlags.NonPublic | BindingFlags.Instance)!
                .Invoke(generatedItem, new object?[] { owner, entity, spawn, null, Vector2.Zero, Vector2.UnitX, 0, itemEventBudget, itemEventSource });
            Equal(false, ReferenceEquals(itemEventSource, FirstDelayedSource()), "real item event callsite snapshots source");
            Equal(true, FirstDelayedSource() is EntitySource_ItemUse, "item callsite retains tML source type");
            RuntimeDelayedActionScheduler.Clear();
            Equal(2, itemEventBudget.Remaining, "item callsite clear releases reservation");

            var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 84, active = true };
            var generatedProjectile = Attach(projectile);
            typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generatedProjectile);
            var projectileSource = projectile.GetSource_FromThis();
            var projectileBudget = new RuntimeSpawnBudget(3);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, projectileSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, projectileBudget), "projectile spawn queued");
            queued = FirstDelayedSource();
            Equal(true, ReferenceEquals(projectileSource, queued), "exact projectile source queued");
            Equal(true, queued is EntitySource_Parent, "queued projectile is parent source");
            Equal(true, ReferenceEquals(projectile, ((EntitySource_Parent)queued).Entity), "queued projectile parent is original");
            projectile.active = false; // terminal event can outlive its parent
            RuntimeDelayedActionScheduler.Update();
            Equal(1, projectileBudget.Remaining, "dead original retains reservation before due tick");
            projectile.identity = 85; // same object reused in slot (no active requirement)
            RuntimeDelayedActionScheduler.Update();
            Equal(3, projectileBudget.Remaining, "reused projectile identity returns reservation");
            Equal(0, PendingActions(), "reused projectile source retired");
            projectile.identity = 86;
            var replacedSource = projectile.GetSource_FromThis();
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, replacedSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, projectileBudget), "projectile slot guard queued");
            Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 86, active = true };
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(3, projectileBudget.Remaining, "same-identity slot replacement releases reservation");
            Equal(0, PendingActions(), "replaced projectile retired");
            Terraria.Main.projectile[0] = projectile;
            var projectileEventBudget = new RuntimeSpawnBudget(3);
            var projectileEntity = Entity();
            projectileEntity.Id = "source_projectile";
            projectileEntity.Kind = RuntimeEntityKind.FreeProjectile;
            projectileEntity.Events = new[] { new RuntimeEventActionSpec {
                Event = "on_kill", ActionCode = RuntimeEventActionCode.SpawnEntity,
                DelayTicks = 2, Count = 2,
            } };
            generatedProjectile.Configure(data, projectileEntity, 0, 3, Vector2.UnitX, activationBudget: projectileEventBudget);
            typeof(GeneratedProjectile).GetMethod("RunRuntimeEvent", BindingFlags.NonPublic | BindingFlags.Instance)!
                .Invoke(generatedProjectile, new object?[] { "on_kill", null, 0 });
            queued = FirstDelayedSource();
            Equal(true, queued is EntitySource_Parent, "projectile callsite source retains parent type");
            Equal(true, ReferenceEquals(projectile, ((EntitySource_Parent)queued).Entity), "projectile callsite retains parent identity");
            Equal(1, projectileEventBudget.Remaining, "projectile callsite reserves spawn slots");
            RuntimeDelayedActionScheduler.Clear();
            Equal(3, projectileEventBudget.Remaining, "projectile callsite clear returns reservation");
            var terminal = new RuntimeEventActionSpec {
                ActionCode = RuntimeEventActionCode.Pull, DelayTicks = 2,
                Mode = "owner_to_target", Strength = 2f, RadiusTiles = 10f,
            };
            var terminalSource = projectile.GetSource_FromThis();
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, terminal,
                owner, terminalSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, projectileBudget), "inactive original queues terminal event");
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(0, PendingActions(), "terminal source dispatches despite inactivity");
            Equal(3, projectileBudget.Remaining, "nonspawn terminal preserves budget");
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, terminalSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, projectileBudget), "remote authority probe queued");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Terraria.Main.myPlayer = 1;
            RuntimeDelayedActionScheduler.Update();
            RuntimeDelayedActionScheduler.Update();
            Equal(3, projectileBudget.Remaining, "nonlocal owner does not spend delayed reservation");
            Equal(0, PendingActions(), "nonlocal action retired");
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn,
                owner, terminalSource, Vector2.Zero, Vector2.UnitX, null, 0, 0, projectileBudget), "clear probe reserved");
            Equal(1, projectileBudget.Remaining, "clear probe spent reservation");
            RuntimeDelayedActionScheduler.Clear();
            Equal(3, projectileBudget.Remaining, "clear returns delayed reservation");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.projectile[0] = oldProjectile;
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
        }
    }

    private static IEntitySource FirstDelayedSource()
    {
        var pending = typeof(RuntimeDelayedActionScheduler).GetField("Pending", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
        var first = ((System.Collections.IList)pending)[0]!;
        return (IEntitySource)first.GetType().GetProperty("Source")!.GetValue(first)!;
    }

    // CPU-only observer of the actual Configure seam; NewProjectileDirect requires
    // registered mod content/world and is not available in this harness.
    private static void EventSpawnSiblingsShareActivationBudget()
    {
        var data = GeneratedItemData.Placeholder();
        var a = Entity();
        a.Id = "budget_a";
        var first = Attach(new Projectile { owner = 0, active = true });
        var second = Attach(new Projectile { owner = 0, active = true });
        var ledger = new RuntimeSpawnBudget(3);
        first.Configure(data, a, 0, 3, Vector2.UnitX, activationBudget: ledger);
        second.Configure(data, a, 0, 3, Vector2.UnitX, activationBudget: ledger);
        var field = typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.NonPublic | BindingFlags.Instance)!;
        Equal(true, ReferenceEquals(ledger, field.GetValue(first)), "first root carries activation ledger");
        Equal(true, ReferenceEquals(field.GetValue(first), field.GetValue(second)), "two root A siblings share ledger");
        Equal(3, ledger.Remaining, "root binding projectiles do not consume event budget");
        int spawned = 0;
        // Exercise the same Reserve operation used by the hooked event executor:
        // A1 -> B1 -> B1 descendant, then A2 -> B2 -> denied descendant.
        for (int attempt = 0; attempt < 4; attempt++) spawned += ledger.Reserve(1);
        Equal(3, spawned, "two A with B+B allow only three event spawns");
        Equal(0, ledger.Remaining, "shared ledger exhausted");
        var anotherActivation = new RuntimeSpawnBudget(3);
        Equal(3, anotherActivation.Reserve(3), "independent activation retains its own allowance");

        Player previous = Terraria.Main.player[0];
        int previousMode = Terraria.Main.netMode;
        int previousLocal = Terraria.Main.myPlayer;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var delayed = new RuntimeEventActionSpec {
                ActionCode = RuntimeEventActionCode.SpawnEntity, DelayTicks = 2, Count = 2,
            };
            var delayedLedger = new RuntimeSpawnBudget(3);
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, a, delayed,
                Terraria.Main.player[0], Terraria.Main.player[0].GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 }),
                Vector2.Zero, Vector2.UnitX, null, 0, 0, delayedLedger),
                "real scheduler accepts delayed reservation");
            Equal(1, delayedLedger.Remaining, "delayed B+B reserves two before due tick");
            Equal(1, delayedLedger.Reserve(1), "unreserved descendant spends last shared slot");
            Equal(0, delayedLedger.Reserve(1), "sibling and descendant cannot overdraw delayed reservation");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Terraria.Main.myPlayer = 1;
            var peer = Attach(new Projectile { owner = 0, active = true });
            peer.Configure(data, a, 0, 3, Vector2.UnitX);
            Equal(true, field.GetValue(peer) is null, "network peer does not mint an owner-local budget from AI snapshot");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = previous;
            Terraria.Main.netMode = previousMode;
            Terraria.Main.myPlayer = previousLocal;
        }
    }

    private static void EventDamageUsesAuthoredSource()
    {
        var oldMetrics = Terraria.Main.SceneMetrics;
        NPC[] oldNpcs = (NPC[])Terraria.Main.npc.Clone();
        Player[] oldPlayers = (Player[])Terraria.Main.player.Clone();
        int oldMode = Terraria.Main.netMode;
        var oldRandom = Terraria.Main.rand;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            for (int i = 0; i < Terraria.Main.player.Length; i++) Terraria.Main.player[i] = new Player { whoAmI = i, active = false };
            var owner = new Player { whoAmI = 0, active = true };
            Terraria.Main.player[0] = owner;
            Terraria.Main.SceneMetrics = new SceneMetrics();
            owner.GetArmorPenetration(Terraria.ModLoader.DamageClass.Magic) += 40f;
            NPC Target(int slot, float x) => new NPC {
                whoAmI = slot, active = true, life = 1000, lifeMax = 1000,
                defense = 80, width = 20, height = 20, position = new Vector2(x, 1600f),
                HideStrikeDamage = true, // no combat-text/font resources in this CPU check
            };
            int checkedCases = 0;
            var deliveries = new[] {
                (Event: "on_hit", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_crit", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 1, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 10, ExpectedHit: false),
                (Event: "on_expire", FinalAI: true, Life: 0, ExpectedHit: true),
                (Event: "on_kill", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "on_kill", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_kill", FinalAI: true, Life: 0, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 1, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 10, ExpectedHit: false),
                (Event: "terminal_pair", FinalAI: true, Life: 0, ExpectedHit: true),
            };
            foreach (bool itemBody in new[] { false, true })
            foreach (bool chain in new[] { false, true })
            foreach (int delay in new[] { 0, 2 })
            foreach (var delivery in deliveries)
            foreach (int killDelay in new[] { -1, 0, 2, 4 })
            {
                bool pair = delivery.Event == "terminal_pair";
                if ((pair && killDelay < 0) || (!pair && killDelay >= 0)) continue;
                bool terminal = pair || delivery.Event is "on_expire" or "on_kill";
                // The registry only permits these terminal damage events on projectile AoE.
                if (terminal && (itemBody || chain)) continue;
                bool crit = delivery.Event == "on_crit";
                string label = $"{(itemBody ? "item" : "projectile")} {(chain ? "chain" : "area")} delay={delay} event={delivery.Event} finalAI={delivery.FinalAI} life={delivery.Life} killDelay={killDelay}";
                RuntimeDelayedActionScheduler.Clear();
                try
                {
                    NPC direct = Terraria.Main.npc[0] = Target(0, 1600f);
                    NPC nearby = Terraria.Main.npc[1] = Target(1, 1640f);
                    NPC outside = Terraria.Main.npc[2] = Target(2, 2400f);
                    Equal(true, nearby.CanBeChasedBy(), "fixture is eligible");
                    NPC control = Target(3, 2600f);
                    // Observe real Terraria defense + class-specific armor penetration,
                    // not a reimplementation of its damage formula.
                    owner.ApplyDamageToNPC(control, 50, 0f, 1, false, Terraria.ModLoader.DamageClass.Magic, false);
                    Equal(true, control.life < 1000, "real control damage was applied");
                    var data = GeneratedItemData.Placeholder();
                    data.Gameplay.Damage = itemBody ? 100 : 20;
                    data.Gameplay.DamageClass = itemBody ? "magic" : "melee";
                    var action = new RuntimeEventActionSpec {
                        Id = "event_damage_probe", Event = pair ? "on_expire" : delivery.Event, DelayTicks = delay,
                        Action = chain ? "chain_damage_on_event" : "damage_area_on_event",
                        ActionCode = chain ? RuntimeEventActionCode.ChainDamage : RuntimeEventActionCode.DamageArea,
                        DamageMultiplier = 0.5f, RadiusPx = 120, RangeTiles = 8f, Count = 1,
                    };
                    action.NormalizeAndValidate();
                    var entity = itemBody ? new RuntimeEntitySpec() : Entity();
                    entity.Id = "damage_source";
                    entity.Kind = itemBody ? RuntimeEntityKind.ItemBody : RuntimeEntityKind.FreeProjectile;
                    if (!itemBody) entity.Damage.DamageClass = "magic";
                    entity.Events = new[] { action };
                    if (pair)
                    {
                        var killAction = new RuntimeEventActionSpec {
                            Id = "kill_damage_probe", Event = "on_kill", DelayTicks = killDelay,
                            Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                            DamageMultiplier = 0.75f, RadiusPx = 120,
                        };
                        killAction.NormalizeAndValidate();
                        entity.Events = new[] { action, killAction };
                    }
                    // Live damage/damageDone are deliberately different from authored 100.
                    var projectile = new Projectile { owner = 0, active = true, damage = 777 };
                    if (itemBody)
                    {
                        data.RuntimeProgram.ItemEntityId = entity.Id;
                        data.RuntimeProgram.Entities = new[] { entity };
                        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                            Id = "contact", Input = RuntimeInputKind.PrimaryUse,
                            UsePolicy = new RuntimeBindingUsePolicySpec {
                                ContactDamage = true,
                                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity.Id },
                            },
                        } };
                        var generatedItem = new GeneratedItem();
                        var hostItem = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1, damage = 777 };
                        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                            .SetValue(generatedItem, hostItem);
                        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generatedItem, data);
                        generatedItem.OnHitNPC(owner, direct, new NPC.HitInfo { Crit = crit }, 333);
                    }
                    else
                    {
                        var generated = Attach(projectile);
                        generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                        projectile.Center = direct.Center;
                        if (terminal)
                        {
                            if (delivery.FinalAI)
                            {
                                projectile.timeLeft = 2;
                                generated.AI();
                                Equal(1000, nearby.life, label + " no damage before final AI");
                                Equal(0, PendingActions(), label + " no early reservation");
                                projectile.timeLeft = 1;
                                generated.AI();
                                if (pair)
                                {
                                    Equal(delay == 0 ? control.life : 1000, nearby.life, label + " final AI runs only expiry, before OnKill");
                                    Equal(delay == 0 ? control.life : 1000, direct.life, label + " final AI center target");
                                    Equal(delay > 0 ? 1 : 0, PendingActions(), label + " final AI reserves only expiry");
                                }
                            }
                            projectile.active = false;
                            generated.OnKill(delivery.Life);
                        }
                        else
                            generated.OnHitNPC(direct, new NPC.HitInfo { Crit = crit }, 333);
                    }
                    if (pair)
                    {
                        // Distinct multipliers make a lost kill/duplicated expiry observable.
                        // Build each expected transition with the actual Terraria damage API.
                        control.life = 1000;
                        void CheckPairTick(int tick)
                        {
                            if (delivery.ExpectedHit && delay == tick)
                                owner.ApplyDamageToNPC(control, 50, 0f, 1, false, DamageClass.Magic, false);
                            if (killDelay == tick)
                                owner.ApplyDamageToNPC(control, 75, 0f, 1, false, DamageClass.Magic, false);
                            Equal(control.life, nearby.life, label + " independent events tick=" + tick);
                            Equal(control.life, direct.life, label + " center receives both events tick=" + tick);
                            Equal(1000, outside.life, label + " captured center excludes distant target");
                            int pending = (delivery.ExpectedHit && delay > tick ? 1 : 0) + (killDelay > tick ? 1 : 0);
                            Equal(pending, PendingActions(), label + " exact remaining actions tick=" + tick);
                        }
                        CheckPairTick(0);
                        projectile.Center = outside.Center;
                        projectile.damage = 1;
                        for (int tick = 1; tick <= Math.Max(delay, killDelay) + 1; tick++)
                        {
                            RuntimeDelayedActionScheduler.Update();
                            CheckPairTick(tick);
                        }
                        checkedCases++;
                        continue;
                    }
                    if (delay > 0)
                    {
                        Equal(1000, nearby.life, label + " not immediate");
                        projectile.active = false; // delayed action outlives its projectile
                        projectile.damage = 1;
                        projectile.Center = outside.Center; // queued position must not follow the retired host
                        RuntimeDelayedActionScheduler.Update();
                        Equal(1000, nearby.life, label + " not early");
                        RuntimeDelayedActionScheduler.Update();
                    }
                    int expectedLife = delivery.ExpectedHit ? control.life : 1000;
                    Equal(expectedLife, nearby.life, label + " authored damage exactly once, or no premature expiry");
                    Equal(terminal ? expectedLife : 1000, direct.life, label + " terminal AoE has no excluded hit target");
                    Equal(1000, outside.life, label + " excludes out-of-range target");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(expectedLife, nearby.life, label + " no delayed replay");
                    Equal(0, PendingActions(), label + " queue fully retired");
                    checkedCases++;
                }
                catch (Exception error) { failures.Add(label + ": " + error); }
            }
            // Proximity detonation did not directly strike the nearest NPC. It
            // must not reuse the on_hit exclusion that prevents double damage.
            foreach (int proximityDelay in new[] { 0, 2 })
            {
                RuntimeDelayedActionScheduler.Clear();
                for (int i = 0; i < Terraria.Main.npc.Length; i++)
                    Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
                NPC detonatedAt = Terraria.Main.npc[0] = Target(0, 1600f);
                NPC splashNeighbor = Terraria.Main.npc[1] = Target(1, 1650f);
                var proximityData = GeneratedItemData.Placeholder();
                var proximityEntity = Entity();
                proximityEntity.Id = "proximity_damage_source";
                proximityEntity.Kind = RuntimeEntityKind.FreeProjectile;
                proximityEntity.Movement.Name = "move_proximity_missile";
                proximityEntity.Movement.Code = 13;
                proximityEntity.Movement.Params.RangeTiles = 6f;
                proximityEntity.Movement.Params.HomingStrength = .1f;
                proximityEntity.Movement.Params.ProximityRadiusPx = 64f;
                proximityEntity.Events = new[] { new RuntimeEventActionSpec {
                    Id = "proximity_damage", Event = RuntimeEventKind.OnExpire,
                    Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                    RadiusPx = 120, DamageMultiplier = 1f, DelayTicks = proximityDelay,
                } };
                var proximityHost = new Projectile { owner = 0, active = true, damage = 100 };
                proximityHost.Center = detonatedAt.Center;
                var proximityGenerated = Attach(proximityHost);
                proximityGenerated.Configure(proximityData, proximityEntity, 0, 8, Vector2.UnitX);
                proximityGenerated.AI();
                if (proximityDelay > 0)
                {
                    Equal(1000, detonatedAt.life, "delayed proximity AoE does not strike early");
                    RuntimeDelayedActionScheduler.Update();
                    RuntimeDelayedActionScheduler.Update();
                }
                Equal(true, splashNeighbor.life < 1000, "proximity AoE damages neighboring NPC");
                Equal(true, detonatedAt.life < 1000, "proximity AoE damages its trigger NPC without a direct hit");
            }
            Console.WriteLine($"DETAIL: event damage scenarios passed={checkedCases}");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Array.Copy(oldNpcs, Terraria.Main.npc, oldNpcs.Length);
            Array.Copy(oldPlayers, Terraria.Main.player, oldPlayers.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.rand = oldRandom;
            Terraria.Main.SceneMetrics = oldMetrics;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void DelayedStatusKeepsOriginalNpc()
    {
        NPC[] oldNpcs = (NPC[])Terraria.Main.npc.Clone();
        Player[] oldPlayers = (Player[])Terraria.Main.player.Clone();
        int oldMode = Terraria.Main.netMode;
        bool oldGoodWorld = Terraria.Main.getGoodWorld;
        var oldRandom = Terraria.Main.rand;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.getGoodWorld = false;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            for (int i = 0; i < Terraria.Main.player.Length; i++) Terraria.Main.player[i] = new Player { whoAmI = i, active = false };
            var owner = new Player { whoAmI = 0, active = true };
            Terraria.Main.player[0] = owner;
            foreach (string state in new[] { "same", "transform", "inactive", "new_same_type", "new_other_type", "absent" })
            {
                RuntimeDelayedActionScheduler.Clear();
                try
                {
                    Terraria.Main.npc[0].active = false;
                    int slot = NPC.NewNPC(owner.GetSource_Misc("engine_delayed_npc_check"), 1600, 1600, NPCID.BlueSlime);
                    Equal(0, slot, state + " original NPC occupies slot zero");
                    NPC original = Terraria.Main.npc[slot];
                    Equal(false, original.buffImmune[BuffID.OnFire], "real slime allows selected status");
                    var action = new RuntimeEventActionSpec {
                        Id = "delayed_status_probe", Event = "on_hit", DelayTicks = 2,
                        Action = "apply_status_on_event", ActionCode = RuntimeEventActionCode.ApplyStatus,
                        BuffId = BuffID.OnFire, DurationTicks = 90,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    Equal(true, ScheduleTestItemAction(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action,
                        owner, original.Center, Vector2.UnitX, state == "absent" ? null : original, 10, 0, ref budget), state + " queued");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(false, original.HasBuff(BuffID.OnFire), state + " not early");
                    bool sameEntity = state is "same" or "transform";
                    if (!sameEntity && state != "absent") original.active = false;
                    if (state == "transform")
                    {
                        original.Transform(NPCID.Zombie);
                        Equal(true, ReferenceEquals(original, Terraria.Main.npc[slot]), "real Transform preserves NPC instance");
                        Equal(NPCID.Zombie, original.type, "real Transform changes type");
                        Equal(slot, original.whoAmI, "real Transform retains slot");
                        Equal(true, original.active, "transformed target remains active");
                        Equal(false, original.buffImmune[BuffID.OnFire], "transformed target permits status");
                    }
                    if (state.StartsWith("new_", StringComparison.Ordinal))
                    {
                        int type = state == "new_same_type" ? NPCID.BlueSlime : NPCID.Zombie;
                        int replacementSlot = NPC.NewNPC(owner.GetSource_Misc("engine_delayed_npc_reuse"), 1600, 1600, type);
                        Equal(slot, replacementSlot, state + " real NewNPC reuses the slot");
                        Equal(false, ReferenceEquals(original, Terraria.Main.npc[slot]), state + " real NewNPC replaces the instance");
                        Equal(type, Terraria.Main.npc[slot].type, state + " actual replacement type");
                    }
                    RuntimeDelayedActionScheduler.Update();
                    Equal(sameEntity, Terraria.Main.npc[slot].HasBuff(BuffID.OnFire), state + " only original hit target gets status");
                    if (sameEntity)
                    {
                        int index = original.FindBuffIndex(BuffID.OnFire);
                        Equal(90, original.buffTime[index], "authored duration reaches real NPC.AddBuff");
                        original.buffTime[index] = 17;
                        RuntimeDelayedActionScheduler.Update();
                        Equal(17, original.buffTime[index], "retired delayed status does not refresh again");
                    }
                }
                catch (Exception error) { failures.Add(state + ": " + error); }
            }
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Array.Copy(oldNpcs, Terraria.Main.npc, oldNpcs.Length);
            Array.Copy(oldPlayers, Terraria.Main.player, oldPlayers.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.getGoodWorld = oldGoodWorld;
            Terraria.Main.rand = oldRandom;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static bool ScheduleTestItemAction(GeneratedItemData data, RuntimeEntitySpec entity,
        RuntimeEventActionSpec action, Player owner, Vector2 position, Vector2 direction,
        NPC? target, int damageDone, int childDepth, ref int remainingBudget)
    {
        // The test's legacy ref-budget convenience must still provide a real
        // item-use source; production scheduling never fabricates Misc lineage.
        var budget = new RuntimeSpawnBudget(remainingBudget);
        bool queued = RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner,
            owner.GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 }),
            position, direction, target, damageDone, childDepth, budget);
        remainingBudget = budget.Remaining;
        return queued;
    }

    private static void DelayedQueueHonorsLimits()
    {
        var oldOwner = Terraria.Main.player[0];
        var oldTarget = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode;
        try
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var owner = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            Terraria.Main.player[0] = owner;
            var target = new NPC { whoAmI = 0, active = true, knockBackResist = 1f };
            target.Center = new Vector2(32f, 0f);
            Terraria.Main.npc[0] = target;
            var data = GeneratedItemData.Placeholder();
            var pull = new RuntimeEventActionSpec {
                Id = "queue_budget_probe", Event = "on_hit", DelayTicks = 2,
                Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                Mode = "target_to_owner", Strength = 2f, RadiusTiles = 10f,
            };
            pull.NormalizeAndValidate();
            int budget = 5;
            int capacity = InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxPendingRuntimeActions;
            int perTick = InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick;
            for (int i = 0; i < capacity; i++)
                Equal(true, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                    target, 0, 0, ref budget), "queue accepts entry " + i);
            Equal(false, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                target, 0, 0, ref budget), "full queue rejects overflow");
            var spawn = new RuntimeEventActionSpec { DelayTicks = 2, ActionCode = RuntimeEventActionCode.SpawnEntity, Count = 3 };
            // Reservation-only probe. Do not dispatch this synthetic spawn or claim entity-spawn proof.
            Equal(false, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "full queue rejects spawn before reserving budget");
            Equal(5, budget, "rejection and non-spawn actions leave budget unchanged");
            RuntimeDelayedActionScheduler.Update();
            Equal(Vector2.Zero, target.velocity, "no early queue execution");
            int executed = 0;
            while (executed < capacity)
            {
                RuntimeDelayedActionScheduler.Update();
                executed = Math.Min(capacity, executed + perTick);
                Equal(new Vector2(-2f * executed, 0f), target.velocity, "real executor effects respect per-tick limit");
            }
            RuntimeDelayedActionScheduler.Update();
            Equal(new Vector2(-2f * capacity, 0f), target.velocity, "all accepted actions execute exactly once");
            Equal(true, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "drained queue accepts reservation");
            Equal(2, budget, "first reservation consumes exact requested count");
            Equal(true, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "last partial budget can be reserved");
            Equal(0, budget, "second reservation cannot overdraw budget");
            Equal(false, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "zero spawn budget rejects reservation");
            new RuntimeDelayedActionSystem().OnWorldUnload();
            // If unload left the reserved entries, the following full-capacity fill would fail.
            for (int i = 0; i < capacity; i++)
                Equal(true, ScheduleTestItemAction(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                    target, 0, 0, ref budget), "unload restores full queue capacity");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            Terraria.Main.netMode = oldMode;
        }
    }

    private static void DelayedActionsKeepOriginalOwner()
    {
        var oldOwner = Terraria.Main.player[0];
        var oldTarget = Terraria.Main.npc[0];
        var oldBuffer = NetMessage.buffer[0];
        int oldMode = Terraria.Main.netMode;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server;
            // Reset a socket-free RemoteClient using the actual installed tML method.
            NetMessage.buffer[0] = new MessageBuffer();
            foreach (string state in new[] { "same", "inactive", "reset", "world_unload", "mod_unload" })
            {
                RuntimeDelayedActionScheduler.Clear();
                string label = "delayed owner " + state;
                try
                {
                    var owner = new Player { whoAmI = 0, active = true };
                    owner.Center = Vector2.Zero;
                    Terraria.Main.player[0] = owner;
                    var target = new NPC { whoAmI = 0, active = true, knockBackResist = 1f };
                    target.Center = new Vector2(32f, 0f);
                    Terraria.Main.npc[0] = target;
                    var action = new RuntimeEventActionSpec {
                        Id = "delayed_owner_probe", Event = "on_hit", DelayTicks = 2,
                        Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                        Mode = "target_to_owner", Strength = 2f, RadiusTiles = 10f,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    Equal(true, ScheduleTestItemAction(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action,
                        owner, Vector2.Zero, Vector2.UnitX, target, 0, 0, ref budget), label + " queued");
                    Equal(8, budget, label + " non-spawn action preserves budget");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(Vector2.Zero, target.velocity, label + " not before authored tick");
                    if (state == "inactive") owner.active = false;
                    if (state == "reset")
                    {
                        var client = new RemoteClient { Id = 0, IsActive = true, State = 10 };
                        client.Reset();
                        Equal(false, ReferenceEquals(owner, Terraria.Main.player[0]), "actual RemoteClient.Reset replaces Player");
                        Equal(false, client.IsActive, "actual client reset completed");
                        // Model the next connection occupying exactly the vacated slot.
                        var newcomer = Terraria.Main.player[0];
                        newcomer.active = true;
                        newcomer.whoAmI = 0;
                        newcomer.Center = new Vector2(96f, 0f);
                    }
                    if (state == "world_unload") new RuntimeDelayedActionSystem().OnWorldUnload();
                    if (state == "mod_unload") new RuntimeDelayedActionSystem().Unload();
                    RuntimeDelayedActionScheduler.Update();
                    Vector2 expected = state == "same" ? new Vector2(-2f, 0f) : Vector2.Zero;
                    Equal(expected, target.velocity, label + " effect belongs only to original owner");
                    Equal(Vector2.Zero, owner.velocity, label + " no player impulse in NPC mode");
                    // Reviving the original owner must not re-execute a retired entry.
                    owner.active = true;
                    Terraria.Main.player[0] = owner;
                    RuntimeDelayedActionScheduler.Update();
                    Equal(expected, target.velocity, label + " executes once or is permanently retired");
                }
                catch (Exception error) { failures.Add(label + ": " + error.Message); }
            }
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            NetMessage.buffer[0] = oldBuffer;
            Terraria.Main.netMode = oldMode;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void PullModesPreserveSubjectAndAuthority()
    {
        NPC[] previous = (NPC[])Terraria.Main.npc.Clone();
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        var failures = new List<string>();
        try
        {
            for (int i = 0; i < Terraria.Main.npc.Length; i++)
                Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            var target = new NPC { whoAmI = 0, type = NPCID.BlueSlime, active = true, life = 100, lifeMax = 100,
                width = 16, height = 16, knockBackResist = 1f, friendly = false, dontTakeDamage = false };
            var nearby = new NPC { whoAmI = 1, type = NPCID.BlueSlime, active = true, life = 100, lifeMax = 100,
                width = 16, height = 16, knockBackResist = 1f, friendly = false, dontTakeDamage = false };
            target.Center = new Vector2(32f, 0f);
            nearby.Center = new Vector2(96f, 0f);
            Terraria.Main.npc[0] = target;
            Terraria.Main.npc[1] = nearby;
            Equal(true, nearby.CanBeChasedBy(), "real NPC is eligible for area-pull control");
            foreach (string mode in new[] { "owner_to_target", "target_to_owner", "target_to_entity" })
            foreach (int netMode in new[] { NetmodeID.SinglePlayer, NetmodeID.Server, NetmodeID.MultiplayerClient })
            foreach (bool local in new[] { true, false })
            foreach (bool ownerActive in new[] { true, false })
            foreach (string targetState in new[] { "active", "inactive", "absent" })
            {
                string label = $"{mode}, netMode={netMode}, local={local}, ownerActive={ownerActive}, target={targetState}";
                try
                {
                    Terraria.Main.netMode = netMode;
                    Terraria.Main.myPlayer = local ? 0 : 1;
                    var owner = new Player { whoAmI = 0, active = ownerActive, velocity = Vector2.Zero };
                    owner.Center = Vector2.Zero;
                    target.active = targetState != "inactive";
                    target.velocity = nearby.velocity = Vector2.Zero;
                    NPC? direct = targetState == "absent" ? null : target;
                    var action = new RuntimeEventActionSpec {
                        Id = "pull_probe", Event = "periodic", PeriodTicks = 6,
                        Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                        Mode = mode, Strength = 2f, RadiusTiles = 10f,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    RuntimeProgramExecutor.ExecuteAction(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action, owner,
                        owner.GetSource_Misc("engine_pull_check"), new Vector2(64f, 0f), Vector2.UnitX,
                        direct, 0, 0, ref budget);
                    bool ownerAuthority = ownerActive && (netMode == NetmodeID.SinglePlayer || netMode == NetmodeID.MultiplayerClient && local);
                    bool npcAuthority = netMode != NetmodeID.MultiplayerClient;
                    if (mode == "owner_to_target")
                    {
                        Equal(ownerAuthority && targetState == "active" ? new Vector2(2f, 0f) : Vector2.Zero,
                            owner.velocity, label + " owner impulse");
                        Equal(Vector2.Zero, target.velocity, label + " must never move target");
                        Equal(Vector2.Zero, nearby.velocity, label + " must never fall through to area pull");
                    }
                    else
                    {
                        Equal(Vector2.Zero, owner.velocity, label + " NPC mode must never move owner");
                        Vector2 expectedTarget = !npcAuthority || !target.active ? Vector2.Zero
                            : mode == "target_to_owner" ? new Vector2(-2f, 0f) : new Vector2(2f, 0f);
                        Equal(expectedTarget, target.velocity, label + " NPC mode direct/area target");
                        Equal(npcAuthority && targetState != "active" ? new Vector2(-2f, 0f) : Vector2.Zero,
                            nearby.velocity, label + " NPC mode area control");
                    }
                    Equal(8, budget, label + " does not consume spawn budget");
                }
                catch (Exception error) { failures.Add(error.Message); }
            }
        }
        finally
        {
            Array.Copy(previous, Terraria.Main.npc, previous.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
