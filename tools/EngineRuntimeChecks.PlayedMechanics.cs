using System;
using System.IO;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private sealed class PlayedMiningEntry : Exception { }

    // Reads the retained exact Author capture, then uses an in-memory mechanics
    // envelope with the same native powers, timing and binding transactions.
    // This does not claim Visual/PNG delivery or a complete native world loop.
    private static GeneratedItemData PlayedRecallPickData()
    {
        using var capture = JsonDocument.Parse(File.ReadAllText(
            "LocalGenerator/tests/fixtures/played_a2_a3_a4_author.json"));
        var calls = capture.RootElement.GetProperty("g_fb3aca59f2dc1ac3")
            .GetProperty("runtimeProgram").GetProperty("calls");
        var data = GeneratedPrefixFixture();
        data.Id = "played-a3-recall-pick";
        foreach (var call in calls.EnumerateArray())
        {
            var p = call.GetProperty("params");
            switch (call.GetProperty("fn").GetString())
            {
                case "configure_item_stats":
                    data.Gameplay.Damage = p.GetProperty("damage").GetInt32();
                    data.Gameplay.UseTime = p.GetProperty("useTimeTicks").GetInt32();
                    data.Gameplay.UseAnimation = p.GetProperty("useAnimationTicks").GetInt32();
                    break;
                case "configure_tool":
                    data.Gameplay.PickPower = p.GetProperty("pickPower").GetInt32();
                    data.Gameplay.AxePower = p.GetProperty("axePowerTooltipPercent").GetInt32() / 5;
                    data.Gameplay.HammerPower = p.GetProperty("hammerPower").GetInt32();
                    data.Gameplay.MiningSpeedScale = p.GetProperty("miningSpeedMultiplier").GetSingle();
                    break;
                case "recall_home_on_use":
                    data.Gameplay.MobilityMode = "recall_home";
                    data.Gameplay.MobilityCooldownTicks = p.GetProperty("cooldownTicks").GetInt32();
                    break;
            }
        }
        var alt = new RuntimeBindingSpec {
            Id = "recall_with_pick", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = false, StackCost = 0,
                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.ApplyItemEffects,
                    TargetId = data.RuntimeProgram.ItemEntityId } },
        };
        data.RuntimeProgram.Bindings = new[] { data.RuntimeProgram.Bindings[0], alt };
        Equal(35, data.Gameplay.PickPower, "frozen A3 pick power");
        Equal(1800, data.Gameplay.MobilityCooldownTicks, "frozen A3 shared cooldown");
        return data;
    }

    public static void PlayedAlternateEffectsIsolateAndRestoreNativeMining()
    {
        using var mobility = new MobilityConsumptionNativeScope();
        WithGeneratedPrefixScope(() => WithPersistenceTilemap((_, __) => WithPlayer((player, ___) => {
            PrepareMobilityConsumptionPlayer(player);
            player.SpawnX = player.SpawnY = 42; // inside the retained 100x100 CPU tilemap
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            player.controlUseItem = true;
            player.position = new Vector2(640, 640);
            for (int slot = 0; slot < 50; slot++) player.inventory[slot] = new Item();
            int oldX = Player.tileTargetX, oldY = Player.tileTargetY;
            int entries = 0;
            var mining = typeof(Player).GetMethod("ItemCheck_UseMiningTools", BindingFlags.Instance | BindingFlags.NonPublic)!;
            var strike = typeof(Player).GetMethod("ItemCheck_UseMiningTools_ActuallyUseMiningTool", BindingFlags.Instance | BindingFlags.NonPublic)!;
            using var observer = new ILHook(strike, il => new ILCursor(il).EmitDelegate<Action>(() => {
                entries++;
                throw new PlayedMiningEntry();
            }));
            try
            {
                Player.tileTargetX = Player.tileTargetY = 40;
                Tile target = Terraria.Main.tile[40, 40];
                target.HasTile = true; target.TileType = TileID.Dirt;
                var data = PlayedRecallPickData();
                var host = GeneratedPrefixHost(data, ItemID.CopperPickaxe);
                player.inventory[0] = host.Item; player.selectedItem = 0;
                string definition = host.Data.ToNetworkJson();
                var canonical = host.Data;
                Equal(true, ReferenceEquals(host.Item, player.GetBestPickaxe()), "idle native inventory discovers captured pick before use");
                void Entry(bool expected, string label, int animation = 22)
                {
                    player.toolTime = 0; player.itemTime = 0; player.itemAnimation = animation;
                    int before = entries;
                    try { mining.Invoke(player, new object[] { host.Item }); }
                    catch (TargetInvocationException ex) when (ex.InnerException is PlayedMiningEntry) { }
                    Equal(before + (expected ? 1 : 0), entries, label);
                }
                void IdleInventory(bool switchItem, string label)
                {
                    // Native UpdateEquips/UpdateInventory runs before ItemCheck;
                    // HoldItem follows its animation decrement. Never project a
                    // primary use to make the inventory observer pass.
                    player.itemAnimation = player.itemTime = 0;
                    host.UpdateInventory(player);
                    host.HoldItem(player);
                    Equal(true, ReferenceEquals(host.Item, player.GetBestPickaxe()), label + " real GetBestPickaxe without primary CanUseItem");
                    if (switchItem)
                    {
                        player.inventory[1] = new Item(); player.inventory[1].SetDefaults(ItemID.Wood);
                        player.selectedItem = 1;
                        host.UpdateInventory(player);
                        Equal(true, ReferenceEquals(host.Item, player.GetBestPickaxe()), label + " remains discoverable after switch");
                        player.selectedItem = 0;
                    }
                }
                player.altFunctionUse = 0;
                Equal(true, host.CanUseItem(player), "frozen A3 primary admitted");
                Entry(true, "real native primary reaches mining entry");
                player.controlUseItem = false;
                Entry(false, "native input-disabled positive-tool control");
                player.controlUseItem = true;

                var owner = player.GetModPlayer<InfiniCraftPlayer>();
                player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "frozen A3 alternate admitted");
                Equal(0, host.Item.pick + host.Item.axe + host.Item.hammer, "alternate effect action has no native tool powers");
                Entry(false, "alternate cannot enter native mining");
                host.UpdateInventory(player); host.HoldItem(player);
                Entry(false, "inventory and held callbacks cannot restore powers during alternate window");
                host.UseItem(player);
                Equal(1f, player.teleportTime, "successful recall completed actual native Teleport");
                Equal(1800, owner.GeneratedMobilityCooldownTicks, "successful recall starts captured cooldown");
                // ApplyItemTime can dispatch UseItem inside OwnerOnlyCode before
                // mining; its generic-use tail can also dispatch afterwards. Both
                // leave the same Item fenced, including the last animated tick.
                player.position = new Vector2(640, 640);
                for (int animation = 22; animation > 0; animation--)
                {
                    // Model native UpdateEquips-before-ItemCheck exactly: the
                    // inventory callback sees the previous counter, then the
                    // native mining window sees its decremented value.
                    player.itemAnimation = animation + 1;
                    host.UpdateInventory(player);
                    player.itemAnimation = animation;
                    host.HoldItem(player);
                    Entry(false, "successful UseItem keeps every remaining alternate mining tick fenced " + animation, animation);
                }
                IdleInventory(switchItem: true, "successful alternate completion");

                player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "alternate remains admitted while shared cooldown refuses effect");
                player.itemAnimation = 22;
                Vector2 beforeRecall = player.position;
                host.UseItem(player);
                Equal(beforeRecall, player.position, "cooldown-refused alternate did not teleport");
                host.UpdateInventory(player); host.HoldItem(player);
                Entry(false, "cooldown refusal cannot restore mining");
                IdleInventory(switchItem: true, "cooldown-refused alternate completion");

                // Switching while an animation/timer survives must restore the
                // old inventory instance, not wait for it to be selected again.
                player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "alternate before interrupted switch");
                player.itemAnimation = 22; player.selectedItem = 1;
                host.UpdateInventory(player);
                Equal(true, ReferenceEquals(host.Item, player.GetBestPickaxe()), "switched-away native inventory tool restored during surviving animation");
                player.selectedItem = 0; player.itemAnimation = 0;

                for (int repeat = 0; repeat < 3; repeat++)
                {
                    player.altFunctionUse = 0;
                    Equal(true, host.CanUseItem(player), "primary restored after alternate");
                    Equal(35, host.Item.pick, "primary canonical pick restored");
                    Entry(true, "restored primary native mining entry");
                    player.altFunctionUse = 2;
                    Equal(true, host.CanUseItem(player), "alternate remains usable during cooldown");
                    Entry(false, "repeated alternate remains isolated");
                    IdleInventory(switchItem: false, "repeated alternate completion");
                }
                Equal(true, ReferenceEquals(canonical, host.Data), "tool lifecycle never swaps accepted runtime data");
                Equal(definition, host.Data.ToNetworkJson(), "native lane projection never rewrites saved definition");
                // The same actual mining consumer must remain available to both
                // admitted tool actions, not only to primary item-body tools.
                foreach (string action in new[] { RuntimeBindingAction.UseItemBody, RuntimeBindingAction.SpawnEntity })
                foreach (var lane in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse })
                {
                    var combined = host.Data.RuntimeProgram.Bindings[0];
                    combined.Input = lane; combined.UsePolicy.Action.Kind = action;
                    if (action == RuntimeBindingAction.SpawnEntity)
                    {
                        var root = RootSpawnFixture(0, 1).RuntimeProgram;
                        host.Data.RuntimeProgram.Entities = root.Entities;
                        combined.UsePolicy.Action.TargetId = root.Bindings[0].UsePolicy.Action.TargetId;
                    }
                    typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!
                        .Invoke(host, new object[] { combined });
                    player.altFunctionUse = lane == RuntimeInputKind.AlternateUse ? 2 : 0;
                    Entry(true, "real combined native mining admission " + action + "/" + lane);
                }
                var placement = new RuntimeBindingSpec { Input = RuntimeInputKind.AlternateUse,
                    UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.PlaceItem,
                        Placement = new RuntimePlacementSpec { TileId = -1, WallId = 1, PlaceStyle = 0 } } } };
                typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!
                    .Invoke(host, new object[] { placement });
                player.altFunctionUse = 2;
                Entry(false, "real native placement projection cannot also mine");
                host.UpdateInventory(player); host.HoldItem(player);
                Entry(false, "placement remains isolated after inventory and held callbacks");
                IdleInventory(switchItem: true, "placement projection completion");
                foreach (bool axeOnly in new[] { true, false })
                {
                    host.Data.Gameplay.PickPower = 0;
                    host.Data.Gameplay.AxePower = axeOnly ? 7 : 0;
                    host.Data.Gameplay.HammerPower = axeOnly ? 0 : 20;
                    var body = host.Data.RuntimeProgram.Bindings[0];
                    body.UsePolicy.Action.Kind = RuntimeBindingAction.UseItemBody;
                    typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!
                        .Invoke(host, new object[] { body });
                    Entry(true, axeOnly ? "real native axe-only admission" : "real native hammer-only admission");
                    player.controlUseItem = false;
                    Entry(false, "input-disabled single-power control");
                    player.controlUseItem = true;
                }
            }
            finally { Player.tileTargetX = oldX; Player.tileTargetY = oldY; }
        })));
    }

    public static void PlayedFlailChannelAndCode19LiveAimMatchConsumers()
    {
        using var actors = new NativeActorState();
        var owner = new Player { whoAmI = 0, active = true, position = new Vector2(640, 640), direction = 1 };
        Terraria.Main.player[0] = owner;
        Terraria.Main.myPlayer = 1; // read the existing bounded synced owner axis
        var data = GeneratedItemData.Placeholder();
        var entity = Entity();
        entity.Id = "played-movement"; entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
        var body = new Projectile { owner = 0, active = true, velocity = Vector2.UnitX * 10 };
        body.Center = owner.MountedCenter + Vector2.UnitX * 20;
        var generated = Attach(body);
        generated.Configure(data, entity, 0, 8, Vector2.UnitX);
        var flags = BindingFlags.NonPublic | BindingFlags.Instance;
        var flail = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod("Flail", flags)!;
        var returning = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetField("_returning", flags)!;
        var p = new RuntimeParamsSpec { RangeTiles = 10, ReturnSpeed = 14, DurationTicks = 30 };
        var nativeItem = new Item { channel = false };
        owner.channel = false; owner.StartChanneling(nativeItem);
        Equal(false, owner.channel, "actual native false flag cannot start channel");
        flail.Invoke(generated, new object[] { p });
        Equal(true, (bool)returning.GetValue(generated)!, "frozen A2 returns on first AI consumer");
        returning.SetValue(generated, false);
        nativeItem.channel = true; owner.StartChanneling(nativeItem);
        flail.Invoke(generated, new object[] { p });
        Equal(false, (bool)returning.GetValue(generated)!, "explicit true supports outbound phase");
        owner.channel = false;
        flail.Invoke(generated, new object[] { p });
        Equal(true, (bool)returning.GetValue(generated)!, "release latches return");
        owner.channel = true;
        flail.Invoke(generated, new object[] { p });
        Equal(true, (bool)returning.GetValue(generated)!, "new channel cannot undo latched return");

        var retract = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod("ForwardRetract", flags)!;
        typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetField("_age", flags)!.SetValue(generated, 10);
        body.ai[0] = 1; body.ai[1] = 0;
        retract.Invoke(generated, new object[] { p });
        Equal(true, body.Center.X > owner.MountedCenter.X, "code19 first axis moves collision center right");
        body.ai[0] = 0; body.ai[1] = -1;
        retract.Invoke(generated, new object[] { p });
        AssertVfxNear(new Vector2(owner.MountedCenter.X, body.Center.Y), body.Center,
            "code19 same-age second live axis replaces initial horizontal axis");
        Equal(true, body.Center.Y < owner.MountedCenter.Y, "code19 live aim redirects body/hitbox upward");
        Equal(new Vector2(0, -1), body.velocity, "code19 axis is not fixed initial launch direction");
    }

    public static void PlayedNativeCombinedToolActionsRemainUsable()
    {
        WithGeneratedPrefixScope(() => WithPlayer((player, _) => {
            foreach (string action in new[] { RuntimeBindingAction.UseItemBody, RuntimeBindingAction.SpawnEntity })
            foreach (int prefix in new[] { 0, (int)PrefixID.Legendary })
            {
                var data = PlayedRecallPickData();
                // Nonzero axe/hammer controls prove restoration of all three fields,
                // not only the particular historical pick's sole nonzero power.
                data.Gameplay.AxePower = 7; data.Gameplay.HammerPower = 20;
                var host = GeneratedPrefixHost(data, ItemID.CopperPickaxe);
                if (prefix != 0) Equal(true, host.Item.Prefix(prefix), "native prefix control");
                string prefixStats = GeneratedPrefixStats(host.Item);
                player.altFunctionUse = 2; host.CanUseItem(player);
                Equal(0, host.Item.pick + host.Item.axe + host.Item.hammer, "alternate effect isolation");
                foreach (string isolated in new[] { RuntimeBindingAction.ApplyItemEffects, RuntimeBindingAction.PlaceItem })
                {
                    // Probe the projection directly: placement authorization and
                    // tile mutation are separate owners, not part of this seam.
                    var alternate = host.Data.RuntimeProgram.Bindings[1];
                    alternate.UsePolicy.Action.Kind = isolated;
                    alternate.UsePolicy.StackCost = isolated == RuntimeBindingAction.PlaceItem ? 1 : 0;
                    alternate.UsePolicy.Action.Placement = isolated == RuntimeBindingAction.PlaceItem
                        ? new RuntimePlacementSpec { TileId = -1, WallId = 1, PlaceStyle = 0 } : null;
                    typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!
                        .Invoke(host, new object[] { alternate });
                    string isolatedStats = GeneratedPrefixStats(host.Item);
                    var accepted = host.Data;
                    string definition = accepted.ToNetworkJson();
                    player.inventory[0] = host.Item; player.selectedItem = 0;
                    player.itemAnimation = 2;
                    host.UpdateInventory(player);
                    host.HoldItem(player);
                    Equal(0, host.Item.pick + host.Item.axe + host.Item.hammer, "animated " + isolated + " keeps mining fence");
                    // Actual ItemCheck decrements animation before HoldItem. At
                    // the final inventory pass (1 -> 0), native SmartSelect runs
                    // before HoldItem, so discovery must already work there.
                    player.itemAnimation = 1;
                    host.UpdateInventory(player);
                    Equal(true, ReferenceEquals(host.Item, player.GetBestPickaxe()), "native pre-SmartSelect inventory restore " + isolated);
                    player.itemAnimation = 0;
                    host.HoldItem(player);
                    Equal(35, host.Item.pick, "idle restores canonical pick " + isolated);
                    Equal(7, host.Item.axe, "idle restores canonical axe " + isolated);
                    Equal(20, host.Item.hammer, "idle restores canonical hammer " + isolated);
                    foreach (int strategy in new[] { 1, 2, 3 })
                    {
                        player.selectedItem = 1;
                        typeof(Player).GetMethod("SmartSelect_PickToolForStrategy", BindingFlags.NonPublic | BindingFlags.Instance)!
                            .Invoke(player, new object[] { 40, 40, strategy, false });
                        Equal(0, player.selectedItem, "real native Shift selects restored hammer/axe/pick " + strategy);
                    }
                    Equal(isolatedStats, GeneratedPrefixStats(host.Item), "power-only restore leaves prefix/projection fields untouched");
                    Equal(true, ReferenceEquals(accepted, host.Data), "idle restore retains runtime data identity");
                    Equal(definition, host.Data.ToNetworkJson(), "idle restore leaves accepted definition unchanged");
                    // The one-shot suppression receipt must not become an idle
                    // reauthoring loop that overwrites an unrelated mod's fields.
                    host.Item.pick = 36;
                    host.UpdateInventory(player); host.HoldItem(player);
                    Equal(36, host.Item.pick, "idle restoration retires only its own temporary projection");
                }
                // Both already-admitted tool actions, including a projectile+
                // native-tool composition, retain native powers on either lane.
                var combined = host.Data.RuntimeProgram.Bindings[0];
                combined.UsePolicy.Action.Kind = action;
                if (action == RuntimeBindingAction.SpawnEntity)
                {
                    var root = RootSpawnFixture(0, 1).RuntimeProgram;
                    host.Data.RuntimeProgram.Entities = root.Entities;
                    combined.UsePolicy.Action.TargetId = root.Bindings[0].UsePolicy.Action.TargetId;
                }
                foreach (var lane in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse })
                {
                    combined.Input = lane;
                    typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!
                        .Invoke(host, new object[] { combined });
                    Equal(35, host.Item.pick, "combined action restores pick " + action);
                    Equal(7, host.Item.axe, "combined action restores axe " + action);
                    Equal(20, host.Item.hammer, "combined action restores hammer " + action);
                    if (action == RuntimeBindingAction.UseItemBody)
                        Equal(prefixStats, GeneratedPrefixStats(host.Item), "prefix remains idempotent across lane changes");
                }
            }
        }));
    }
}
