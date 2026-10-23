#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader.IO;
namespace InfiniCrafterLocal.Common.Players;
public sealed partial class InfiniCraftPlayer
{
    internal readonly record struct CraftHistoryEntry(string World, long UtcTicks, int Lane, string Recipe, CraftLaneOutcome Outcome);
    private readonly List<CraftHistoryEntry> _craftHistory = new();
    internal IReadOnlyList<CraftHistoryEntry> CraftHistory => _craftHistory;
    private void RecordCraftHistory(int lane, CraftLaneOutcome outcome)
    {
        if (outcome.Kind == CraftLaneOutcomeKind.None || outcome == _craftLaneOutcomes[lane]) return;
        _craftHistory.Insert(0, new(Main.worldID.ToString(), DateTime.UtcNow.Ticks, lane, BoundedHistoryText(CraftLaneLabel(lane)), outcome));
        if (_craftHistory.Count > 64) _craftHistory.RemoveRange(64, _craftHistory.Count - 64);
    }
    private static string BoundedHistoryText(string value)
    { value = (value ?? "").Replace('\r', ' ').Replace('\n', ' '); return value[..Math.Min(240, value.Length)]; }
    private void SaveCraftHistory(TagCompound tag)
        => tag["infiniCraftHistoryV1"] = _craftHistory.Take(64).Select(row => new TagCompound {
            ["world"] = row.World, ["utc"] = row.UtcTicks, ["lane"] = row.Lane, ["recipe"] = row.Recipe,
            ["kind"] = (int)row.Outcome.Kind, ["message"] = row.Outcome.Message, ["materials"] = (int)row.Outcome.Materials
        }).ToList();
    private void LoadCraftHistory(TagCompound tag)
    {
        _craftHistory.Clear();
        System.Collections.Generic.IList<TagCompound> rows;
        try { rows = tag.GetList<TagCompound>("infiniCraftHistoryV1"); }
        catch (Exception) { return; } // Corrupt optional presentation cannot block durable item recovery.
        foreach (var row in rows.Take(64))
        {
            try {
                int kind = row.GetInt("kind"), lane = row.GetInt("lane"), materials = row.GetInt("materials");
                long utc = row.GetLong("utc"); string world = row.GetString("world");
                if (kind < 1 || kind > 4 || lane < 0 || lane > 2 || materials < 0 || materials > 2
                    || utc < DateTime.MinValue.Ticks || utc > DateTime.MaxValue.Ticks || world.Length > 80) continue;
                _craftHistory.Add(new(world, utc, lane, BoundedHistoryText(row.GetString("recipe")),
                    new((CraftLaneOutcomeKind)kind, BoundedHistoryText(row.GetString("message")), (CraftLaneMaterialDisposition)materials)));
            } catch (Exception) { /* Malformed presentation rows never affect escrow recovery. */ }
        }
    }
}
