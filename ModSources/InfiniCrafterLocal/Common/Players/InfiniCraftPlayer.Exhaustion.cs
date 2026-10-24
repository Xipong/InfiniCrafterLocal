#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

internal readonly record struct GeneratedItemExhaustionStatus(
    string ItemId, string DefinitionIdentity, string ItemName, int RemainingTicks);

public sealed partial class InfiniCraftPlayer
{
    // Refuse a new positive policy at capacity, never evict a live source timer.
    private const int MaxGeneratedItemExhaustionEntries = 64;
    private sealed record GeneratedItemExhaustion(
        string ItemId, string DefinitionIdentity, string ItemName, uint StartTick, int DurationTicks)
    {
        internal int Remaining(uint now)
        {
            uint elapsed = unchecked(now - StartTick);
            return elapsed >= DurationTicks ? 0 : DurationTicks - (int)elapsed;
        }
    }
    private readonly List<GeneratedItemExhaustion> _generatedItemExhaustion = new();

    internal IReadOnlyList<GeneratedItemExhaustionStatus> CaptureGeneratedItemExhaustion()
    {
        uint now = Main.GameUpdateCount;
        // Value records and read-only array wrapper: capture never advances state
        // and neither UI nor previous snapshots can mutate the owner table.
        return Array.AsReadOnly(_generatedItemExhaustion
            .Where(row => row.Remaining(now) > 0)
            .Select(row => new GeneratedItemExhaustionStatus(row.ItemId, row.DefinitionIdentity,
                row.ItemName, row.Remaining(now))).ToArray());
    }

    private bool PruneGeneratedItemExhaustion()
        => _generatedItemExhaustion.RemoveAll(row => row.Remaining(Main.GameUpdateCount) <= 0) > 0;

    private static bool TryGeneratedExhaustionSource(GeneratedItemData? source, out string identity)
    {
        identity = "";
        if (source is null || !GeneratedItemRegistryService.IsCurrentWorldData(source)
            || GeneratedItemData.IsPlayerSaveReferenceOnly(source) || string.IsNullOrWhiteSpace(source.Id)
            || string.IsNullOrWhiteSpace(source.Name)
            || Encoding.UTF8.GetByteCount(source.Id) > 256 || Encoding.UTF8.GetByteCount(source.Name) > 320)
            return false;
        identity = GeneratedItemRegistryService.DefinitionIdentity(source);
        return identity.Length == 64;
    }

    internal bool HasGeneratedItemExhaustion(GeneratedItemData source)
    {
        if (!_generatedItemExhaustion.Any(row => row.ItemId == source.Id)
            || !TryGeneratedExhaustionSource(source, out string identity)) return false;
        return _generatedItemExhaustion.Any(row => row.ItemId == source.Id && row.DefinitionIdentity == identity
            && row.Remaining(Main.GameUpdateCount) > 0);
    }

    private bool CanApplyGeneratedBuff(GeneratedBuffSpec buff, GeneratedItemData? source,
        uint? activationTick, out GeneratedItemExhaustion? start)
    {
        start = null;
        if (PruneGeneratedItemExhaustion()) CorrectGeneratedBuffPrediction();
        int duration = buff.ExhaustionTicks ?? 0;
        // Historical omission/explicit zero keeps the source-less route. All
        // item callers supply their source; one unrelated timer is not a global
        // gate on legacy calls without an authored fatigue policy.
        if (duration == 0 && (source is null
            || !_generatedItemExhaustion.Any(row => row.ItemId == source.Id))) return true;
        if (!TryGeneratedExhaustionSource(source, out string identity)) return duration == 0;
        if (_generatedItemExhaustion.Any(row => row.ItemId == source!.Id && row.DefinitionIdentity == identity)) return false;
        if (duration <= 0) return true;
        uint now = Main.GameUpdateCount, anchor = activationTick ?? now;
        uint elapsed = unchecked(now - anchor);
        if (elapsed > int.MaxValue) return false; // future/out-of-session anchor
        if (elapsed >= duration) return true; // delayed successful buff; fatigue already elapsed
        if (_generatedItemExhaustion.Count >= MaxGeneratedItemExhaustionEntries) return false;
        start = new(source!.Id, identity, source.Name, anchor, duration);
        return true;
    }

