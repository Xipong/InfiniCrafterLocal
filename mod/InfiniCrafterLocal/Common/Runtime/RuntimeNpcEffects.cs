#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Runtime;

// Bounded, independently expiring generated effects. No native buff slot, immunity
// identity, npc.defense mutation or permanent npc.damage mutation is involved.
internal static class RuntimeNpcEffects
{
    internal const int MaxRecordsPerNpc = 16;
    private readonly record struct Key(string Item, string Entity, string Action, int Owner);
    private sealed record Entry(Key Key, Player? Owner, uint Start, int Duration,
        int Regen, int Defense, float Contact, float Retention);
    private sealed record State(NPC Host, uint Generation, List<Entry> Entries);
    private static readonly State?[] States = new State?[Main.maxNPCs];
    internal readonly record struct Totals(int Count, int Regen, int Defense, float Contact, float Retention);

    internal static bool Apply(GeneratedItemData data, RuntimeEntitySpec entity, RuntimeEventActionSpec action, Player owner, NPC? npc)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient || npc is not { active: true } || npc.life <= 0
            || npc.whoAmI < 0 || npc.whoAmI >= Main.maxNPCs || !ReferenceEquals(Main.npc[npc.whoAmI], npc)
            || action.ActionCode != RuntimeEventActionCode.ApplyNpcEffect
            || action.Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
            || action.NpcEffect is not { HasEffect: true } effect || action.DurationTicks is < 1 or > 3600)
            return false;
        uint generation = RuntimeHitNpcGeneration.Get(npc);
        if (generation == 0) return false;
        GetTotals(npc); // retire expired records before capacity admission
        State state = States[npc.whoAmI] ??= new(npc, generation, new());
        var key = new Key(data.Id, entity.Id, action.Id, owner.whoAmI);
        int index = state.Entries.FindIndex(x => x.Key == key);
        var entry = new Entry(key, owner, Main.GameUpdateCount, action.DurationTicks,
            effect.LifeRegenPenalty, effect.DefenseDelta, effect.ContactDamageMultiplier, effect.VelocityRetentionPerTick);
        if (index >= 0) state.Entries[index] = entry; // refresh, never accumulate per hit
        else if (state.Entries.Count < MaxRecordsPerNpc) state.Entries.Add(entry);
        else return false; // explicit technical cap: retain existing independent records
        if (Main.netMode == NetmodeID.Server) npc.netUpdate = true;
        return true;
    }

    internal static Totals GetTotals(NPC npc)
    {
        int slot = npc.whoAmI;
        if (slot < 0 || slot >= States.Length) return new(0, 0, 0, 1f, 1f);
        State? state = States[slot];
        if (state is null) return new(0, 0, 0, 1f, 1f);
        if (!ReferenceEquals(state.Host, npc) || !ReferenceEquals(Main.npc[slot], npc)
            || !npc.active || npc.life <= 0 || state.Generation != RuntimeHitNpcGeneration.Get(npc))
        {
            States[slot] = null;
            return new(0, 0, 0, 1f, 1f);
        }
        int removed = state.Entries.RemoveAll(x => unchecked(Main.GameUpdateCount - x.Start) >= (uint)x.Duration
            || x.Owner is not null && (!x.Owner.active || !ReferenceEquals(Main.player[x.Key.Owner], x.Owner)));
        if (removed > 0 && Main.netMode == NetmodeID.Server) npc.netUpdate = true;
        int regen = 0, defense = 0;
        double contact = 1d, retention = 1d;
        // Multiplication order is stable across arrival order and peer serialization.
        foreach (Entry entry in Ordered(state))
        {
            regen += entry.Regen; defense += entry.Defense;
            contact *= entry.Contact; retention *= entry.Retention;
        }
        return new(state.Entries.Count, Math.Min(regen, 400), Math.Clamp(defense, -100, 100),
            (float)Math.Clamp(contact, .1d, 3d), (float)Math.Clamp(retention, .1d, 1d));
    }

    private static IOrderedEnumerable<Entry> Ordered(State state) => state.Entries.OrderBy(x => x.Key.Owner)
        .ThenBy(x => x.Key.Item, StringComparer.Ordinal).ThenBy(x => x.Key.Entity, StringComparer.Ordinal)
        .ThenBy(x => x.Key.Action, StringComparer.Ordinal);

    internal static void Send(NPC npc, BinaryWriter writer)
    {
        _ = GetTotals(npc);
        State? state = npc.whoAmI >= 0 && npc.whoAmI < States.Length ? States[npc.whoAmI] : null;
        writer.Write((byte)(state?.Entries.Count ?? 0));
        if (state is null) return;
        foreach (Entry entry in Ordered(state))
        {
            writer.Write((ushort)(entry.Duration - unchecked(Main.GameUpdateCount - entry.Start)));
            writer.Write(entry.Regen); writer.Write(entry.Defense); writer.Write(entry.Contact); writer.Write(entry.Retention);
        }
    }

    internal static void Receive(NPC npc, BinaryReader reader)
    {
        int count = reader.ReadByte();
        if (count > MaxRecordsPerNpc) throw new InvalidDataException("NPC effect record cap");
        var entries = new List<Entry>(count);
        for (int i = 0; i < count; i++)
        {
            int duration = reader.ReadUInt16();
            var effect = new RuntimeNpcEffectSpec { LifeRegenPenalty = reader.ReadInt32(), DefenseDelta = reader.ReadInt32(),
                ContactDamageMultiplier = reader.ReadSingle(), VelocityRetentionPerTick = reader.ReadSingle() };
            effect.Validate();
            if (duration is < 1 or > 3600) throw new InvalidDataException("NPC effect duration");
            entries.Add(new(new("", "", "", i), null, Main.GameUpdateCount, duration,
                effect.LifeRegenPenalty, effect.DefenseDelta, effect.ContactDamageMultiplier, effect.VelocityRetentionPerTick));
        }
        // Only authoritative server ExtraAI supplies combat modifier state. A
        // client cannot overwrite the server's active entries through ExtraAI.
        if (Main.netMode != NetmodeID.MultiplayerClient || npc.whoAmI < 0 || npc.whoAmI >= States.Length) return;
        States[npc.whoAmI] = new(npc, RuntimeHitNpcGeneration.Get(npc), entries);
    }

    internal static void Forget(NPC npc)
    {
        if (npc.whoAmI >= 0 && npc.whoAmI < States.Length) States[npc.whoAmI] = null;
    }
    internal static void Clear() => Array.Clear(States);
}
