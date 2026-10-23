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
    internal enum EffectFilter { All, Healing, Mining, Summon, Mobility }

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
            EffectFilter.Mobility => effects.Any(e => e.MobilityMode.Length > 0 || e.GeneratedBuff is { } b
                    && (b.MovementSpeed != 0 || b.JumpBoost != 0))
                || program.Entities.Any(e => e.Events.Any(a => a.ActionCode == RuntimeEventActionCode.MoveOwner
                    || a.ActionCode == RuntimeEventActionCode.Pull && a.Mode == "owner_to_target")),
            _ => false,
        };
    }

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
