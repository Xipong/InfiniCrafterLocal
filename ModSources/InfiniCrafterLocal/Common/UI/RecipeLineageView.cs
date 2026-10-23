#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.UI;

internal static class RecipeLineageView
{
    internal readonly record struct Row(string Id, string Name, int Depth, bool Repeated, bool Unknown);
    internal static IReadOnlyList<Row> Build(GeneratedItemData root, IEnumerable<GeneratedItemData> known, bool descendants)
    {
        var items = RecipeJournalView.Entries(known, root.RecipeMeta.WorldId, "", _ => false, false)
            .ToDictionary(d => d.Id, StringComparer.Ordinal);
        var result = new List<Row>(); var seen = new HashSet<string>(StringComparer.Ordinal) { root.Id };
        var queue = new Queue<(GeneratedItemData Item, int Depth)>(); queue.Enqueue((root, 0));
        while (queue.Count > 0 && result.Count < 256)
        {
            var (item, depth) = queue.Dequeue();
            if (depth >= 32) continue;
            if (descendants)
            {
                foreach (var child in items.Values.Where(d => d.RecipeMeta.ParentIdentities.Contains("generated:" + item.Id, StringComparer.Ordinal))
                    .OrderBy(d => d.Name, StringComparer.CurrentCultureIgnoreCase).ThenBy(d => d.Id, StringComparer.Ordinal)) Add(child, depth + 1);
            }
            else
            {
                for (int index = 0; index < item.RecipeMeta.ParentIdentities.Length && result.Count < 256; index++)
                {
                    string identity = item.RecipeMeta.ParentIdentities[index];
                    if (identity.StartsWith("generated:", StringComparison.Ordinal) && items.TryGetValue(identity[10..], out var parent)) Add(parent, depth + 1);
                    else result.Add(new("", index == 0 ? item.ParentA : item.ParentB, depth + 1, false, identity.StartsWith("generated:", StringComparison.Ordinal)));
                }
            }
        }
        return result;
        void Add(GeneratedItemData next, int depth)
        {
            if (result.Count >= 256) return;
            bool repeated = !seen.Add(next.Id);
            result.Add(new(next.Id, next.Name, depth, repeated, false));
            if (!repeated) queue.Enqueue((next, depth));
        }
    }
}
