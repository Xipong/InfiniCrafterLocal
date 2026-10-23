using System;
using System.Reflection;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static FieldInfo JournalField(string name) => typeof(RecipeJournalUISystem).GetField(name, BindingFlags.NonPublic | BindingFlags.Static)!;
    private static GeneratedItemData JournalEntry(string id)
    {
        var data = GeneratedItemData.Placeholder(); data.Id = id; data.Name = id;
        data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString(); return data;
    }
    private static void JournalNavigationWorkflow()
    {
        WithPlayer((player, _) => {
            var ui = new RecipeJournalUISystem(); ui.OnWorldUnload();
            try {
                JournalField("_known").SetValue(null, new[] { JournalEntry("a"), JournalEntry("b") });
                JournalField("_selected").SetValue(null, "a");
                JournalField("_query").SetValue(null, "name:a");
                JournalField("_favoritesOnly").SetValue(null, true);
                JournalField("_page").SetValue(null, 3);
                JournalField("_detailScroll").SetValue(null, 7);
                typeof(RecipeJournalUISystem).GetMethod("Select", BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, new object[] { "b", true, true });
                Equal("", (string)JournalField("_query").GetValue(null)!, "relation target visible outside previous query");
                Equal("b", (string)JournalField("_selected").GetValue(null)!, "relation target selected");
                Equal(true, RecipeJournalUISystem.NavigateBack(), "history restores prior context");
                Equal("a", (string)JournalField("_selected").GetValue(null)!, "prior selection restored");
                Equal("name:a", (string)JournalField("_query").GetValue(null)!, "query restored");
                Equal(true, (bool)JournalField("_favoritesOnly").GetValue(null)!, "favorite filter restored");
                Equal(3, (int)JournalField("_page").GetValue(null)!, "page restored");
                Equal(7, (int)JournalField("_detailScroll").GetValue(null)!, "reading position restored");
                Equal(false, RecipeJournalUISystem.NavigateBack(), "history consumed once");
            } finally { ui.OnWorldUnload(); }
        });
    }
    private static void JournalSavedFilters()
    {
        WithPlayer((player, owner) => {
            int world = Terraria.Main.worldID;
            var preset = new InfiniCrafterLocal.Common.Players.JournalFilterPreset("tag:magic -name:wood", true, true,
                RecipeJournalView.EffectFilter.Equipment, "exact-parent", RecipeJournalView.SortOrder.Recent);
            Equal(true, owner.SaveJournalPreset(2, preset), "save composed search");
            var tag = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(tag);
            owner.SaveJournalPreset(2, null); owner.LoadData(tag);
            Equal(preset, owner.JournalPreset(2), "full search survives real save/load");
            try { Terraria.Main.worldID = world + 1; Equal(true, owner.JournalPreset(2) is null, "presets world scoped"); }
            finally { Terraria.Main.worldID = world; }
            Equal(true, owner.SaveJournalPreset(1, preset with { Query = new string('x', 240) }), "entire supported query can be saved");
            Equal(false, owner.SaveJournalPreset(6, preset), "bounded slots");
            Equal(false, owner.SaveJournalPreset(1, preset with { Query = new string('x', 241) }), "bounded persisted query");
            JournalField("_query").SetValue(null, "tag:magic");
            JournalField("_ingredientFilter").SetValue(null, "exact-parent");
            RecipeJournalUISystem.ResetFilters();
            Equal("", (string)JournalField("_ingredientFilter").GetValue(null)!, "reset clears ingredient as well");
            Equal(true, RecipeJournalUISystem.UndoFilterReset(), "reset is reversible");
            Equal("tag:magic", (string)JournalField("_query").GetValue(null)!, "undo restores search");
            Equal("exact-parent", (string)JournalField("_ingredientFilter").GetValue(null)!, "undo restores ingredient");
            Equal(false, RecipeJournalUISystem.UndoFilterReset(), "undo consumed once");
            new RecipeJournalUISystem().OnWorldUnload();
        });
    }
    private static void JournalStockWorkflow()
    {
        var recipe = JournalEntry("result"); recipe.RecipeMeta.ParentIdentities = new[] { "generated:parent", "generated:parent" };
        var stock = new System.Collections.Generic.Dictionary<string, RecipeInventoryView.Stock> {
            ["generated:parent"] = new("generated:parent", 2, 1, 1),
            ["generated:result"] = new("generated:result", 0, 1, 0),
        };
        Equal(true, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.Owned, stock), "bank-owned result counts owned");
        Equal(false, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.Missing, stock), "owned result not missing");
        Equal(false, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.ReadyCarried, stock), "duplicate parent needs two unprotected units");
        Equal(true, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.ReadyWithBanks, stock), "bank ingredient fills exact shortage for planning");
        stock["generated:parent"] = new("generated:parent", 3, 0, 1);
        Equal(true, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.ReadyCarried, stock), "live stock change makes duplicate recipe ready");
        recipe.RecipeMeta.ParentIdentities = new[] { "generated:parent", "generated:other" };
        Equal(false, RecipeStockFilter.Matches(recipe, RecipeStockFilter.Mode.ReadyWithBanks, stock), "names cannot substitute missing identity");
        WithPlayer((player, owner) => {
            var preset = new InfiniCrafterLocal.Common.Players.JournalFilterPreset("", false, false,
                RecipeJournalView.EffectFilter.All, "", RecipeJournalView.SortOrder.Name, RecipeStockFilter.Mode.ReadyCarried);
            owner.SaveJournalPreset(0, preset);
            var tag = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(tag); owner.LoadData(tag);
            Equal(preset, owner.JournalPreset(0), "stock mode survives native preset save/load");
        });
    }
    private static void JournalDirectOpenWorkflow()
    {
        WithPlayer((player, owner) => {
            var property = typeof(InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            object? before = property.GetValue(null); int mode = Terraria.Main.netMode;
            int local = Terraria.Main.myPlayer; Player oldActor = Terraria.Main.player[0];
            bool menu = Terraria.Main.gameMenu, active = player.active, dead = player.dead;
            using var registry = new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
            try {
                property.SetValue(null, registry); Terraria.Main.myPlayer = 0; Terraria.Main.player[0] = player; Terraria.Main.netMode = 0; Terraria.Main.gameMenu = false; player.active = true; player.dead = false;
                var data = AssetOwnerData("journal_open_known", "journal_open.png");
                registry.RegisterLocal(data, false, false);
                new RecipeJournalUISystem().OnWorldUnload();
                Equal(false, RecipeJournalUISystem.OpenRecipe("unknown"), "unknown direct link refused");
                Equal(false, RecipeJournalUISystem.IsOpen, "invalid link does not open UI");
                JournalField("_query").SetValue(null, "impossible query");
                Equal(true, RecipeJournalUISystem.OpenRecipe(data.Id), "known current-world exact ID opens");
                Equal(data.Id, (string)JournalField("_selected").GetValue(null)!, "exact selection");
                Equal("Guide", JournalField("_detailPage").GetValue(null)!.ToString(), "direct open presents actual item guide");
                Equal("", (string)JournalField("_query").GetValue(null)!, "hidden target revealed");
                Equal(true, owner.JournalLastVisited(data.Id) > 0, "direct link records reading history");
                int world = Terraria.Main.worldID;
                try { Terraria.Main.worldID = world + 1; Equal(false, RecipeJournalUISystem.OpenRecipe(data.Id), "foreign definition refused"); }
                finally { Terraria.Main.worldID = world; }
            } finally {
                new RecipeJournalUISystem().OnWorldUnload(); property.SetValue(null, before);
                Terraria.Main.myPlayer = local; Terraria.Main.player[0] = oldActor;
                Terraria.Main.netMode = mode; Terraria.Main.gameMenu = menu; player.active = active; player.dead = dead;
            }
        });
    }
}
