using System.Reflection;
using Terraria.GameInput;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void JournalHotkeyToleratesTriggerLifecycle()
    {
        var system = new RecipeJournalUISystem();
        var binding = typeof(RecipeJournalUISystem).GetField("_toggleJournalTrigger", BindingFlags.Static | BindingFlags.NonPublic)!;
        var triggersField = typeof(PlayerInput).GetField("Triggers", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!;
        var keybind = typeof(RecipeJournalUISystem).GetProperty(nameof(RecipeJournalUISystem.ToggleJournalKey))!;
        object? oldKeybind = keybind.GetValue(null);
        object? oldBinding = binding.GetValue(null), oldTriggers = triggersField.GetValue(null);
        var players = Terraria.Main.player;
        int local = Terraria.Main.myPlayer, mode = Terraria.Main.netMode;
        bool menu = Terraria.Main.gameMenu, focus = Terraria.Main.hasFocus, inventory = Terraria.Main.playerInventory;
        bool blocked = Terraria.Main.blockInput, writing = PlayerInput.WritingText, chat = Terraria.Main.drawingPlayerChat;
        var triggers = new TriggersPack();
        const string key = "InfiniCrafterLocal/ToggleRecipeJournal";
        try
        {
            system.OnWorldUnload();
            binding.SetValue(null, key);
            triggersField.SetValue(null, triggers);
            Terraria.Main.myPlayer = 0; Terraria.Main.netMode = 0;
            Terraria.Main.player = new[] { new Terraria.Player { active = true } };
            Terraria.Main.hasFocus = true; Terraria.Main.blockInput = PlayerInput.WritingText = Terraria.Main.drawingPlayerChat = false;
            Terraria.Main.gameMenu = true;
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "loading without registered trigger is inert");
            Terraria.Main.gameMenu = false;
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "active player during trigger rebuild is inert");
            triggers.JustPressed.KeyStatus[key] = false;
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "unpressed initialized trigger is inert");
            triggers.JustPressed.KeyStatus[key] = true;
            system.PostUpdateInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "registered press opens journal");
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "next press closes journal");
            triggers.JustPressed.KeyStatus.Remove(key);
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "removed reload trigger is inert");
            triggers.JustPressed.KeyStatus[key] = true;
            system.Unload();
            system.PostUpdateInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "unloaded binding cannot consume stale trigger");
        }
        finally
        {
            system.OnWorldUnload(); binding.SetValue(null, oldBinding); keybind.SetValue(null, oldKeybind); triggersField.SetValue(null, oldTriggers);
            Terraria.Main.player = players; Terraria.Main.myPlayer = local; Terraria.Main.netMode = mode;
            Terraria.Main.gameMenu = menu; Terraria.Main.hasFocus = focus; Terraria.Main.playerInventory = inventory;
            Terraria.Main.blockInput = blocked; PlayerInput.WritingText = writing; Terraria.Main.drawingPlayerChat = chat;
        }
    }

    private static void JournalHotkeyAndCompactControlsStayScoped()
    {
        Equal(true, RecipeJournalUISystem.CanToggleFromKey(true, false, false, false, false, false, false), "ordinary gameplay can toggle");
        for (int blocked = 0; blocked < 7; blocked++)
        {
            bool[] flags = { true, false, false, false, false, false, false };
            flags[blocked] = blocked != 0;
            Equal(false, RecipeJournalUISystem.CanToggleFromKey(flags[0], flags[1], flags[2], flags[3], flags[4], flags[5], flags[6]), "focus/menu/death/text/chat/block/rebind refuse toggle");
        }
        // UI-space dimensions also model high UI scales. Every visible detail
        // area keeps both controls contained and non-overlapping, including <200px.
        foreach (int width in new[] { 60, 96, 160, 240, 360, 640 })
        foreach (int height in new[] { 40, 60, 90, 120, 199, 200, 300 })
        {
            var area = new Rectangle(17, 31, width, height);
            var controls = RecipeJournalView.DetailControls(area);
            Equal(true, area.Contains(controls.Back), "back inside short detail");
            Equal(true, area.Contains(controls.Save), "save inside short detail");
            Equal(false, controls.Back.Intersects(controls.Save), "controls do not overlap");
            Equal(true, controls.Back.Width > 0 && controls.Save.Width > 0 && controls.Save.Height >= 20, "usable controls stay visible");
        }
    }
}
