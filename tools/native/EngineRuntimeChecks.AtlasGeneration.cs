using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;

internal static partial class EngineRuntimeChecks
{
    private sealed class AtlasGenerationObserved : Exception { }
    private static void AtlasDetailGenerationUsesKnownAncestry()
    {
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        Type ui = typeof(RecipeJournalUISystem);
        object? Get(string name) => ui.GetField(name, flags)!.GetValue(null);
        void Set(string name, object value) => ui.GetField(name, flags)!.SetValue(null, value);
        GeneratedItemData Entry(string id, params string[] parents) {
            var data = GeneratedItemData.Placeholder(); data.Id = id; data.Name = id;
            data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = "17";
            data.RecipeMeta.GenerationDepth = 0; data.RecipeMeta.ParentIdentities = parents;
            return data;
        }
        object? observed = null;
        using var paper = new Hook(ui.GetMethod("DrawPaperSlip", flags)!, (Action<SpriteBatch, Rectangle, bool>)((_, _, _) => {}));
        using var button = new Hook(ui.GetMethod("Button", flags)!, (Func<SpriteBatch, Rectangle, string, bool, Vector2, bool, bool, bool>)((_, _, _, _, _, _, _) => false));
        using var label = new Hook(ui.GetMethod("Label", flags)!, (Action<SpriteBatch, string, Vector2, Color, float, int>)((_, _, _, _, _, _) => {}));
        using var text = new Hook(ui.GetMethod("Text", flags)!, (Func<string, object[], string>)((key, args) => {
            if (key == "Generation") { observed = args.Single(); throw new AtlasGenerationObserved(); }
            return key;
        }));
        int oldWorld = Terraria.Main.worldID;
        try {
            Terraria.Main.worldID = 17; new RecipeJournalUISystem().OnWorldUnload();
            var player = new InfiniCraftPlayer();
            object Caption(GeneratedItemData root, GeneratedItemData[] known) {
                observed = null; Set("_selected", root.Id); Set("_known", known);
                try { ui.GetMethod("DrawDetail", flags)!.Invoke(null, new object?[] { null, root, new Rectangle(0, 0, 500, 600), player, false, new Vector2(-100) }); }
                catch (TargetInvocationException error) when (error.InnerException is AtlasGenerationObserved) { }
                return observed ?? throw new Exception("Actual detail did not emit generation caption");
            }
            var first = Entry("first", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            var second = Entry("second", "generated:first", "item:Terraria/Wood:9");
            var third = Entry("third", "generated:second", "generated:first");
            var known = new[] { first, second, third };
            Equal<object>(3, Caption(third, known), "actual detail derives complete chain despite stored zero");
            object graph = Get("_lineage")!;
            Equal<object>(3, Caption(third, known), "same snapshot renders same depth");
            Equal(true, ReferenceEquals(graph, Get("_lineage")), "unchanged detail frames reuse graph");
            Equal<object>(3, Caption(third, known.ToArray()), "fresh unchanged snapshot retains depth");
            Equal(true, ReferenceEquals(graph, Get("_lineage")), "fresh unchanged snapshot avoids graph layout and allocation");
            Equal<object>(1, Caption(first, known), "native parents make first generation");
            Equal(false, ReferenceEquals(graph, Get("_lineage")), "root change rebuilds cached graph");
            Equal<object>(2, Caption(second, known), "generated parent adds one generation");
            // Registry refresh can return the same mutable records in a new snapshot.
            Set("_lineagePan", new Vector2(27, -13)); Set("_lineageZoom", .75f);
            var canvas = new Rectangle(10, 20, 700, 500); Set("_lineageCanvas", canvas);
            object previousGraph = Get("_lineage")!;
            second.RecipeMeta.ParentIdentities[0] = "item:Terraria/Wood:9";
            second.RecipeMeta.ParentIdentities[1] = "item:Terraria/StoneBlock:3";
            Equal<object>(1, Caption(second, known.ToArray()), "snapshot refresh sees changed ancestry on same record");
            Equal(false, ReferenceEquals(previousGraph, Get("_lineage")), "new snapshot invalidates old cached graph");
            Equal(new Vector2(27, -13), (Vector2)Get("_lineagePan")!, "same root refresh preserves pan");
            Equal(.75f, (float)Get("_lineageZoom")!, "same root refresh preserves zoom");
            Equal(canvas, (Rectangle)Get("_lineageCanvas")!, "same root refresh does not trigger fit");
            Equal(0, second.RecipeMeta.GenerationDepth, "presentation never rewrites saved metadata");
            object beforeCaption = Get("_lineage")!;
            second.Name = "Renamed item";
            Equal<object>(1, Caption(second, known.ToArray()), "caption change retains known generation");
            Equal(false, ReferenceEquals(beforeCaption, Get("_lineage")), "captured graph caption updates on snapshot");
            object beforeReplacement = Get("_lineage")!;
            var replacement = Entry("second", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            Equal<object>(1, Caption(replacement, new[] { first, replacement, third }), "replacement definition retains depth");
            Equal(false, ReferenceEquals(beforeReplacement, Get("_lineage")), "new record reference refreshes graph data and icon owner");
            var missing = Entry("missing", "generated:absent", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(missing, new[] { missing }), "missing parent does not invent exact depth");
            var arrived = Entry("absent", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            Equal<object>(2, Caption(missing, new[] { missing, arrived }), "previously missing parent arrival invalidates unknown graph");
            Equal(Rectangle.Empty, (Rectangle)Get("_lineageCanvas")!, "new root requests normal viewport fit");
            var unresolvedNative = Entry("malformed", "item:unknown", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(unresolvedNative, new[] { unresolvedNative }), "invalid native identity is not a known generation-zero root");
            var cycle = Entry("cycle", "generated:cycle", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(cycle, new[] { cycle }), "cycle has no exact depth");
            var chain = Enumerable.Range(0, 600).Select(i => Entry("chain-" + i, i == 0 ? "item:Terraria/Wood:9" : "generated:chain-" + (i - 1), "item:Terraria/StoneBlock:3")).ToArray();
            Equal<object>("?", Caption(chain[^1], chain), "bounded truncated graph has no exact depth");
            object deepGraph = Get("_lineage")!;
            var ensure = ui.GetMethod("EnsureLineageGraph", flags)!;
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            var watch = System.Diagnostics.Stopwatch.StartNew();
            for (int i = 0; i < 100; i++) {
                Set("_known", chain.ToArray()); ensure.Invoke(null, null);
                Equal(true, ReferenceEquals(deepGraph, Get("_lineage")), "unchanged deep snapshot does not repeat layout");
            }
            watch.Stop();
            Console.WriteLine($"ATLAS_REFRESH snapshots=100 records={chain.Length} layoutRebuilds=0 elapsedMs={watch.Elapsed.TotalMilliseconds:F2} allocatedBytes={GC.GetAllocatedBytesForCurrentThread()-allocated}");
            new RecipeJournalUISystem().OnWorldUnload();
            Equal(true, Get("_lineage") is null, "world reset clears detail graph");
        }
        finally { new RecipeJournalUISystem().OnWorldUnload(); Terraria.Main.worldID = oldWorld; }
    }
}
