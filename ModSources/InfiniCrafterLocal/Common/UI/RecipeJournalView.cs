#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Globalization;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.UI;

// Read-only discovery projection. Names never resolve identities or reveal unknown recipes.
internal static class RecipeJournalView
{
    internal enum SortOrder { Name, ShallowFirst, DeepFirst, Recent }

    internal static GeneratedItemData[] Sort(GeneratedItemData[] entries, SortOrder order, Func<string, bool> favorite, Func<string, long>? visited = null)
        => entries.OrderByDescending(d => favorite(d.Id))
            .ThenBy(d => order == SortOrder.ShallowFirst ? (long)d.RecipeMeta.GenerationDepth
                : order == SortOrder.DeepFirst ? -(long)d.RecipeMeta.GenerationDepth
                : order == SortOrder.Recent ? -(visited?.Invoke(d.Id) ?? 0) : 0L)
            .ThenBy(d => d.Name, StringComparer.CurrentCultureIgnoreCase)
            .ThenBy(d => d.Id, StringComparer.Ordinal).ToArray();

    internal enum EffectFilter { All, Healing, Mining, Summon, Mobility, Equipment, Placement, Mana }

    internal static GeneratedItemData[] Children(GeneratedItemData parent, IEnumerable<GeneratedItemData> known)
        => Entries(known, parent.RecipeMeta.WorldId, "", _ => false, false)
            .Where(d => d.RecipeMeta.ParentIdentities?.Contains("generated:" + parent.Id, StringComparer.Ordinal) == true).ToArray();

