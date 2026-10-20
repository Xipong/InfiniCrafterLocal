#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.UI;

// Read-only discovery projection. Names never resolve identities or reveal unknown recipes.
internal static class RecipeJournalView
{
    internal static GeneratedItemData[] Entries(IEnumerable<GeneratedItemData> records, string world,
        string query, Func<string, bool> favorite, bool onlyFavorites)
        => records.Where(d => d is not null && d.RecipeMeta.WorldScoped && d.RecipeMeta.WorldId == world
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(d) && d.Id != "placeholder"
                && (!onlyFavorites || favorite(d.Id))
                && (string.IsNullOrWhiteSpace(query) || new[] { d.Name, d.ParentA, d.ParentB }
                    .Any(text => (text ?? "").Contains(query.Trim(), StringComparison.OrdinalIgnoreCase))))
            .GroupBy(d => d.Id, StringComparer.Ordinal).Select(g => g.First())
            .OrderByDescending(d => favorite(d.Id)).ThenBy(d => d.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();

    internal static GeneratedItemData? Parent(GeneratedItemData child, int index, IEnumerable<GeneratedItemData> known)
    {
        string[] identities = child.RecipeMeta.ParentIdentities;
        if (identities is null || index < 0 || index >= identities.Length) return null;
        string identity = identities[index];
        if (!identity.StartsWith("generated:", StringComparison.Ordinal)) return null;
        string id = identity[10..];
        return known.FirstOrDefault(d => d.Id == id && d.RecipeMeta.WorldScoped
            && !GeneratedItemData.IsPlayerSaveReferenceOnly(d) && d.RecipeMeta.WorldId == child.RecipeMeta.WorldId);
    }

    internal readonly record struct Layout(Rectangle Book, Rectangle List, Rectangle Detail, int Rows);
    internal static Layout Bounds(int width, int height)
    {
        int w = Math.Max(240, Math.Min(1040, width - 32));
        int h = Math.Max(240, Math.Min(650, height - 32));
        var book = new Rectangle(Math.Max(0, (width - w) / 2), Math.Max(0, (height - h) / 2), w, h);
        bool narrow = w < 700;
        int listWidth = narrow ? w - 40 : Math.Clamp(w / 3, 230, 330);
        int listHeight = narrow ? Math.Min(160, (h - 142) / 2) : h - 148;
        var list = new Rectangle(book.X + 20, book.Y + 98, listWidth, listHeight);
        var detail = narrow
            ? new Rectangle(book.X + 20, list.Bottom + 12, w - 40, Math.Max(60, book.Bottom - list.Bottom - 62))
            : new Rectangle(list.Right + 24, list.Y, book.Right - list.Right - 44, list.Height);
        return new(book, list, detail, Math.Max(1, list.Height / 58));
    }
}