    internal void CorrectGeneratedBuffPrediction()
    {
        if (Main.netMode == NetmodeID.Server) SendGeneratedBuffState(); // includes owner
    }

    internal void ClearGeneratedItemExhaustion(bool syncNetwork = false)
    {
        bool changed = _generatedItemExhaustion.Count > 0;
        _generatedItemExhaustion.Clear();
        if (changed && syncNetwork) CorrectGeneratedBuffPrediction();
    }

    private uint? _generatedUtilityDeathTick;

    internal bool IsGeneratedUtilityActivationCurrent(uint? activationTick)
        => !activationTick.HasValue || !_generatedUtilityDeathTick.HasValue
            || unchecked(activationTick.Value - _generatedUtilityDeathTick.Value) is > 0 and <= int.MaxValue;

    internal void ClearGeneratedUtilityState(bool syncNetwork = false)
    {
        bool changed = _generatedItemExhaustion.Count > 0 || _activeGeneratedUtilityBuffs.Count > 0 || _generatedBuffTicks > 0;
        ClearGeneratedItemExhaustion();
        _activeGeneratedUtilityBuffs.Clear();
        ResetGeneratedUtilityBuffAggregate();
        if (changed && syncNetwork) CorrectGeneratedBuffPrediction();
    }

    public override void UpdateDead()
    {
        // Keep the last dead tick: queued activations from this life must not revive buffs.
        _generatedUtilityDeathTick = Main.GameUpdateCount;
        ClearGeneratedUtilityState(syncNetwork: true);
    }

    // Existing utility snapshot, no second protocol. BinaryWriter strings use
    // a 7-bit UTF8 byte count; read the count BEFORE allocating the bounded bytes.
    private static string ReadGeneratedBuffText(BinaryReader reader, int maxBytes)
    {
        int count = reader.Read7BitEncodedInt();
        if (count < 0 || count > maxBytes) throw new InvalidDataException("generated utility string byte limit");
        byte[] bytes = reader.ReadBytes(count);
        if (bytes.Length != count) throw new EndOfStreamException();
        return new UTF8Encoding(false, true).GetString(bytes);
    }

    private void WriteGeneratedItemExhaustion(BinaryWriter writer)
    {
        var rows = CaptureGeneratedItemExhaustion();
        writer.Write((byte)rows.Count);
        foreach (var row in rows)
        {
            writer.Write(row.ItemId); writer.Write(row.DefinitionIdentity);
            writer.Write(row.ItemName); writer.Write(row.RemainingTicks);
        }
    }
    private static List<GeneratedItemExhaustion> ReadGeneratedItemExhaustion(BinaryReader reader)
    {
        int count = reader.ReadByte();
        if (count > MaxGeneratedItemExhaustionEntries) throw new InvalidDataException("generated exhaustion row limit");
        var rows = new List<GeneratedItemExhaustion>(count);
        var keys = new HashSet<(string, string)>();
        for (int i = 0; i < count; i++)
        {
            string id = ReadGeneratedBuffText(reader, 256), identity = ReadGeneratedBuffText(reader, 64), name = ReadGeneratedBuffText(reader, 320);
            int remaining = reader.ReadInt32();
            if (string.IsNullOrWhiteSpace(id) || identity.Length != 64
                || identity.Any(c => !(c is >= '0' and <= '9' or >= 'a' and <= 'f'))
                || string.IsNullOrWhiteSpace(name) || remaining is < 1 or > 21600 || !keys.Add((id, identity)))
                throw new InvalidDataException("invalid generated exhaustion row");
            rows.Add(new(id, identity, name, Main.GameUpdateCount, remaining));
        }
        return rows;
    }
}

// Retirement is explicit and world-owned. Timers never enter SaveData or an Item.
public sealed class GeneratedItemExhaustionLifecycleSystem : ModSystem
{
    private static void ClearPlayers()
    {
        foreach (Player? player in Main.player)
        {
            // Uninitialized/retired native slots have no ModPlayer. The native
            // Try query checks the roster/index without throwing first-chance
            // exceptions which tML logs even when our caller catches them.
            if (player is not null && player.TryGetModPlayer<InfiniCraftPlayer>(out var craftPlayer))
                craftPlayer.ClearGeneratedUtilityState();
        }
    }
    public override void OnWorldUnload() => ClearPlayers();
    public override void Unload() => ClearPlayers();
}