    internal static bool MatchesEffect(GeneratedItemData data, EffectFilter filter)
    {
        var program = data.RuntimeProgram;
        var effects = new List<IItemEffectsSpec>();
        foreach (var binding in program.Bindings)
            if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects)
            {
                var selected = binding.UsePolicy.Action.EffectGroupId;
                if (selected is null) effects.Add(data.Gameplay);
                else if (program.TryGetEffectGroup(selected) is { } group) effects.Add(group);
            }
        if (program.TryGetEffectGroup(program.HeldEffectGroupId ?? "") is { } held) effects.Add(held);
        foreach (var source in program.Entities)
        foreach (var action in source.Events)
            if (action.ActionCode == RuntimeEventActionCode.ApplyGeneratedBuff
                && program.TryGetEffectGroup(action.EffectGroupId ?? "") is { } reactive) effects.Add(reactive);
        return filter switch
        {
            EffectFilter.All => true,
            EffectFilter.Healing => effects.Any(e => e.HealLife > 0 || e.GeneratedBuff?.LifeRegen > 0)
                || program.Entities.Any(e => e.Events.Any(a => a.ActionCode == RuntimeEventActionCode.HealOwner)),
            EffectFilter.Mining => data.Gameplay.PickPower > 0 || data.Gameplay.AxePower > 0 || data.Gameplay.HammerPower > 0
                || effects.Any(e => e.GeneratedBuff is { MiningSpeedMultiplier: > 1f }),
            EffectFilter.Summon => program.Entities.Any(e => e.IsProjectileEntity && e.Damage.Enabled
                && e.Damage.DamageClass is "summon" or "summon_melee_speed" or "magic_summon_hybrid"),
            EffectFilter.Equipment => data.Accessory.Enabled || data.Armor.Enabled,
            EffectFilter.Placement => program.Bindings.Any(b => b.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem),
            EffectFilter.Mana => effects.Any(e => e.HealMana > 0 || e.GeneratedBuff is { ManaRegen: > 0 }),
            EffectFilter.Mobility => effects.Any(e => e.MobilityMode.Length > 0 || e.GeneratedBuff is { } b
                    && (b.MovementSpeed != 0 || b.JumpBoost != 0))
                || program.Entities.Any(e => e.Events.Any(a => a.ActionCode == RuntimeEventActionCode.MoveOwner
                    || a.ActionCode == RuntimeEventActionCode.Pull && a.Mode == "owner_to_target")),
            _ => false,
        };
    }

    internal static GeneratedItemData[] Entries(IEnumerable<GeneratedItemData> records, string world,
        string query, Func<string, bool> favorite, bool onlyFavorites, Func<string, string>? note = null, Func<string, int>? collection = null)
        => records.Where(d => d is not null && d.RecipeMeta.WorldScoped && d.RecipeMeta.WorldId == world
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(d) && d.Id != "placeholder"
                && (!onlyFavorites || favorite(d.Id))
                && MatchesQuery(d, query, note?.Invoke(d.Id) ?? "", collection?.Invoke(d.Id) ?? 0))
            .GroupBy(d => d.Id, StringComparer.Ordinal).Select(g => g.First())
            .OrderByDescending(d => favorite(d.Id)).ThenBy(d => d.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();

    internal static bool MatchesQuery(GeneratedItemData data, string query, string note = "", int collection = 0)
    {
        foreach (string raw in ParseQuery(query ?? "").Terms)
        {
            bool excluded = raw.StartsWith('-') && raw.Length > 1;
            string term = excluded ? raw[1..] : raw;
            int colon = term.IndexOf(':');
            string field = colon >= 0 ? term[..colon].ToLowerInvariant() : "";
            string value = colon >= 0 ? term[(colon + 1)..] : term;
            bool Contains(string? text) => (text ?? "").Contains(value, StringComparison.OrdinalIgnoreCase);
            bool matches = value.Length > 0 && (field switch {
                "name" => Contains(data.Name), "parent" => Contains(data.ParentA) || Contains(data.ParentB),
                "tag" => data.Tags.Any(Contains), "kind" => Contains(data.Category), "id" => Contains(data.Id),
                "note" => Contains(note),
                "collection" => value.Equals(collection switch { 1 => "combat", 2 => "exploration", 3 => "building", 4 => "experiments", _ => "none" }, StringComparison.OrdinalIgnoreCase),
                "depth" => DepthMatches(data.RecipeMeta.GenerationDepth, value),
                "" => Contains(data.Name) || Contains(data.ParentA) || Contains(data.ParentB),
                _ => new[] { data.Name, data.ParentA, data.ParentB }.Any(text => (text ?? "").Contains(term, StringComparison.OrdinalIgnoreCase)),
            });
            if (excluded ? matches : !matches) return false;
        }
        return true;
    }
    private static bool DepthMatches(int depth, string value)
        => TryDepth(value, out string op, out int n)
            && (op switch { ">=" => depth >= n, "<=" => depth <= n, ">" => depth > n, "<" => depth < n, _ => depth == n });

    private static bool TryDepth(string value, out string op, out int n)
    {
        op = value.StartsWith(">=") || value.StartsWith("<=") ? value[..2]
            : value.StartsWith('>') || value.StartsWith('<') || value.StartsWith('=') ? value[..1] : "";
        return int.TryParse(value[op.Length..], NumberStyles.None, CultureInfo.InvariantCulture, out n);
    }

    internal readonly record struct SearchQuery(string[] Terms, bool UnclosedQuote, bool Truncated);
    internal static SearchQuery ParseQuery(string query)
    {
        var words = new List<string>(); var word = new StringBuilder(); bool quote = false;
        for (int index = 0; index < Math.Min(240, query.Length); index++)
        {
            char c = query[index];
            if (c == '\\' && index + 1 < Math.Min(240, query.Length) && query[index + 1] == '"')
            { word.Append('"'); index++; continue; }
            if (c == '"') { quote = !quote; continue; }
            if (char.IsWhiteSpace(c) && !quote)
            { if (word.Length > 0) { words.Add(word.ToString()); word.Clear(); } }
            else word.Append(c);
        }
        if (word.Length > 0) words.Add(word.ToString());
        return new(words.ToArray(), quote, query.Length > 240);
    }

    internal static string QueryIssue(string query)
    {
        var parsed = ParseQuery(query);
        if (parsed.Truncated) return "SearchTooLong";
        if (parsed.UnclosedQuote) return "SearchUnclosedQuote";
        foreach (string raw in parsed.Terms)
        {
            string term = raw.StartsWith('-') ? raw[1..] : raw;
            if (term.StartsWith("depth:", StringComparison.OrdinalIgnoreCase) && !TryDepth(term[6..], out _, out _)) return "SearchDepthInvalid";
        }
        return "";
    }

    internal static int NativeParentType(GeneratedItemData child, int index)
    {
        var identities = child.RecipeMeta.ParentIdentities;
        if (identities is null || index < 0 || index >= identities.Length) return 0;
        string[] parts = identities[index].Split(':');
        string name, typeText;
        if (parts.Length == 3 && parts[0] == "item" && parts[1].StartsWith("Terraria/", StringComparison.Ordinal))
        { name = parts[1][9..]; typeText = parts[2]; }
        else if (parts.Length == 4 && parts[0] == "item" && parts[1] == "Terraria")
        { name = parts[2]; typeText = parts[3]; }
        else return 0;
        if (!int.TryParse(typeText, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out int type)
            || type <= 0 || type >= Terraria.ID.ItemID.Count
            || !Terraria.ID.ItemID.Search.TryGetId(name, out int named) || named != type) return 0;
        return type;
    }

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

    internal static (Rectangle Back, Rectangle Save) DetailControls(Rectangle area)
    {
        int x = area.X + 12, width = Math.Max(0, area.Width - 24);
        int saveWidth = Math.Min(118, Math.Max(0, (width - 6) / 2));
        int height = Math.Min(26, Math.Max(0, area.Height - 20));
        return (new Rectangle(x, area.Y + 10, Math.Min(88, Math.Max(0, width - saveWidth - 6)), height),
            new Rectangle(area.Right - 12 - saveWidth, area.Y + 10, saveWidth, height));
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
        int top = Math.Min(120, Math.Max(0, h - footer));
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
