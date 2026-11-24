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
            Equal<object>(3, Caption(third, known.ToArray()), "an unchanged refreshed snapshot retains depth");
            Equal<object>(1, Caption(first, known), "native parents make first generation");
            Equal<object>(2, Caption(second, known), "generated parent adds one generation");
            // Registry refresh can return the same mutable records in a new snapshot.
            second.RecipeMeta.ParentIdentities[0] = "item:Terraria/Wood:9";
            second.RecipeMeta.ParentIdentities[1] = "item:Terraria/StoneBlock:3";
            Equal<object>(1, Caption(second, known.ToArray()), "snapshot refresh sees changed ancestry on same record");
            Equal(0, second.RecipeMeta.GenerationDepth, "presentation never rewrites saved metadata");
            var missing = Entry("missing", "generated:absent", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(missing, new[] { missing }), "missing parent does not invent exact depth");
            var arrived = Entry("absent", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            Equal<object>(2, Caption(missing, new[] { missing, arrived }), "previously missing parent arrival invalidates unknown graph");
            var unresolvedNative = Entry("malformed", "item:unknown", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(unresolvedNative, new[] { unresolvedNative }), "invalid native identity is not a known generation-zero root");
            var cycle = Entry("cycle", "generated:cycle", "item:Terraria/Wood:9");
            Equal<object>("?", Caption(cycle, new[] { cycle }), "cycle has no exact depth");
            var chain = Enumerable.Range(0, 600).Select(i => Entry("chain-" + i, i == 0 ? "item:Terraria/Wood:9" : "generated:chain-" + (i - 1), "item:Terraria/StoneBlock:3")).ToArray();
            Equal<object>("?", Caption(chain[^1], chain), "bounded truncated graph has no exact depth");
        }
        finally { new RecipeJournalUISystem().OnWorldUnload(); Terraria.Main.worldID = oldWorld; }
    }
}
