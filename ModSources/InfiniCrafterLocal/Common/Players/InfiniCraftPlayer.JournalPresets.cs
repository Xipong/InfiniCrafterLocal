#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

internal sealed record JournalFilterPreset(string Query, bool Favorites, bool Unread,
    RecipeJournalView.EffectFilter Effect, string Ingredient, RecipeJournalView.SortOrder Sort)
{
    internal bool Valid => Query.Length <= 80 && Ingredient.Length <= 120
        && Enum.IsDefined(Effect) && Enum.IsDefined(Sort);
    internal TagCompound Save() => new() { ["query"] = Query, ["favorites"] = Favorites ? 1 : 0, ["unread"] = Unread ? 1 : 0,
        ["effect"] = (int)Effect, ["ingredient"] = Ingredient, ["sort"] = (int)Sort };
    internal static JournalFilterPreset Read(TagCompound tag) => new(tag.GetString("query"), tag.GetInt("favorites") == 1,
        tag.GetInt("unread") == 1, (RecipeJournalView.EffectFilter)tag.GetInt("effect"), tag.GetString("ingredient"),
        (RecipeJournalView.SortOrder)tag.GetInt("sort"));
}

public sealed partial class InfiniCraftPlayer
{
    private readonly Dictionary<string, JournalFilterPreset> _journalPresets = new(StringComparer.Ordinal);
    internal JournalFilterPreset? JournalPreset(int slot) => slot is >= 0 and < 6
        ? _journalPresets.GetValueOrDefault(JournalKey("preset:" + slot)) : null;
    internal bool SaveJournalPreset(int slot, JournalFilterPreset? preset)
    {
        if (slot is < 0 or >= 6 || preset is { Valid: false }) return false;
        string key = JournalKey("preset:" + slot);
        if (preset is null) return _journalPresets.Remove(key);
        if (!_journalPresets.ContainsKey(key) && _journalPresets.Count >= 256) return false;
        _journalPresets[key] = preset; return true;
    }
    private void SaveJournalPresets(TagCompound tag) => tag["infiniJournalPresets"] = _journalPresets
        .OrderBy(row => row.Key, StringComparer.Ordinal).Select(row => new TagCompound {
            ["key"] = row.Key, ["filter"] = row.Value.Save() }).ToList();
    private void LoadJournalPresets(TagCompound tag)
    {
        _journalPresets.Clear();
        foreach (var row in tag.GetList<TagCompound>("infiniJournalPresets").Take(256))
        {
            string key = row.GetString("key"); var preset = JournalFilterPreset.Read(row.GetCompound("filter"));
            if (key.Length is > 0 and <= 160 && preset.Valid) _journalPresets[key] = preset;
        }
    }
}
