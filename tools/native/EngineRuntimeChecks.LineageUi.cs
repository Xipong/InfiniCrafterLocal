using System;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameInput;

internal static partial class EngineRuntimeChecks
{
    private static void LineageLocalizationUsesNativeFilenamePrefix()
    {
        WithForgePresentationLanguages(locale =>
        {
            foreach (string suffix in new[] { "Title", "Search", "All", "Favorites", "NoFavorites", "Empty",
                "NoMatches", "Welcome", "Back", "Save", "Saved", "Ingredients", "Ingredient",
                "OpenParent", "Result", "Notes", "Close", "Lineage", "LineageMissing", "LineageBrowserHint",
                "LineageBrowserAbsent", "LineageCycle", "LineageTruncated", "FilterAll", "FilterHealing",
                "FilterMining", "FilterSummon", "FilterMobility" })
            {
                string key = "Mods.InfiniCrafterLocal.RecipeJournal." + suffix;
                string value = RecipeJournalUISystem.Text(suffix);
                Equal(false, string.IsNullOrWhiteSpace(value) || value == key, locale + " translated journal key " + suffix);
            }
            foreach (string suffix in new[] { "Generation", "Children", "UsingIngredient", "Page", "Count" })
            {
                string key = "Mods.InfiniCrafterLocal.RecipeJournal." + suffix;
                string value = RecipeJournalUISystem.Text(suffix, 2, 3);
                Equal(false, string.IsNullOrWhiteSpace(value) || value == key || value.Contains("{0}") || value.Contains("{1}"),
                    locale + " translated formatted journal key " + suffix);
            }
        });
    }

    private static void LineageViewportKeepsAnchorAndReachableHitTargets()
    {
        var data = GeneratedItemData.Placeholder(); data.Id = "viewport";
        data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = "17";
        data.RecipeMeta.ParentIdentities = new[] { "item:Terraria:Wood:9", "item:Terraria:StoneBlock:3" };
        var graph = RecipeLineageGraph.Build(data, new[] { data });
        var fitted = RecipeJournalUISystem.FitLineageView(new Vector2(800, 600), new Vector2(graph.Width, graph.Height), graph.Nodes[graph.RootIndex].Position);
        Equal(true, fitted.Pan.X >= 0 && fitted.Pan.Y >= 0
            && fitted.Pan.X + graph.Width * fitted.Zoom <= 800 && fitted.Pan.Y + graph.Height * fitted.Zoom <= 600,
            "ordinary graph fully fits viewport");
        var pan = new Vector2(-100, 30); var anchor = new Vector2(237, 83);
        foreach (float before in new[] { .25f, .6f, 1f, 2f })
        foreach (float requested in new[] { .1f, .25f, .75f, 1.5f, 2f, 10f })
        {
            float after = RecipeJournalUISystem.ClampLineageZoom(requested);
            Vector2 moved = RecipeJournalUISystem.AnchoredLineagePan(pan, anchor, before, after);
            Equal(true, Vector2.Distance((anchor - pan) / before, (anchor - moved) / after) < .001f,
                "zoom retains graph point under cursor including clamped zoom");
            for (int i = 0; i < graph.Nodes.Length; i++)
                Equal(i, RecipeJournalUISystem.HitLineageNode(graph, moved + graph.Nodes[i].Position * after, moved, after),
                    "each native/generated node remains hit-testable at every scale");
            Equal(-1, RecipeJournalUISystem.HitLineageNode(graph, new Vector2(-100000), moved, after), "empty map never selects a node");
        }
        foreach (var viewport in new[] { new Vector2(160, 120), new Vector2(800, 600) })
        foreach (float zoom in new[] { .25f, 1f, 2f })
        foreach (var extreme in new[] { new Vector2(-100000), new Vector2(100000), Vector2.Zero })
        {
            var size = new Vector2(graph.Width, graph.Height);
            Vector2 bounded = RecipeJournalUISystem.ClampLineagePan(extreme, viewport, size, zoom);
            Equal(true, bounded.X < viewport.X && bounded.Y < viewport.Y && bounded.X + size.X * zoom > 0 && bounded.Y + size.Y * zoom > 0,
                "pan cannot strand entire graph beyond viewport");
            Equal(bounded, RecipeJournalUISystem.ClampLineagePan(bounded, viewport, size, zoom), "pan bounds are idempotent");
        }
    }

