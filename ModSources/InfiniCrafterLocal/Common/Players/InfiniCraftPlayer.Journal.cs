#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private readonly Dictionary<string, long> _journalVisits = new(StringComparer.Ordinal);
    private long _journalVisitSequence;
    internal long JournalLastVisited(string id) => _journalVisits.GetValueOrDefault(JournalKey(id));
    internal void VisitJournalRecipe(string id)
    {
        if (id.Length is 0 or > 120) return;
        string key = JournalKey(id);
        if (_journalVisits.Count >= 4096 && !_journalVisits.ContainsKey(key))
            _journalVisits.Remove(_journalVisits.OrderBy(p => p.Value).ThenBy(p => p.Key, StringComparer.Ordinal).First().Key);
        _journalVisits[key] = ++_journalVisitSequence;
    }
    private readonly Dictionary<string, string> _journalNotes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _journalCollections = new(StringComparer.Ordinal);
    internal string JournalNote(string id) => _journalNotes.GetValueOrDefault(JournalKey(id), "");
    internal int JournalCollection(string id) => _journalCollections.GetValueOrDefault(JournalKey(id));
    internal void SetJournalNote(string id, string value)
    {
        if (id.Length is 0 or > 120) return;
        string key = JournalKey(id); value = (value ?? "").Replace('\r', ' ').Replace('\n', ' ');
        if (value.Length > 240) value = value[..240];
        if (value.Length == 0) _journalNotes.Remove(key);
        else if (_journalNotes.ContainsKey(key) || _journalNotes.Count < 4096) _journalNotes[key] = value;
    }
    internal void SetJournalCollection(string id, int value)
    {
        if (id.Length is 0 or > 120 || value is < 0 or > 4) return;
        string key = JournalKey(id);
        if (value == 0) _journalCollections.Remove(key);
        else if (_journalCollections.ContainsKey(key) || _journalCollections.Count < 4096) _journalCollections[key] = value;
    }
    private readonly HashSet<string> _journalPins = new(StringComparer.Ordinal);
    private readonly HashSet<string> _journalFavorites = new(StringComparer.Ordinal);
    private static string JournalKey(string id) => Main.worldID + ":" + id;
    internal bool IsJournalFavorite(string id) => _journalFavorites.Contains(JournalKey(id));
    internal void SetJournalFavorite(string id, bool favorite)
    {
        if (id.Length is 0 or > 120) return;
        string key = JournalKey(id);
        if (!favorite) _journalFavorites.Remove(key);
        else if (_journalFavorites.Count < 4096) _journalFavorites.Add(key);
    }
    internal void ToggleJournalFavorite(string id)
    {
        string key = JournalKey(id);
        if (!_journalFavorites.Remove(key) && _journalFavorites.Count < 4096) _journalFavorites.Add(key);
    }
    internal bool IsJournalPinned(string id) => _journalPins.Contains(JournalKey(id));
    internal bool ToggleJournalPin(string id)
    {
        if (string.IsNullOrWhiteSpace(id) || id.Length > 120) return false;
        string key = JournalKey(id);
        if (_journalPins.Remove(key)) return true;
        if (_journalPins.Count >= 4096 || _journalPins.Count(k => k.StartsWith(Main.worldID + ":", StringComparison.Ordinal)) >= 3) return false;
        return _journalPins.Add(key);
    }
    private void SaveJournal(TagCompound tag)
    {
        SaveJournalPresets(tag);
        SaveObjectives(tag);
        tag["infiniJournalVisits"] = _journalVisits.OrderBy(p => p.Value)
            .Select(p => new TagCompound { ["key"] = p.Key, ["order"] = p.Value }).ToList();
        tag["infiniJournalNotes"] = _journalNotes.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => new TagCompound { ["key"] = p.Key, ["text"] = p.Value }).ToList();
        tag["infiniJournalCollections"] = _journalCollections.OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => new TagCompound { ["key"] = p.Key, ["collection"] = p.Value }).ToList();
        tag["infiniJournalFavorites"] = _journalFavorites.OrderBy(x => x, StringComparer.Ordinal).ToList();
        tag["infiniJournalPins"] = _journalPins.OrderBy(x => x, StringComparer.Ordinal).ToList();
    }
    private void LoadJournal(TagCompound tag)
    {
        LoadJournalPresets(tag);
        LoadObjectives(tag);
        _journalVisits.Clear(); _journalVisitSequence = 0;
        foreach (var row in tag.GetList<TagCompound>("infiniJournalVisits").Take(4096))
        {
            string key = row.GetString("key"); long order = row.GetLong("order");
            if (key.Length is > 0 and <= 160 && order is > 0 and < long.MaxValue / 2)
            { _journalVisits[key] = order; _journalVisitSequence = Math.Max(_journalVisitSequence, order); }
        }
        _journalNotes.Clear(); _journalCollections.Clear();
        foreach (var row in tag.GetList<TagCompound>("infiniJournalNotes").Take(4096))
        {
            string key = row.GetString("key"), text = row.GetString("text");
            if (key.Length is > 0 and <= 160 && text.Length is > 0 and <= 240) _journalNotes[key] = text.Replace('\n', ' ').Replace('\r', ' ');
        }
        foreach (var row in tag.GetList<TagCompound>("infiniJournalCollections").Take(4096))
        {
            string key = row.GetString("key"); int value = row.GetInt("collection");
            if (key.Length is > 0 and <= 160 && value is >= 1 and <= 4) _journalCollections[key] = value;
        }
        _journalFavorites.Clear(); _journalPins.Clear();
        foreach (string key in tag.GetList<string>("infiniJournalPins").Take(4096))
            if (!string.IsNullOrWhiteSpace(key) && key.Length <= 160) _journalPins.Add(key);
        foreach (string key in tag.GetList<string>("infiniJournalFavorites").Take(4096))
            if (!string.IsNullOrWhiteSpace(key) && key.Length <= 160) _journalFavorites.Add(key);
    }
}
