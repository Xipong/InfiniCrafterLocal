using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameInput;
using Terraria.ModLoader;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasModalMouseBlocksNativeInventoryAndUse()
    {
        const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
        var ui = typeof(RecipeJournalUISystem);
        var system = new RecipeJournalUISystem();
        int oldLocal = Terraria.Main.myPlayer;
        Player previous = Terraria.Main.player[0];
        SpriteBatch oldBatch = Terraria.Main.spriteBatch;
        var scrollOwners = (List<string>)typeof(PlayerInput).GetField("MouseInModdedUI", all)!.GetValue(null)!;
        var oldScroll = scrollOwners.ToArray();
        bool focus = Terraria.Main.hasFocus, inventory = Terraria.Main.playerInventory, menu = Terraria.Main.gameMenu;
        bool hide = Terraria.Main.hideUI, map = Terraria.Main.mapFullscreen, options = Terraria.Main.ingameOptionsWindow, fancy = Terraria.Main.inFancyUI;
        bool chat = Terraria.Main.drawingPlayerChat, block = Terraria.Main.blockInput, writing = PlayerInput.WritingText;
        bool left = Terraria.Main.mouseLeft, right = Terraria.Main.mouseRight, leftRelease = Terraria.Main.mouseLeftRelease, rightRelease = Terraria.Main.mouseRightRelease;
        var savedHooks = new List<(FieldInfo Field, object? Value)>();
        void Open(Player player)
        {
            ui.GetField("<IsOpen>k__BackingField", all)!.SetValue(null, true);
            ui.GetField("_sessionOwner", all)!.SetValue(null, player);
            ui.GetField("_sessionWorld", all)!.SetValue(null, Terraria.Main.worldID);
        }
        List<GameInterfaceLayer> Layers()
        {
            var native = (Terraria.Main)RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Main));
            typeof(Terraria.Main).GetField("_needToSetupDrawInterfaceLayers", all)!.SetValue(native, true);
            typeof(Terraria.Main).GetMethod("SetupDrawInterfaceLayers", all)!.Invoke(native, null);
            var layers = (List<GameInterfaceLayer>)typeof(Terraria.Main).GetField("_gameInterfaceLayers", all)!.GetValue(native)!;
            system.ModifyInterfaceLayers(layers);
            return layers;
        }
        try
        {
            system.OnWorldUnload();
            Terraria.Main.myPlayer = 0;
            Terraria.Main.hasFocus = Terraria.Main.playerInventory = true;
            Terraria.Main.gameMenu = Terraria.Main.hideUI = Terraria.Main.mapFullscreen = Terraria.Main.ingameOptionsWindow = Terraria.Main.inFancyUI = false;
            Terraria.Main.drawingPlayerChat = Terraria.Main.blockInput = PlayerInput.WritingText = false;
            Terraria.Main.mouseLeft = Terraria.Main.mouseRight = Terraria.Main.mouseLeftRelease = Terraria.Main.mouseRightRelease = true;
            Terraria.Main.spriteBatch = null!;
            WithPlayer((player, owner) =>
            {
                player.active = true; player.dead = false; player.whoAmI = 0;
                Terraria.Main.player[0] = player;
                Open(player);
                var layers = Layers();
                var nativeInventory = layers.Single(l => l.Name == "Vanilla: Inventory");
                Equal(false, nativeInventory.Active, "actual native inventory layer cannot process left/right/shift while atlas owns the mouse");
                Equal(true, nativeInventory.Draw(), "native layer returns before SpriteBatch and DrawInventory, even without a graphics device");
                Equal(true, layers.Any(l => l.Name == "InfiniCrafterLocal: Recipe Journal"), "atlas layer remains present");
                Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseRight && Terraria.Main.mouseLeftRelease && Terraria.Main.mouseRightRelease,
                    "native inventory gate leaves raw buttons available to atlas pan/buttons and RecipeBrowser");
                ui.GetField("_awaitingMouseRelease", all)!.SetValue(null, true);
                Equal(false, Layers().Single(l => l.Name == "Vanilla: Inventory").Active, "held-button resume fence never leaks to inventory");
                ui.GetField("_awaitingMouseRelease", all)!.SetValue(null, false);
                scrollOwners.Clear(); scrollOwners.Add("OtherMod: scope");
                system.PostUpdateInput();
                Equal(true, player.mouseInterface, "early post-input gate covers cursor outside the book too");
                Equal(true, scrollOwners.Count > 1, "native paused/full-update recipe wheel sees atlas scroll ownership");
                foreach (string name in new[] { "HookSetControls", "HookCanUseItem" })
                {
                    var field = typeof(PlayerLoader).GetField(name, all)!;
                    object original = field.GetValue(null)!; savedHooks.Add((field, original));
                    var query = field.FieldType.GetProperty("HookOverrideQuery", all)!.GetValue(original);
                    var ctor = field.FieldType.GetConstructors(all).Single(c => c.GetParameters().Length == 1 && c.GetParameters()[0].ParameterType.IsInstanceOfType(query));
                    object hook = ctor.Invoke(new[] { query });
                    field.FieldType.GetMethod("Update")!.Invoke(hook, new object[] { new ModPlayer[] { owner } });
                    field.SetValue(null, hook);
                }
                player.controlUseItem = player.controlUseTile = player.controlThrow = player.channel = true;
                player.controlLeft = true;
                PlayerLoader.SetControls(player);
                Equal(false, player.controlUseItem || player.controlUseTile || player.controlThrow || player.channel, "real ModPlayer controls block use, alternate interaction, drop and channel");
                Equal(true, player.controlLeft, "modal mouse does not reserve movement keys");
                var oldCursor = Terraria.Main.mouseItem;
                try
                {
                    Terraria.Main.mouseItem = new Item { type = Terraria.ID.ItemID.Wood, stack = 7, maxStack = 9999 };
                    player.dropItemCheck();
                    Equal(Terraria.ID.ItemID.Wood, Terraria.Main.mouseItem.type, "native cursor-drop path retains the cursor item outside atlas");
                    Equal(7, Terraria.Main.mouseItem.stack, "native cursor-drop path preserves material count");
                }
                finally { Terraria.Main.mouseItem = oldCursor; }
                var item = new Item { type = Terraria.ID.ItemID.Wood, stack = 1, shoot = -1, createTile = -1, createWall = -1 };
                // Fast-use may reassert controlUseItem after SetControls: the actual
                // ItemCheck admission still must reach the CanUseItem override first.
                player.controlUseItem = true;
                var canUse = typeof(Player).GetMethod("ItemCheck_CheckCanUse", all)!;
                Equal(false, (bool)canUse.Invoke(player, new object[] { item })!, "native ItemCheck blocks late fast-use activation");
                player.altFunctionUse = 2;
                Equal(false, (bool)canUse.Invoke(player, new object[] { item })!, "native alternate item use is blocked too");
                player.altFunctionUse = 0;
                WithPlayer((remote, remoteOwner) =>
                {
                    remote.active = true; remote.whoAmI = 1;
                    remote.controlUseItem = remote.controlUseTile = remote.controlThrow = remote.channel = true;
                    PlayerLoader.SetControls(remote);
                    Equal(true, remote.controlUseItem && remote.controlUseTile && remote.controlThrow && remote.channel,
                        "local atlas never changes another player's controls");
                    Equal(true, remoteOwner.CanUseItem(item), "remote player's ordinary item admission is unaffected");
                });
                Terraria.Main.inFancyUI = true;
                Equal(true, Layers().Single(l => l.Name == "Vanilla: Inventory").Active, "covered atlas yields native UI ownership");
                system.PostUpdateInput();
                Equal(true, scrollOwners.SequenceEqual(new[] { "OtherMod: scope" }), "covered/autopause cleanup removes only the atlas scroll marker");
                Equal(true, owner.CanUseItem(item), "covered atlas does not block another interface's item use");
                Terraria.Main.inFancyUI = false;
                system.OnWorldUnload();
                Equal(true, Layers().Single(l => l.Name == "Vanilla: Inventory").Active, "closed atlas restores ordinary inventory layer");
                Equal(true, owner.CanUseItem(item), "closed atlas restores ordinary item admission");
            });
        }
        finally
        {
            foreach (var saved in savedHooks) saved.Field.SetValue(null, saved.Value);
            system.OnWorldUnload();
            Terraria.Main.myPlayer = oldLocal; Terraria.Main.player[0] = previous; Terraria.Main.spriteBatch = oldBatch;
            Terraria.Main.hasFocus = focus; Terraria.Main.playerInventory = inventory; Terraria.Main.gameMenu = menu;
            Terraria.Main.hideUI = hide; Terraria.Main.mapFullscreen = map; Terraria.Main.ingameOptionsWindow = options; Terraria.Main.inFancyUI = fancy;
            Terraria.Main.drawingPlayerChat = chat; Terraria.Main.blockInput = block; PlayerInput.WritingText = writing;
            Terraria.Main.mouseLeft = left; Terraria.Main.mouseRight = right; Terraria.Main.mouseLeftRelease = leftRelease; Terraria.Main.mouseRightRelease = rightRelease;
            scrollOwners.Clear(); scrollOwners.AddRange(oldScroll);
        }
    }
}
