using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem NativeUtilityItem(string fields)
    {
        var data = GeneratedItemData.Placeholder();
        data.SourceMode = "test_fixture";
        data.Visual.EquipOverlayPath = "native_utility_overlay.png";
        data.Visual.EquipOverlayStatus = "generated";
        data.RuntimeProgram.Bindings = new[] {
            new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                } },
        };
        var node = System.Text.Json.Nodes.JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(data,
            new System.Text.Json.JsonSerializerOptions { PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase }))!;
        node["accessory"] = System.Text.Json.Nodes.JsonNode.Parse("{\"enabled\":true," + fields + "}");
        data = GeneratedItemData.FromJson(node.ToJsonString()) ?? throw new InvalidOperationException("utility fixture rejected");
        var generated = new GeneratedItem();
        var item = new Item();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
        data.ApplyToItem(item);
        // Real network DTO round trip before the hook, no game/network transport.
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated,
            GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new InvalidOperationException("utility network fixture rejected"));
        return generated;
    }

    // The real native dispatch needs a scoped ModPlayer hook roster in this loader-free harness.
    private sealed class NativeUtilityPlayerHooks : IDisposable
    {
        private readonly System.Collections.Generic.List<Action> _restores = new();
        public NativeUtilityPlayerHooks(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer owner)
        {
            try {
                foreach (string name in new[] { "HookResetEffects", "HookPostUpdateEquips" }) {
                    object hook = typeof(PlayerLoader).GetField(name, BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
                    var flags = BindingFlags.Instance | BindingFlags.NonPublic;
                    FieldInfo indices = hook.GetType().GetField("indices", flags)!;
                    FieldInfo defaults = hook.GetType().GetField("defaultInstances", flags)!;
                    object oldIndices = indices.GetValue(hook)!, oldDefaults = defaults.GetValue(hook)!;
                    _restores.Add(() => { indices.SetValue(hook, oldIndices); defaults.SetValue(hook, oldDefaults); });
                    hook.GetType().GetMethod("Update")!.Invoke(hook, new object[] { new ModPlayer[] { owner } });
                }
            }
            catch { Dispose(); throw; }
        }
        public void Dispose() { foreach (Action restore in _restores) restore(); _restores.Clear(); }
    }

    private static GeneratedItem NativeDispatchedUtilityItem(string fields)
    {
        var generated = NativeUtilityItem(fields);
        typeof(Item).GetProperty("ModItem")!.SetValue(generated.Item, generated);
        // A neutral native shell, not a shoe identity or inferred generated preset.
        generated.Item.type = 1;
        generated.Item.stack = 1;
        return generated;
    }

    private static void NativeEquipmentRocketSlotOrder()
    {
        WithPlayer((player, owner) => {
            using var hooks = new NativeUtilityPlayerHooks(owner);
            bool allModesSurvived = true;
            foreach (bool mixed in new[] { false, true })
            foreach (int vanillaType in new[] { Terraria.ID.ItemID.RocketBoots, Terraria.ID.ItemID.FrostsparkBoots })
            foreach (bool generatedFirst in new[] { false, true }) {
                var generated = NativeDispatchedUtilityItem(mixed
                    ? "\"rocketBoots\":5,\"accRunSpeed\":20,\"iceSkate\":true,\"wireVision\":true,\"noKnockback\":true,\"fireWalk\":true,\"defense\":2,\"movementSpeed\":0.08"
                    : "\"rocketBoots\":5");
                player.ResetEffects();
                var vanilla = new Item { type = vanillaType, stack = 1 };
                Equal(true, ItemLoader.CanAccessoryBeEquippedWith(player, generated.Item, vanilla), "native pair coexistence");
                Equal(true, ItemLoader.CanAccessoryBeEquippedWith(player, vanilla, generated.Item), "native reversed coexistence");
                player.rocketTime = 2; player.rocketDelay = 4; player.rocketDelay2 = 9;
                player.canRocket = false; player.rocketRelease = false;
                if (generatedFirst) { player.ApplyEquipFunctional(generated.Item, false); player.ApplyEquipFunctional(vanilla, false); }
                else { player.ApplyEquipFunctional(vanilla, false); player.ApplyEquipFunctional(generated.Item, false); }
                // Same dispatcher as Player.Update, after all equips and before movement.
                PlayerLoader.PostUpdateEquips(player);
                Console.WriteLine($"ROCKET_ORDER mixed={mixed} vanilla={vanillaType} generatedFirst={generatedFirst} mode={player.rocketBoots}");
                allModesSurvived &= player.rocketBoots == 5;
                Equal(2, player.rocketTime, "post-equip does not refill spent flight");
                Equal(4, player.rocketDelay, "post-equip does not bypass thrust cooldown");
                Equal(9, player.rocketDelay2, "post-equip does not reset presentation delay");
                Equal(false, player.canRocket, "native thrust gate retained");
                Equal(false, player.rocketRelease, "native release gate retained");
                Equal(vanillaType == Terraria.ID.ItemID.RocketBoots ? 1 : 3, player.vanityRocketBoots, "native vanity choice retained");
                player.ResetEffects();
                player.ApplyEquipFunctional(vanilla, false);
                PlayerLoader.PostUpdateEquips(player);
                Equal(vanillaType == Terraria.ID.ItemID.RocketBoots ? 1 : 3, player.rocketBoots, "generated mode expires on unequip via native reset dispatcher");
            }
            Equal(true, allModesSurvived, "generated mode 5 survives later vanilla Rocket Boots and Frostspark in both slot orders");
        });
    }

    private static void NativeEquipmentSprintSlotOrder()
    {
        WithPlayer((player, owner) => {
            using var hooks = new NativeUtilityPlayerHooks(owner);
            bool allFloorsSurvived = true;
            // Pure field reproduction, then the exact reviewer's mixed native-hook fixture.
            foreach (bool mixed in new[] { false, true })
            foreach (bool generatedFirst in new[] { false, true }) {
                var generated = NativeDispatchedUtilityItem(mixed
                    ? "\"rocketBoots\":5,\"accRunSpeed\":20,\"iceSkate\":true,\"wireVision\":true,\"noKnockback\":true,\"fireWalk\":true,\"defense\":2,\"movementSpeed\":0.08"
                    : "\"accRunSpeed\":20");
                var vanilla = new Item { type = Terraria.ID.ItemID.FrostsparkBoots, stack = 1 };
                Equal(true, ItemLoader.CanAccessoryBeEquippedWith(player, generated.Item, vanilla), "native sprint pair coexistence");
                Equal(true, ItemLoader.CanAccessoryBeEquippedWith(player, vanilla, generated.Item), "native sprint reversed coexistence");
                for (int tick = 0; tick < 2; tick++) {
                    player.ResetEffects();
                    player.accRunSpeed = player.maxRunSpeed = 3f;
                    player.statDefense = new Player.DefenseStat(); player.statDefense += 100;
                    player.rocketTime = 2; player.rocketDelay = 4;
                    player.GrantArmorBenefits(generated.Item);
                    if (generatedFirst) { player.ApplyEquipFunctional(generated.Item, true); player.ApplyEquipFunctional(vanilla, false); }
                    else { player.ApplyEquipFunctional(vanilla, false); player.ApplyEquipFunctional(generated.Item, true); }
                    PlayerLoader.PostUpdateEquips(player);
                    Console.WriteLine($"SPRINT_ORDER mixed={mixed} generatedFirst={generatedFirst} tick={tick} speed={player.accRunSpeed}");
                    allFloorsSurvived &= player.accRunSpeed == 20f;
                    Equal(3f, player.maxRunSpeed, "no duplicate flat run-speed grant");
                    Equal(mixed ? 102 : 100, (int)player.statDefense, "native Item defense once per tick");
                    float expectedMoveSpeed = 1f + 0.08f;
                    if (mixed) expectedMoveSpeed += 0.08f;
                    Equal(expectedMoveSpeed, player.moveSpeed, "vanilla and generated moveSpeed once per tick");
                    if (!mixed) Equal(3, player.rocketBoots, "independent native rocket mode preserved");
                    // Exact mixed generated-mode max is asserted separately by the rocket regression.
                    Equal(3, player.vanityRocketBoots, "native vanity not inferred from generated mode");
                    Equal(true, player.iceSkate, "native ice-skate retained");
                    Equal(mixed, player.InfoAccMechShowWires, "generated wire flag retained");
                    Equal(mixed, player.noKnockback, "generated knockback flag retained");
                    Equal(mixed, player.fireWalk, "generated hot-block flag retained");
                    Equal(false, player.lavaImmune, "no inferred lava immunity");
                    Equal(2, player.rocketTime, "no refill in post-equip");
                    Equal(4, player.rocketDelay, "no cooldown reset in post-equip");
                    player.controlRight = true; player.controlLeft = false; player.velocity.X = 7f;
                    player.runAcceleration = 0.08f; player.runSlowdown = 0.2f; player.dashDelay = 0;
                    player.HorizontalMovement();
                    // Keep checking all orders on RED rather than stop at the first failed native sprint.
                    allFloorsSurvived &= player.velocity.X > 7f;
                }
                player.ResetEffects(); player.accRunSpeed = player.maxRunSpeed = 3f;
                player.ApplyEquipFunctional(vanilla, false);
                PlayerLoader.PostUpdateEquips(player);
                Equal(6.75f, player.accRunSpeed, "generated floor expires on unequip");
                Equal(3, player.rocketBoots, "generated rocket expires on unequip");
                Equal(false, player.InfoAccMechShowWires, "generated flags expire on unequip");
                Equal(false, player.noKnockback, "knockback immunity expires on unequip");
                Equal(false, player.fireWalk, "hot-block immunity expires on unequip");
            }
            Equal(true, allFloorsSurvived, "generated sprint floor 20 survives Frostspark in both orders before actual HorizontalMovement");
        });
    }

    private static void NativeEquipmentUtilityFlags()
    {
        WithPlayer((player, _) => {
            (string Field, Func<Player, bool> Read)[] cases = {
                ("iceSkate", p => p.iceSkate), ("noKnockback", p => p.noKnockback), ("fireWalk", p => p.fireWalk),
            };
            foreach (var test in cases) {
                var generated = NativeUtilityItem("\"" + test.Field + "\":true");
                Equal(true, generated.Data.Accessory.HasAnyEffect, test.Field + " alone is an effect");
                player.ResetEffects();
                generated.UpdateAccessory(player, true);
                Equal(true, test.Read(player), test.Field + " reaches exact native flag");
                Equal(false, player.lavaImmune, "no hot-block/lava conflation");
                var hurt = new Player.HurtModifiers { HitDirection = 1 };
                var hurtInfo = hurt.ToHurtInfo(20, 0, 0.5f, 6f, player.noKnockback);
                Equal(test.Field == "noKnockback" ? 0f : 6f, hurtInfo.Knockback, "actual native hurt knockback consumer");
                Equal(test.Field != "fireWalk", Collision.CanTileHurt(Terraria.ID.TileID.Meteorite, 0, 0, player), "actual native hot-tile consumer");
                Equal(true, Collision.CanTileHurt(Terraria.ID.TileID.Spikes, 0, 0, player), "fireWalk is not all-tile immunity");
                player.ResetEffects();
                Equal(false, test.Read(player), test.Field + " expires on unequip");
                NativeUtilityItem("\"" + test.Field + "\":false,\"defense\":1").UpdateAccessory(player, false);
                Equal(false, test.Read(player), test.Field + " false is no grant");
            }
        });
    }

    private static void NativeEquipmentRocketFlight()
    {
        WithPlayer((player, owner) => {
            using var hooks = new NativeUtilityPlayerHooks(owner);
            foreach (int mode in new[] { 1, 2, 3, 4, 5 }) {
                var generated = NativeUtilityItem("\"rocketBoots\":" + mode);
                Equal(true, generated.Data.Accessory.HasAnyEffect, "rocket mode alone is an effect");
                player.ResetEffects();
                player.rocketTime = 2;
                player.rocketDelay = 4;
                generated.UpdateAccessory(player, false);
                generated.UpdateAccessory(player, false);
                PlayerLoader.PostUpdateEquips(player);
                Equal(mode, player.rocketBoots, "native flight/delay mode");
                Equal(2, player.rocketTime, "equip does not refresh spent flight budget");
                Equal(4, player.rocketDelay, "equip does not bypass native thrust cooldown");
                Equal(7, player.rocketTimeMax, "native seven charge budget remains unchanged");
                Equal(0, player.vanityRocketBoots, "no implicit presentation choice");
                player.RefreshMovementAbilities(doubleJumps: false);
                Equal(7, player.rocketTime, "actual native movement refresh owns refill");
                Equal(0, player.rocketDelay, "native refill resets delay");
                player.ResetEffects();
                PlayerLoader.PostUpdateEquips(player);
                Equal(0, player.rocketBoots, "unequipped flag expires at native reset and post-equip");
            }
            player.rocketBoots = 4;
            NativeUtilityItem("\"rocketBoots\":2").UpdateAccessory(player, false);
            PlayerLoader.PostUpdateEquips(player);
            Equal(4, player.rocketBoots, "lower mode does not erase an existing native mode");
            foreach (string value in new[] { "-1", "6", "1.5", "true", "null" }) {
                bool refused = false;
                try { NativeUtilityItem("\"defense\":1,\"rocketBoots\":" + value); }
                catch (InvalidOperationException) { refused = true; }
                Equal(true, refused, "present invalid rocket mode rejected before narrowing: " + value);
            }
        });
    }

    private static void NativeEquipmentSprintSpeed()
    {
        WithPlayer((player, modPlayer) => {
            using var hooks = new NativeUtilityPlayerHooks(modPlayer);
            foreach (float speed in new[] { 0f, 3f, 6.75f, 20f }) {
                player.ResetEffects();
                player.accRunSpeed = 3f;
                player.maxRunSpeed = 3f;
                player.moveSpeed = 1f;
                var generated = NativeUtilityItem("\"defense\":1,\"accRunSpeed\":" + speed.ToString(System.Globalization.CultureInfo.InvariantCulture));
                generated.UpdateAccessory(player, false);
                PlayerLoader.PostUpdateEquips(player);
                Equal(Math.Max(3f, speed), player.accRunSpeed, "explicit native sprint speed floor");
                Equal(3f, player.maxRunSpeed, "not a duplicate run-speed bonus");
                Equal(1f, player.moveSpeed, "does not select movement-speed percent");
                player.controlRight = true;
                player.controlLeft = false;
                player.velocity.X = 4f;
                player.runAcceleration = 0.08f;
                player.runSlowdown = 0.2f;
                player.dashDelay = 0;
                // Actual native movement consumer, no world/tile simulation.
                player.HorizontalMovement();
                Equal(speed > 4f, player.velocity.X > 4f, "native sprint branch consumes authored speed");
            }
            player.ResetEffects();
            player.accRunSpeed = 15f;
            NativeUtilityItem("\"accRunSpeed\":6.75").UpdateAccessory(player, true);
            PlayerLoader.PostUpdateEquips(player);
            Equal(15f, player.accRunSpeed, "lower equipped floor never erases another accessory");
            foreach (string value in new[] { "-1", "20.00000000000001", "true", "null" }) {
                bool refused = false;
                try { NativeUtilityItem("\"defense\":1,\"accRunSpeed\":" + value); }
                catch (InvalidOperationException) { refused = true; }
                Equal(true, refused, "present invalid speed refused before float32 narrowing: " + value);
            }
            var nativeData = NativeUtilityItem("\"accRunSpeed\":6.75").Data;
            Equal(true, nativeData.Accessory.HasAnyEffect, "speed-only effect remains active");
        });
    }

    private static void NativeEquipmentWireVision()
    {
        using var actorState = new NativeActorState();
        WithPlayer((player, _) => {
            var generated = NativeUtilityItem("\"wireVision\":true");
            Equal(true, generated.Data.Accessory.HasAnyEffect, "flag-only item is an effect");
            foreach (bool hidden in new[] { false, true }) {
                player.ResetEffects();
                Equal(false, player.InfoAccMechShowWires, "native tick resets wire vision");
                bool rulerBefore = player.rulerLine;
                generated.UpdateAccessory(player, hidden);
                Equal(true, player.InfoAccMechShowWires, "exact native wire visibility flag, including hidden accessory");
                Equal(rulerBefore, player.rulerLine, "wire vision does not synthesize rulers");

                Terraria.Main.myPlayer = 0;
                Terraria.Main.player[0] = player;
                Terraria.Main.getGoodWorld = false;
                player.selectedItem = 0;
                player.inventory[0].mech = false;
                player.builderAccStatus[8] = 0;
                Equal(true, Terraria.GameContent.UI.WiresUI.Settings.DrawWires, "actual native draw eligibility consumes flag");
                player.builderAccStatus[8] = 1;
                Equal(false, Terraria.GameContent.UI.WiresUI.Settings.DrawWires, "native hide-all toggle retained");
                player.builderAccStatus[8] = 0;

            }
            player.ResetEffects();
            var inactive = NativeUtilityItem("\"wireVision\":true");
            inactive.Data.Accessory.Enabled = false;
            inactive.UpdateAccessory(player, false);
            Equal(false, player.InfoAccMechShowWires, "disabled accessory cannot grant effects");
            NativeUtilityItem("\"defense\":1").UpdateAccessory(player, false);
            Equal(false, player.InfoAccMechShowWires, "old absent field remains inert");
            NativeUtilityItem("\"wireVision\":false,\"defense\":1").UpdateAccessory(player, false);
            Equal(false, player.InfoAccMechShowWires, "false/unequip does not enable wire vision");
        });
    }
}
