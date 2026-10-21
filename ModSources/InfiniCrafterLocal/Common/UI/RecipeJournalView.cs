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

    internal readonly record struct Layout(Rectangle Book, Rectangle List, Rectangle Detail, int Rows, int Columns);
    internal static Layout Bounds(int width, int height)
    {
        // These coordinates are UI-space pixels: Terraria has already applied UI scale.
        // Never enforce a minimum book size larger than the actual viewport.
        width = Math.Max(0, width);
        height = Math.Max(0, height);
        int margin = Math.Min(16, Math.Min(width, height) / 16);
        int w = Math.Min(920, width - margin * 2);
        int h = Math.Min(560, height - margin * 2);
        var book = new Rectangle((width - w) / 2, (height - h) / 2, w, h);
        int inset = Math.Min(12, w / 8);
        int pageWidth = Math.Max(0, w - inset * 2);
        int footer = Math.Min(32, h / 6);
        int top = Math.Min(88, Math.Max(0, h - footer));
        int contentHeight = Math.Max(0, h - top - footer);
        bool narrow = w < 700;
        int gutter = Math.Min(12, narrow ? contentHeight : pageWidth);
        int listWidth = narrow ? pageWidth : pageWidth * 42 / 100 / 52 * 52;
        // A short viewport must not paint a partial row over the detail page.
        int listHeight = narrow
            ? Math.Min(104, Math.Max(contentHeight >= 116 ? 52 : 0, contentHeight / 3 / 52 * 52))
            : contentHeight;
        var list = new Rectangle(book.X + inset, book.Y + top, listWidth, listHeight);
        var detail = narrow
            ? new Rectangle(list.X, list.Bottom + gutter, pageWidth, Math.Max(0, contentHeight - listHeight - gutter))
            : new Rectangle(list.Right + gutter, list.Y, Math.Max(0, pageWidth - listWidth - gutter), contentHeight);
        return new(book, list, detail, list.Height / 52, list.Width / 52);
    }
}
