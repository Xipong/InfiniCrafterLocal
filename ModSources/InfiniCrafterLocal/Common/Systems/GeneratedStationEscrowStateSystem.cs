#nullable enable
using InfiniCrafterLocal.Common.Players;
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Canonical world-owned multiplayer station escrow state and exactly-once outcome
/// journal. A stable client token survives player-object recreation. Outcomes are
/// never evicted: once capacity is reached, new operations are rejected before any
/// mutation, preserving replay safety.
/// </summary>
public sealed class GeneratedStationEscrowStateSystem : ModSystem
{
    private const string OwnersSaveKey = "infiniStationEscrowOwnersV1";
    private const string OutcomesSaveKey = "infiniStationEscrowOutcomesV1";
    private const string CraftTransactionsSaveKey = "infiniStationCraftTransactionsV1";
    private const int MaxOwners = 256;
    private const int MaxOutcomes = 65536;
    private const int MaxCraftTransactions = 65536;
    private const int SlotCount = 6;

    internal readonly record struct ReplayOutcome(byte Action, int Index, bool Success, string Message);
    internal readonly record struct CraftReplayOutcome(bool Success, string ItemName, string Message);

    private sealed class OwnerState
    {
        public Item[] Slots { get; init; } = NewAirSlots();
    }

    private sealed class CraftTransactionState
    {
        public int LaneIndex { get; init; }
        public bool Pending { get; set; }
        public bool Success { get; set; }
        public string ItemName { get; set; } = "";
        public string Message { get; set; } = "";
    }

    private static readonly Dictionary<string, OwnerState> Owners = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, ReplayOutcome> Outcomes = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, CraftTransactionState> CraftTransactions = new(StringComparer.Ordinal);

    public override void ClearWorld()
    {
        Owners.Clear();
        Outcomes.Clear();
        CraftTransactions.Clear();
    }

