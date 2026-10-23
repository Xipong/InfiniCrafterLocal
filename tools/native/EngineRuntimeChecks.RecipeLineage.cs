#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void RecipeLineage()
 {
        GeneratedItemData Entry(string id, params string[] parents) { var d = GeneratedItemData.Placeholder(); d.Id = id; d.Name = id; d.RecipeMeta.WorldId = "w"; d.RecipeMeta.ParentIdentities = parents; return d; }
        var a = Entry("a", "generated:b", "generated:c"); var b = Entry("b", "generated:a"); var c = Entry("c", "generated:b");
        var native = Entry("native", "item:Terraria/Wood:9"); native.ParentA = "Wood";
        var nativeRow = RecipeLineageView.Build(native, new[] { native }, false).Single();
        Equal(9, nativeRow.NativeType, "recursive native ancestor uses exact identity icon");
        Equal("item:Terraria/Wood:9", nativeRow.Identity, "ingredient stock retains exact identity");
        Equal("native", nativeRow.ViaName, "lineage keeps the edge source for branching provenance");
        var foreign = Entry("foreign", "generated:a"); foreign.RecipeMeta.WorldId = "other";
        var rows = RecipeLineageView.Build(a, new[] { a,b,c,foreign }, false);
        Equal(4, rows.Count, "diamond and cycle have bounded explicit links");
        Equal(2, rows.Count(r => r.Repeated), "repeat stops expansion");
        Equal(true, RecipeLineageView.Build(a, new[] { a,b,c,foreign }, true).All(r => r.Id != "foreign"), "world fence");
        Equal(true, RecipeLineageView.Build(a, new[] { a }, false).All(r => r.Unknown), "unknown ancestors never fabricated");
 }
}