    private static void LineageInputReleasesOwnedFocusAcrossInterruptions()
    {
        bool oldBlock = Terraria.Main.blockInput, oldWriting = PlayerInput.WritingText;
        try
        {
            Terraria.Main.blockInput = false; PlayerInput.WritingText = false;
            RecipeJournalUISystem.SetSearchFocus(true);
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "search owns text focus");
            Equal(false, RecipeJournalUISystem.CanResumeInput(true, true, false), "covered UI suppresses input");
            Equal(false, Terraria.Main.blockInput || PlayerInput.WritingText, "overlay releases journal-owned text focus");
            Equal(false, RecipeJournalUISystem.CanResumeInput(false, true, false), "held left cannot click through dismissal");
            Equal(false, RecipeJournalUISystem.CanResumeInput(false, false, true), "held right cannot click through dismissal");
            Equal(true, RecipeJournalUISystem.CanResumeInput(false, false, false), "release restores input");
            Terraria.Main.blockInput = true; PlayerInput.WritingText = true;
            RecipeJournalUISystem.SetSearchFocus(true);
            RecipeJournalUISystem.SetSearchFocus(false);
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "journal never releases another interface's focus");
            new RecipeJournalUISystem().OnWorldUnload();
            Equal(false, RecipeJournalUISystem.IsOpen, "world unload closes session");
            Equal(true, Terraria.Main.blockInput && PlayerInput.WritingText, "unload preserves foreign focus reservation");
        }
        finally
        {
            RecipeJournalUISystem.SetSearchFocus(false);
            Terraria.Main.blockInput = oldBlock; PlayerInput.WritingText = oldWriting;
            RecipeJournalUISystem.CanResumeInput(false, false, false);
        }
    }

    private static void LineageNativeHoverAndDeferredHandoffKeepOwnership()
    {
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        var type = typeof(RecipeJournalUISystem);
        void Set(string name, object? value) => type.GetField(name, flags)!.SetValue(null, value);
        var open = type.GetProperty(nameof(RecipeJournalUISystem.IsOpen))!;
        Item oldHover = Terraria.Main.HoverItem;
        bool oldFocus = Terraria.Main.hasFocus, oldHide = Terraria.Main.hideUI, oldMap = Terraria.Main.mapFullscreen,
            oldOptions = Terraria.Main.ingameOptionsWindow, oldFancy = Terraria.Main.inFancyUI, oldChat = Terraria.Main.drawingPlayerChat,
            oldBlock = Terraria.Main.blockInput, oldWriting = PlayerInput.WritingText;
        int oldX = PlayerInput.MouseX, oldY = PlayerInput.MouseY;
        var oldUi = Terraria.UI.UserInterface.ActiveInstance;
        const string query = "RecipeBrowser/QueryHoveredItem";
        var keys = PlayerInput.Triggers.JustPressed.KeyStatus;
        bool existed = keys.TryGetValue(query, out bool oldPressed);
        var native = new Item { type = Terraria.ID.ItemID.Wood, stack = 1 };
        var unrelated = new Item { type = Terraria.ID.ItemID.StoneBlock, stack = 1 };
        var graph = new RecipeLineageGraph { Nodes = new[] {
            new RecipeLineageGraph.Node { Kind = RecipeLineageGraph.NodeKind.Native, Position = new Vector2(100, 100) },
            new RecipeLineageGraph.Node { Kind = RecipeLineageGraph.NodeKind.Generated, Position = new Vector2(300, 100) }
        }};
        void Session()
        {
            new RecipeJournalUISystem().OnWorldUnload();
            open.SetValue(null, true); Set("_lineageOpen", true); Set("_lineage", graph);
            Set("_lineageCanvas", new Rectangle(0, 0, 500, 400)); Set("_nativeNodes", new Item?[] { native, null });
            PlayerInput.MouseX = (int)(100 * Terraria.Main.UIScale); PlayerInput.MouseY = (int)(100 * Terraria.Main.UIScale);
            keys[query] = false;
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, ReferenceEquals(native, Terraria.Main.HoverItem), "input publishes exact native node without drawing or name guesses");
        }
        try
        {
            Terraria.Main.hasFocus = true; Terraria.Main.hideUI = Terraria.Main.mapFullscreen = Terraria.Main.ingameOptionsWindow = false;
            Terraria.Main.inFancyUI = Terraria.Main.drawingPlayerChat = Terraria.Main.blockInput = PlayerInput.WritingText = false;
            Terraria.UI.UserInterface.ActiveInstance = null!;
            Session();
            keys[query] = true;
            RecipeJournalUISystem.QueueLineageBrowserHandoff(false);
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "absent RecipeBrowser does not dismiss atlas");
            keys[query] = false;
            RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "unpressed query does not dismiss atlas");
            // The public registered trigger is binding-independent: no Mouse3 poll is involved.
            keys[query] = true;
            RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            Equal(true, RecipeJournalUISystem.IsOpen && ReferenceEquals(native, Terraria.Main.HoverItem),
                "queued handoff retains hover for next autopause UpdateUI consumer");
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "next input stage dismisses after regular or autopause consumer");
            Equal(false, ReferenceEquals(native, Terraria.Main.HoverItem), "handoff releases only owned hover");
            RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(false, RecipeJournalUISystem.IsOpen, "held/repeated trigger cannot reopen or duplicate handoff");
            Session(); keys[query] = true;
            PlayerInput.MouseX = (int)(450 * Terraria.Main.UIScale);
            RecipeJournalUISystem.UpdateLineageInput();
            RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "moving off node clears stale query target before trigger consumer");
            Session(); keys[query] = true;
            PlayerInput.MouseX = (int)(300 * Terraria.Main.UIScale);
            RecipeJournalUISystem.UpdateLineageInput();
            RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "generated nodes never become native RecipeBrowser targets");
            Session(); Terraria.Main.HoverItem = unrelated; Terraria.Main.hideUI = true;
            RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, ReferenceEquals(unrelated, Terraria.Main.HoverItem), "covered atlas never clears another interface hover");
            Terraria.Main.hideUI = false;
            Session(); keys[query] = true; RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            type.GetMethod("Close", flags)!.Invoke(null, null);
            open.SetValue(null, true); RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "explicit close cancels pending handoff before reopen");
            Session(); keys[query] = true; RecipeJournalUISystem.QueueLineageBrowserHandoff(true);
            new RecipeJournalUISystem().OnWorldUnload();
            open.SetValue(null, true); RecipeJournalUISystem.UpdateLineageInput();
            Equal(true, RecipeJournalUISystem.IsOpen, "world reset cancels pending handoff rather than closing next session");
        }
        finally
        {
            new RecipeJournalUISystem().OnWorldUnload(); Terraria.Main.HoverItem = oldHover;
            Terraria.Main.hasFocus = oldFocus; Terraria.Main.hideUI = oldHide; Terraria.Main.mapFullscreen = oldMap;
            Terraria.Main.ingameOptionsWindow = oldOptions; Terraria.Main.inFancyUI = oldFancy; Terraria.Main.drawingPlayerChat = oldChat;
            Terraria.Main.blockInput = oldBlock; PlayerInput.WritingText = oldWriting;
            PlayerInput.MouseX = oldX; PlayerInput.MouseY = oldY; Terraria.UI.UserInterface.ActiveInstance = oldUi;
            if (existed) keys[query] = oldPressed; else keys.Remove(query);
        }
    }

    private static void LineageBoundedStressReportsActualLayoutCost()
    {
        var entries = Enumerable.Range(0, 255).Select(i => {
            var d = GeneratedItemData.Placeholder(); d.Id = "stress-" + i; d.Name = d.Id;
            d.RecipeMeta.WorldScoped = true; d.RecipeMeta.WorldId = "stress";
            d.RecipeMeta.ParentIdentities = new[] { i == 0 ? "item:Terraria:Wood:9" : "generated:stress-" + (i - 1), "item:Probe:Leaf" + i + ":" + (10000 + i) };
            return d;
        }).ToArray();
        long allocated = GC.GetAllocatedBytesForCurrentThread(); var clock = Stopwatch.StartNew();
        var graph = RecipeLineageGraph.Build(entries[^1], entries);
        clock.Stop(); allocated = GC.GetAllocatedBytesForCurrentThread() - allocated;
        Equal(true, graph.Nodes.Length <= 512, "adversarial graph stays within native node budget");
        Equal(false, graph.IsTruncated, "within-budget ancestry remains complete");
        foreach (var viewport in new[] { new Vector2(160, 120), new Vector2(800, 600) })
        {
            var view = RecipeJournalUISystem.FitLineageView(viewport, new Vector2(graph.Width, graph.Height), graph.Nodes[graph.RootIndex].Position);
            Vector2 rootOnScreen = view.Pan + graph.Nodes[graph.RootIndex].Position * view.Zoom;
            Equal(true, rootOnScreen.X > 0 && rootOnScreen.X < viewport.X && rootOnScreen.Y > 0 && rootOnScreen.Y < viewport.Y,
                "deep graph initial fit keeps selected root visible at readability floor");
            Equal(graph.RootIndex, RecipeJournalUISystem.HitLineageNode(graph, rootOnScreen, view.Pan, view.Zoom),
                "deep graph selected root remains immediately reachable after fit");
        }
        int visibleSegments = 0;
        foreach (var edge in graph.Edges)
        {
            var range = RecipeJournalUISystem.VisibleLineageSegments(edge.Path, graph.Height / 2, graph.Height / 2 + 600);
            visibleSegments += Math.Max(0, range.End - range.Start);
            for (int p = 1; p < edge.Path.Length; p++)
            {
                bool intersects = edge.Path[p - 1].Y >= graph.Height / 2 && edge.Path[p].Y <= graph.Height / 2 + 600;
                if (intersects) Equal(true, p >= range.Start && p < range.End, "binary clipping preserves every visible edge segment");
            }
        }
        Equal(true, visibleSegments < graph.Edges.Sum(e => e.Path.Length) / 10, "viewport excludes hidden generations from per-frame segment loop");
        Console.WriteLine($"LINEAGE_CULL candidateSegments={visibleSegments}");
        Console.WriteLine($"LINEAGE_STRESS nodes={graph.Nodes.Length} edges={graph.Edges.Length} pathVertices={graph.Edges.Sum(e => e.Path.Length)} elapsedMs={clock.Elapsed.TotalMilliseconds:F1} allocatedBytes={allocated}");
    }
}