    public override void SaveWorldData(TagCompound tag)
    {
        tag[OwnersSaveKey] = Owners.OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair =>
        {
            var slots = new List<TagCompound>();
            for (int index = 0; index < SlotCount; index++)
            {
                Item item = pair.Value.Slots[index];
                if (item is null || item.IsAir || item.stack <= 0)
                    continue;
                slots.Add(new TagCompound
                {
                    ["index"] = index,
                    ["item"] = ItemIO.Save(item),
                });
            }
            return new TagCompound
            {
                ["clientId"] = pair.Key,
                ["slots"] = slots,
            };
        }).ToList();
        tag[OutcomesSaveKey] = Outcomes.OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair => new TagCompound
        {
            ["key"] = pair.Key,
            ["action"] = (int)pair.Value.Action,
            ["index"] = pair.Value.Index,
            ["success"] = pair.Value.Success,
            ["message"] = pair.Value.Message ?? "",
        }).ToList();
        tag[CraftTransactionsSaveKey] = CraftTransactions.OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair => new TagCompound
        {
            ["key"] = pair.Key,
            ["laneIndex"] = pair.Value.LaneIndex,
            ["pending"] = pair.Value.Pending,
            ["success"] = pair.Value.Success,
            ["itemName"] = pair.Value.ItemName ?? "",
            ["message"] = pair.Value.Message ?? "",
        }).ToList();
    }

    public override void LoadWorldData(TagCompound tag)
    {
        ClearWorld();
        foreach (TagCompound row in tag.GetList<TagCompound>(OwnersSaveKey).Take(MaxOwners))
        {
            string clientId = NormalizeClientId(row.GetString("clientId"));
            if (clientId.Length == 0)
                continue;
            Item[] slots = NewAirSlots();
            foreach (TagCompound slotRow in row.GetList<TagCompound>("slots").Take(SlotCount))
            {
                int index = slotRow.GetInt("index");
                if (index is < 0 or >= SlotCount || !slotRow.ContainsKey("item"))
                    continue;
                try
                {
                    Item item = ItemIO.Load(slotRow.GetCompound("item"));
                    if (item is not null && !item.IsAir && item.stack > 0)
                        slots[index] = item.Clone();
                }
                catch { }
            }
            Owners[clientId] = new OwnerState { Slots = slots };
        }
        foreach (TagCompound row in tag.GetList<TagCompound>(OutcomesSaveKey).Take(MaxOutcomes))
        {
            string key = (row.GetString("key") ?? "").Trim();
            int action = row.GetInt("action");
            int index = row.GetInt("index");
            string message = (row.GetString("message") ?? "");
            if (!ValidOutcomeKey(key) || action is < 1 or > byte.MaxValue || message.Length > 500)
                continue;
            Outcomes[key] = new ReplayOutcome((byte)action, index, row.GetBool("success"), message);
        }
        foreach (TagCompound row in tag.GetList<TagCompound>(CraftTransactionsSaveKey).Take(MaxCraftTransactions))
        {
            string key = (row.GetString("key") ?? "").Trim().ToLowerInvariant();
            int laneIndex = row.GetInt("laneIndex");
            string itemName = (row.GetString("itemName") ?? "");
            string message = (row.GetString("message") ?? "");
            if (!ValidOutcomeKey(key) || laneIndex is < 0 or > 2 || itemName.Length > 120 || message.Length > 500)
                continue;
            bool wasPending = row.GetBool("pending");
            CraftTransactions[key] = new CraftTransactionState
            {
                LaneIndex = laneIndex,
                Pending = false,
                Success = wasPending ? false : row.GetBool("success"),
                ItemName = wasPending ? "" : itemName,
                Message = wasPending ? "server restarted; inputs remain in station" : message,
            };
        }
    }

    internal static bool RestoreOwnerState(string clientId, InfiniCraftPlayer player)
    {
        string key = NormalizeClientId(clientId);
        if (key.Length == 0 || player is null)
            return false;
        if (Owners.TryGetValue(key, out OwnerState? state))
        {
            player.RestoreServerStationEscrowSlots(state.Slots);
            return true;
        }
        if (Owners.Count >= MaxOwners)
            return false;
        CaptureOwnerState(key, player);
        return true;
    }

    internal static void CaptureOwnerState(string clientId, InfiniCraftPlayer player)
    {
        string key = NormalizeClientId(clientId);
        if (key.Length == 0 || player is null || (!Owners.ContainsKey(key) && Owners.Count >= MaxOwners))
            return;
        Owners[key] = new OwnerState { Slots = player.SnapshotServerStationEscrowSlots() };
    }

    internal static bool CanAcceptNewOperation(string clientId, string operationId)
    {
        string key = OutcomeKey(clientId, operationId);
        return key.Length > 0 && (Outcomes.ContainsKey(key) || Outcomes.Count < MaxOutcomes);
    }

    internal static bool TryReplay(string clientId, string operationId, out ReplayOutcome outcome)
    {
        string key = OutcomeKey(clientId, operationId);
        return Outcomes.TryGetValue(key, out outcome);
    }

    internal static bool RememberOutcome(
        string clientId,
        string operationId,
        byte action,
        int index,
        bool success,
        string message)
    {
        string key = OutcomeKey(clientId, operationId);
        if (key.Length == 0)
            return false;
        if (Outcomes.TryGetValue(key, out ReplayOutcome existing))
            return existing.Action == action
                && existing.Index == index
                && existing.Success == success
                && string.Equals(existing.Message, message ?? "", StringComparison.Ordinal);
        if (Outcomes.Count >= MaxOutcomes)
            return false;
        Outcomes[key] = new ReplayOutcome(action, index, success, (message ?? "")[..Math.Min((message ?? "").Length, 500)]);
        return true;
    }

    internal static bool TryReplayCraft(string clientId, string requestId, out CraftReplayOutcome outcome)
    {
        string key = OutcomeKey(clientId, requestId);
        if (CraftTransactions.TryGetValue(key, out CraftTransactionState? state) && !state.Pending)
        {
            outcome = new CraftReplayOutcome(state.Success, state.ItemName, state.Message);
            return true;
        }
        outcome = default;
        return false;
    }

    internal static bool IsCraftPending(string clientId, string requestId)
    {
        string key = OutcomeKey(clientId, requestId);
        return CraftTransactions.TryGetValue(key, out CraftTransactionState? state) && state.Pending;
    }

    internal static bool TryBeginCraft(string clientId, string requestId, int laneIndex)
    {
        string key = OutcomeKey(clientId, requestId);
        if (key.Length == 0 || laneIndex is < 0 or > 2 || CraftTransactions.ContainsKey(key) || CraftTransactions.Count >= MaxCraftTransactions)
            return false;
        CraftTransactions[key] = new CraftTransactionState { LaneIndex = laneIndex, Pending = true };
        return true;
    }

    internal static bool CompleteCraft(
        string clientId,
        string requestId,
        bool success,
        string itemName,
        string message)
    {
        string key = OutcomeKey(clientId, requestId);
        if (!CraftTransactions.TryGetValue(key, out CraftTransactionState? state))
            return false;
        if (!state.Pending)
            return state.Success == success
                && string.Equals(state.ItemName, itemName ?? "", StringComparison.Ordinal)
                && string.Equals(state.Message, message ?? "", StringComparison.Ordinal);
        state.Pending = false;
        state.Success = success;
        state.ItemName = (itemName ?? "")[..Math.Min((itemName ?? "").Length, 120)];
        state.Message = (message ?? "")[..Math.Min((message ?? "").Length, 500)];
        return true;
    }

    internal static string NormalizeClientId(string? value)
    {
        string id = (value ?? "").Trim().ToLowerInvariant();
        return id.Length == 32 && id.All(Uri.IsHexDigit) ? id : "";
    }

    private static string OutcomeKey(string clientId, string operationId)
    {
        string owner = NormalizeClientId(clientId);
        string operation = (operationId ?? "").Trim().ToLowerInvariant();
        if (owner.Length == 0 || operation.Length != 32 || !operation.All(Uri.IsHexDigit))
            return "";
        return owner + ":" + operation;
    }

    private static bool ValidOutcomeKey(string key)
    {
        string[] parts = (key ?? "").Split(':');
        return parts.Length == 2
            && NormalizeClientId(parts[0]).Length == 32
            && parts[1].Length == 32
            && parts[1].All(Uri.IsHexDigit);
    }

    private static Item[] NewAirSlots()
    {
        var slots = new Item[SlotCount];
        for (int index = 0; index < slots.Length; index++)
        {
            slots[index] = new Item();
            slots[index].TurnToAir();
        }
        return slots;
    }
}
