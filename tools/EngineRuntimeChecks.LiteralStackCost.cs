using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable observer: calls the real inherited static hook explicitly,
    // just as tML registration would. Never writes ForceConsumption per definition.
    private sealed class LiteralCostStaticScope : IDisposable
    {
        private readonly bool? proxy = ItemID.Sets.ForceConsumption[ItemID.CopperShortsword];
        private readonly bool? vanilla = ItemID.Sets.ForceConsumption[ItemID.WoodenSword];
        private readonly bool blockMouse = Terraria.Main.blockMouse;
        internal LiteralCostStaticScope()
        {
            // A loader-free proxy fixture borrows one ordinary native type ID.
            // The real control must not inherit either a preexisting fixture or a coin rule.
            ItemID.Sets.ForceConsumption[ItemID.CopperShortsword] = null;
            ItemID.Sets.ForceConsumption[ItemID.WoodenSword] = null;
        }
        public void Dispose()
        {
            ItemID.Sets.ForceConsumption[ItemID.CopperShortsword] = proxy;
            ItemID.Sets.ForceConsumption[ItemID.WoodenSword] = vanilla;
            Terraria.Main.blockMouse = blockMouse;
        }
    }

    private static readonly string[] LiteralCostSavingKinds = {
        "none", "ammoCost80", "ammoCost75", "chloroAmmoCost80", "huntressAmmoCost90", "ThrownCost50", "ThrownCost33",
    };

    private static int LiteralCostSavedSeed(string saving)
    {
        int bound = saving == "huntressAmmoCost90" ? 10 : saving == "ammoCost75" ? 4
            : saving.StartsWith("Thrown", StringComparison.Ordinal) ? 100 : 5;
        // Select a real native RNG witness; do not implement the RNG or lottery.
        for (int seed = 0; seed < 10000; seed++)
            if (new UnifiedRandom(seed).Next(bound) == 0) return seed;
        throw new InvalidOperationException("No native saving seed found for " + saving);
    }

    private static void LiteralCostSaving(Player player, string saving)
    {
        player.ammoCost80 = saving == "ammoCost80";
        player.ammoCost75 = saving == "ammoCost75";
        player.chloroAmmoCost80 = saving == "chloroAmmoCost80";
        player.huntressAmmoCost90 = saving == "huntressAmmoCost90";
        player.ThrownCost50 = saving == "ThrownCost50";
        player.ThrownCost33 = saving == "ThrownCost33";
        Terraria.Main.rand = new UnifiedRandom(LiteralCostSavedSeed(saving));
    }

    private static GeneratedItemData LiteralCostData(string saving, int primaryCost, int alternateCost, bool ammo = false)
    {
        var data = MobilityConsumptionFixture("", primaryCost);
        data.Gameplay.DamageClass = saving.StartsWith("Thrown", StringComparison.Ordinal) ? "throwing" : "ranged";
        data.Gameplay.HealLife = 7;
        data.Gameplay.Potion = true;
        data.Gameplay.MaxStack = 9999;
        data.RuntimeProgram.Bindings = new[] {
            new RuntimeBindingSpec { Id = "literal_primary", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = primaryCost,
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } } },
            new RuntimeBindingSpec { Id = "literal_alternate", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = alternateCost,
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } } },
        };
        if (ammo)
        {
            data.Gameplay.AmmoCategory = "bullet";
            data.Gameplay.AmmoProjectileId = ProjectileID.Bullet;
            data.Gameplay.AmmoShootSpeedPxPerTick = 2.5f;
        }
        // Exercise the canonical strict decoder, not only a hand-built DTO.
        return GeneratedItemData.FromJson(data.ToNetworkJson())
            ?? throw new InvalidOperationException("Literal-cost fixture rejected by real FromJson");
    }

    private static MobilityConsumptionProbeItem LiteralCostHost(GeneratedItemData data)
    {
        var host = MobilityConsumptionHost(data);
        host.Item.stack = 3;
        host.SetStaticDefaults(); // production registration seam, unchanged for RED
        return host;
    }

    private static void NativeDirectUseStackCostIsLiteralUnderSaving()
    {
        using var native = new MobilityConsumptionNativeScope();
        using var statics = new LiteralCostStaticScope();
        var failures = new List<string>();
        foreach (string saving in LiteralCostSavingKinds)
        foreach (int cost in new[] { 0, 1 })
        foreach (int selector in new[] { 0, 2 })
        foreach (bool ammo in new[] { false, true })
        {
            string label = saving + "/primaryCost=" + cost + "/input=" + selector + "/ammo=" + ammo;
            try
            {
                WithPlayer((player, _) => {
                    PrepareMobilityConsumptionPlayer(player);
                    // Ammo keeps consumable=true even at direct stackCost=0, making
                    // the final ModItem gate observable rather than bypassing it.
                    var host = LiteralCostHost(LiteralCostData(saving, cost, 1 - cost, ammo: ammo));
                    int selectedCost = selector == 2 ? 1 - cost : cost;
                    bool gateExpected = ammo || selectedCost == 1;
                    player.inventory[0] = host.Item; player.altFunctionUse = selector;
                    Equal(true, host.CanUseItem(player), label + " real admission");
                    Equal(gateExpected, host.Item.consumable, label + " direct/independent ammo consumable lanes");
                    Equal(saving.StartsWith("Thrown", StringComparison.Ordinal), host.Item.CountsAsClass(DamageClass.Throwing), label + " exact native class");
                    LiteralCostSaving(player, saving);
                    native.RunNativeSuffix(player); // unchanged real UseItem/heal/ConsumeItem/stack-- tail
                    Equal(64, player.statLife, label + " successful real native heal");
                    Equal(1, host.UseCalls, label + " one actual use");
                    Equal(gateExpected ? 1 : 0, host.ConsumeCalls, label + " direct gate reached despite saving when consumable");
                    Equal(gateExpected ? "use,consume" : "use", string.Join(",", host.Trace), label + " actual hook order");
                    Equal(selectedCost == 1 ? 2 : 3, host.Item.stack, label + " literal native debit");
                    Equal(selector, player.altFunctionUse, label + " selected input retained");
                });
            }
            catch (Exception error) { failures.Add(label + ": " + error); }
        }
        // The defect's native control: a successful ranged heal under the saving
        // witness spends no stack if ForceConsumption remains null. No gameplay stub.
        foreach (string saving in new[] { "ammoCost80", "ammoCost75", "chloroAmmoCost80", "huntressAmmoCost90" })
        {
            try
            {
                WithPlayer((player, _) => {
                    PrepareMobilityConsumptionPlayer(player);
                    var control = new Item(); control.SetDefaults(ItemID.WoodenSword);
                    control.DamageType = DamageClass.Ranged; control.stack = 3;
                    control.consumable = true; control.healLife = 7; control.UseSound = null;
                    control.useTime = control.useAnimation = 20; control.shoot = ProjectileID.None;
                    player.inventory[0] = control;
                    LiteralCostSaving(player, saving);
                    native.RunNativeSuffix(player);
                    Equal(64, player.statLife, saving + " vanilla control actually heals");
                    Equal(3, control.stack, saving + " unchanged vanilla direct-use saving remains");
                    Equal(true, ItemID.Sets.ForceConsumption[ItemID.WoodenSword] is null, "no foreign type mutation");
                });
            }
            catch (Exception error) { failures.Add("vanilla/" + saving + ": " + error); }
        }
        // Two definitions coexist on ONE proxy type. Projection/activation must
        // never toggle a type-wide set according to one instance's selected cost.
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var reusable = LiteralCostHost(LiteralCostData("ammoCost80", 0, 1, ammo: true));
            var spent = LiteralCostHost(LiteralCostData("ammoCost80", 1, 0));
            Equal(reusable.Item.type, spent.Item.type, "two definitions share exact proxy type");
            foreach ((MobilityConsumptionProbeItem host, int expected) in new[] { (reusable, 3), (spent, 2) })
            {
                PrepareMobilityConsumptionPlayer(player);
                player.inventory[0] = host.Item;
                Equal(true, host.CanUseItem(player), "coexisting definition admitted");
                Equal(true, ItemID.Sets.ForceConsumption[host.Item.type] == true, "projection cannot toggle shared type set");
                LiteralCostSaving(player, "ammoCost80"); native.RunNativeSuffix(player);
                Equal(expected, host.Item.stack, "coexisting definition pays only its own literal cost");
            }
            Equal(3, reusable.Item.stack, "consuming sibling cannot charge reusable instance");
        });
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private sealed class LiteralCostQuickRecipeBoundary : Exception { }

    private static void NativeQuickHealStackCostUsesPrimaryUnderSaving()
    {
        using var native = new MobilityConsumptionNativeScope();
        using var statics = new LiteralCostStaticScope();
        var bridge = new GeneratedQuickUseSystem();
        MethodInfo quick = typeof(Player).GetMethod(nameof(Player.QuickHeal), Type.EmptyTypes)!;
        int boundaries = 0;
        using var stop = new ILHook(quick, il => {
            var c = new ILCursor(il);
            if (!c.TryGotoNext(MoveType.AfterLabel, i => i.MatchCall<Recipe>(nameof(Recipe.FindRecipes))))
                throw new InvalidOperationException("Native QuickHeal post-consumption Recipe boundary missing");
            c.EmitDelegate<Action>(() => { boundaries++; throw new LiteralCostQuickRecipeBoundary(); });
        });
        try
        {
            bridge.Load();
            foreach (int primaryCost in new[] { 0, 1 })
            foreach (int selector in new[] { 0, 2 })
            WithPlayer((player, _) => {
                PrepareMobilityConsumptionPlayer(player);
                var host = LiteralCostHost(LiteralCostData("ammoCost80", primaryCost, 1 - primaryCost, ammo: true));
                player.inventory[0] = host.Item; player.altFunctionUse = selector;
                LiteralCostSaving(player, "ammoCost80");
                int before = boundaries;
                try { player.QuickHeal(); }
                catch (LiteralCostQuickRecipeBoundary) { }
                Equal(before + 1, boundaries, "real QuickHeal reached post-consumption boundary");
                Equal(64, player.statLife, "quick native healing happened once");
                Equal(1, host.UseCalls, "quick real mod-use dispatch happened once");
                Equal(1, host.ConsumeCalls, "quick real mod gate happened once");
                Equal(primaryCost == 1 ? 2 : 3, host.Item.stack, "quick always pays primary, not alternate cost");
                Equal(selector, player.altFunctionUse, "quick preserves physical input selector");
            });
        }
        finally { bridge.Unload(); }
    }

    private static void NativeLiteralStackCostKeepsMobilityAndPlacementGates()
    {
        using var native = new MobilityConsumptionNativeScope();
        using var statics = new LiteralCostStaticScope();
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player);
            var data = MobilityConsumptionFixture("recall_home", 1);
            data.Gameplay.DamageClass = "ranged";
            var host = LiteralCostHost(data); player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "pure mobility admitted");
            Equal(true, generated.TryReserveGeneratedMobilityCooldown(30), "refusal introduced AFTER admission");
            var position = player.position;
            LiteralCostSaving(player, "ammoCost80"); native.RunNativeSuffix(player);
            Equal(position, player.position, "refused real mobility does not move");
            Equal(3, host.Item.stack, "forced pre-gate cannot charge refused mobility");
            Equal("use,consume", string.Join(",", host.Trace), "refusal actually reaches final mod gate");
            Equal(1, player.ItemUsesThisAnimation, "refusal completes native timing once");
        });
        foreach (bool accepted in new[] { false, true })
        WithPersistenceTilemap((player, ledger) => {
            int x = Player.tileTargetX, y = Player.tileTargetY;
            try
            {
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
                PrepareMobilityConsumptionPlayer(player);
                player.position = new Microsoft.Xna.Framework.Vector2(640f, 640f); // target 40 stays inside the real ledger reach fence
                Player.tileTargetX = Player.tileTargetY = 40;
                Tile cell = Terraria.Main.tile[40, 40]; cell.WallType = 0;
                var data = PersistencePlacementData(); data.Gameplay.DamageClass = "ranged";
                var host = LiteralCostHost(data); player.inventory[0] = host.Item;
                Equal(true, host.CanUseItem(player), "real placement ledger captures before-state");
                // A deliberate CPU cell mutation is the existing receipt seam, NOT
                // a claim that WorldGen.PlaceWall or a world loop was executed.
                if (accepted) cell.WallType = 1;
                LiteralCostSaving(player, "ammoCost80"); native.RunNativeSuffix(player);
                Equal(accepted ? 2 : 3, host.Item.stack, "native debit requires accepted placement receipt");
                Equal("use,consume", string.Join(",", host.Trace), "placement reaches final mod gate despite saving");
                Equal(false, ItemLoader.ConsumeItem(host.Item, player), "receipt cannot be spent/replayed again");
                Equal(accepted ? 2 : 3, host.Item.stack, "gate does not duplicate native arithmetic");
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; }
        });
    }

    private static void NativePickAmmoSavingRemainsIndependentOfDirectStackCost()
    {
        using var native = new MobilityConsumptionNativeScope();
        using var statics = new LiteralCostStaticScope();
        foreach (string saving in new[] { "none", "ammoCost80", "ammoCost75", "chloroAmmoCost80", "huntressAmmoCost90", "ThrownCost50", "ThrownCost33" })
        foreach (int directCost in new[] { 0, 1 })
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var host = LiteralCostHost(LiteralCostData(saving, directCost, directCost, ammo: true));
            host.Item.stack = 9;
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "ammo direct projection admitted");
            var weapon = new Item(); weapon.SetDefaults(ItemID.WoodenSword);
            weapon.DamageType = DamageClass.Ranged; weapon.useAmmo = AmmoID.Bullet;
            weapon.shoot = ProjectileID.Bullet; weapon.shootSpeed = 8f; weapon.damage = 30;
            player.inventory[1] = weapon; player.selectedItem = 1;
            LiteralCostSaving(player, saving);
            Equal(true, player.PickAmmo(weapon, out int projectile, out float speed,
                out int damage, out float knockback, out int usedId, dontConsume: false), "actual native PickAmmo chose generated ammo");
            Equal(host.Item.type, usedId, "native ammo identity");
            Equal(ProjectileID.Bullet, projectile, "independent ammo projectile projection");
            Equal(10.5f, speed, "native ammo speed contribution");
            Equal(saving == "none" ? 8 : 9, host.Item.stack, "native ammo saving independent of direct stackCost=" + directCost + "/" + saving);
            Equal(0, host.UseCalls, "PickAmmo does not execute direct use");
            Equal(0, host.ConsumeCalls, "PickAmmo never borrows direct ConsumeItem gate");
            Equal(true, ItemID.Sets.ForceConsumption[host.Item.type] == true, "real generated static registration stays enabled");
        });
    }
}
