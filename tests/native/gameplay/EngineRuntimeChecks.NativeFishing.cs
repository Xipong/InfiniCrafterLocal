using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData NativeFishingFixture(bool alternate = false)
    {
        var data = GeneratedItemData.Placeholder();
        data.Gameplay.Damage = 0;
        data.Gameplay.UseStyleName = "swing";
        data.Gameplay.UseStyle = ItemUseStyleID.Swing;
        data.Gameplay.ManaCost = 7;
        data.Gameplay.UseTime = data.Gameplay.UseAnimation = 8;
        data.RuntimeProgram.ItemUse.Configured = true;
        data.RuntimeProgram.ItemUse.UseStyle = "swing";
        var fishing = new RuntimeBindingSpec {
            Id = "cast", Input = alternate ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse,
            Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.NativeFishing, TargetId = data.RuntimeProgram.ItemEntityId,
                Fishing = new RuntimeFishingSpec { Power = 25, CastSpeedPxPerTick = 9f } } } };
        var ordinary = new RuntimeBindingSpec {
            Id = "ordinary", Input = alternate ? RuntimeInputKind.PrimaryUse : RuntimeInputKind.AlternateUse,
            Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.UseItemBody, TargetId = data.RuntimeProgram.ItemEntityId } } };
        data.RuntimeProgram.Bindings = new[] { fishing, ordinary };
        return data;
    }

    private static void NativeFishingWireAdmission()
    {
        var source = NativeFishingFixture();
        var copy = GeneratedItemData.FromJson(source.ToNetworkJson()) ?? throw new InvalidOperationException("native fishing wire rejected");
        Equal(25, copy.RuntimeProgram.Bindings[0].UsePolicy.Action.Fishing!.Power, "fishing power roundtrip");
        Equal(9f, copy.RuntimeProgram.Bindings[0].UsePolicy.Action.Fishing!.CastSpeedPxPerTick, "cast speed roundtrip");
        var loaded = MobilityConsumptionHost(copy);
        Equal(25, loaded.Item.fishingPole, "network definition hydration projects native pole before use");
        Equal(ProjectileID.BobberWooden, loaded.Item.shoot, "network definition hydration projects native bobber before use");
        var ammo = NativeFishingFixture();
        ammo.Gameplay.AmmoCategory = "arrow";
        bool ammoRefused = false;
        try { typeof(GeneratedItemData).GetMethod("ValidateBindingCapabilityProjection", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(ammo, null); }
        catch (TargetInvocationException error) when (error.InnerException is InvalidDataException) { ammoRefused = true; }
        Equal(true, ammoRefused, "native rod cannot simultaneously be an ammo projectile stack");
        var action = NativeFishingFixture().RuntimeProgram.Bindings[0].UsePolicy;
        action.NormalizeAndValidate(RuntimeInputKind.PrimaryUse);
        action.NormalizeAndValidate(RuntimeInputKind.AlternateUse);
        Equal(true, RuntimeBindingAction.IsAllowed(RuntimeInputKind.AlternateUse, RuntimeBindingAction.NativeFishing), "alternate fishing has explicit native selector transport");
        Equal(false, RuntimeBindingAction.IsAllowed(RuntimeInputKind.Hold, RuntimeBindingAction.NativeFishing), "no implicit held fishing action");
        foreach (string invalid in new[] { "missing", "zero", "infinity", "stack", "contact", "wrong_action" })
        {
            var bad = NativeFishingFixture().RuntimeProgram.Bindings[0].UsePolicy;
            switch (invalid) {
                case "missing": bad.Action.Fishing = null; break;
                case "zero": bad.Action.Fishing!.Power = 0; break;
                case "infinity": bad.Action.Fishing!.CastSpeedPxPerTick = float.PositiveInfinity; break;
                case "stack": bad.StackCost = 1; break;
                case "contact": bad.ContactDamage = true; break;
                case "wrong_action": bad.Action.Kind = RuntimeBindingAction.UseItemBody; break;
            }
            bool refused = false;
            try { bad.NormalizeAndValidate(RuntimeInputKind.PrimaryUse); }
            catch (InvalidDataException) { refused = true; }
            Equal(true, refused, invalid + " fishing wire refuses rather than defaults");
        }
    }

    private static void NativeFishingProjectionAndReelCosts()
    {
        using var scope = new MobilityConsumptionNativeScope();
        const bool alternate = false;
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            player.manaCost = 1f; player.manaFlower = false;
            var host = MobilityConsumptionHost(NativeFishingFixture(alternate));
            player.inventory[0] = host.Item;
            Equal(alternate ? 0 : 25, host.Item.fishingPole, "fresh primary projection before first use");
            if (!alternate) Equal(ProjectileID.BobberWooden, host.Item.shoot, "fresh primary native bobber");
            player.altFunctionUse = alternate ? 2 : 0;
            Equal(true, host.CanUseItem(player), "selected cast admits");
            Equal(25, host.Item.fishingPole, "selected fishing power");
            Equal(ProjectileID.BobberWooden, host.Item.shoot, "declared native bobber");
            Equal(9f, host.Item.shootSpeed, "declared native cast speed");
            Equal(AmmoID.None, host.Item.useAmmo, "bait is not weapon ammo");
            Equal(true, host.Item.noMelee, "no contact damage");
            Equal(false, host.ConsumeItem(player), "rod stack never consumed");
            Equal(7, host.Item.mana, "cast cost");
            Equal(true, player.CheckMana(host.Item, -1, true, true), "native cast payment");
            Equal(13, player.statMana, "one native debit");
            player.statMana = 0;
            Equal(false, player.CheckMana(host.Item, -1, false, true), "low mana refuses first cast");
            // A different native rod's owned bobber still belongs to native reel admission.
            var bobber = Terraria.Main.projectile[0];
            bobber.SetDefaults(ProjectileID.BobberGolden); bobber.active = true; bobber.owner = player.whoAmI;
            Equal(true, host.CanUseItem(player), "reel admission at zero mana");
            Equal(0, host.Item.mana, "existing owner bobber waives only recast charge");
            Equal(true, player.CheckMana(host.Item, -1, true, true), "native zero-cost reel payment");
            Equal(0, player.statMana, "reel no debit");
            bool canCast = (bool)typeof(Player).GetMethod("ItemCheck_CheckFishingBobbers", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(player, new object[] { true })!;
            Equal(false, canCast, "native existing bobber prevents another cast");
            Equal(1f, bobber.ai[0], "native owner initiates reel");
            player.altFunctionUse = alternate ? 0 : 2;
            Equal(true, host.CanUseItem(player), "ordinary input projection");
            Equal(0, host.Item.fishingPole, "ordinary input clears fishing identity");
            Equal(ProjectileID.None, host.Item.shoot, "ordinary input clears native bobber");
            Equal(7, host.Item.mana, "ordinary input restores own cost");
            bobber.active = false;
            player.altFunctionUse = alternate ? 2 : 0;
            Equal(true, host.CanUseItem(player), "next cast projection");
            Equal(7, host.Item.mana, "no lingering free cast after reel");
            bobber.active = true; bobber.owner = player.whoAmI + 1;
            Equal(true, host.CanUseItem(player), "other player's bobber is unrelated");
            Equal(7, host.Item.mana, "foreign bobber never waives cast cost");
            host.Data.Gameplay.UseConditionMode = "mana_above";
            host.Data.Gameplay.UseConditionMinMana = 10;
            bobber.owner = player.whoAmI;
            Equal(false, host.CanUseItem(player), "explicit authored condition still gates reel; free cost is not condition bypass");
            Equal(1f, bobber.ai[0], "admission does not mutate bobber state");
            bobber.active = false;
        });
    }

    private static void NativeFishingAndWeaponAmmoSwitchIndependently()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var data = WeaponAmmoFixture("arrow", "native_shot");
            data.RuntimeProgram.Bindings[0].Input = RuntimeInputKind.AlternateUse;
            var fish = NativeFishingFixture().RuntimeProgram.Bindings[0];
            fish.Role = RuntimeEntityRole.Secondary;
            data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Concat(new[] { fish }).ToArray();
            var host = WeaponAmmoHost(data);
            player.inventory[0] = host.Item;
            player.inventory[54] = new Item(ItemID.WoodenArrow) { stack = 10 };
            player.altFunctionUse = 2;
            Equal(true, host.CanUseItem(player), "ordinary bow admission");
            Equal(AmmoID.Arrow, host.Item.useAmmo, "ordinary bow retains ammo consumer");
            player.altFunctionUse = 0;
            Equal(true, host.CanUseItem(player), "primary native fishing admission");
            Equal(AmmoID.None, host.Item.useAmmo, "native fishing does not spend weapon ammo");
            Equal(ProjectileID.BobberWooden, host.Item.shoot, "native fishing identity selected");
            player.altFunctionUse = 2;
            Equal(true, host.CanUseItem(player), "ordinary bow admission restored");
            Equal(AmmoID.Arrow, host.Item.useAmmo, "ordinary ammo projection restored");
            Equal(0, host.Item.fishingPole, "ordinary bow has no fishing pole semantics");
            Equal(10, player.inventory[54].stack, "projection never consumes ammunition");
        });
    }
}
