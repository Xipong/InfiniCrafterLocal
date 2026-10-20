#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private readonly HashSet<string> _journalFavorites = new(StringComparer.Ordinal);
    private static string JournalKey(string id) => Main.worldID + ":" + id;
    internal bool IsJournalFavorite(string id) => _journalFavorites.Contains(JournalKey(id));
    internal void ToggleJournalFavorite(string id)
    {
        string key = JournalKey(id);
        if (!_journalFavorites.Remove(key) && _journalFavorites.Count < 4096) _journalFavorites.Add(key);
    }
    private void SaveJournal(TagCompound tag) => tag["infiniJournalFavorites"] = _journalFavorites.OrderBy(x => x, StringComparer.Ordinal).ToList();
    private void LoadJournal(TagCompound tag)
    {
        _journalFavorites.Clear();
        foreach (string key in tag.GetList<string>("infiniJournalFavorites").Take(4096))
            if (!string.IsNullOrWhiteSpace(key) && key.Length <= 160) _journalFavorites.Add(key);
    }
}
