#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private readonly Dictionary<string, (int Quantity, bool Storage)> _objectives = new(StringComparer.Ordinal);
    internal (int Quantity, bool Storage) JournalObjective(string id)
        => _objectives.GetValueOrDefault(JournalKey(id), (1, false));
    internal void SetJournalObjective(string id, int quantity, bool storage)
    {
        if (string.IsNullOrWhiteSpace(id) || id.Length > 120) return;
        string key = JournalKey(id);
        if (!_objectives.ContainsKey(key) && _objectives.Count >= 4096) return;
        _objectives[key] = (Math.Clamp(quantity, 1, 999), storage);
    }
    private void SaveObjectives(TagCompound tag)
        => tag["infiniObjectives"] = _objectives.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => new TagCompound { ["key"] = p.Key, ["quantity"] = p.Value.Quantity, ["storage"] = p.Value.Storage ? 1 : 0 }).ToList();
    private void LoadObjectives(TagCompound tag)
    {
        _objectives.Clear();
        foreach (var row in tag.GetList<TagCompound>("infiniObjectives").Take(4096))
        {
            string key = row.GetString("key"); int quantity = row.GetInt("quantity");
            if (key.Length is > 0 and <= 160 && quantity is >= 1 and <= 999)
                _objectives[key] = (quantity, row.GetInt("storage") == 1);
        }
    }
}
