#nullable enable
using System;
using System.IO;
using Terraria;

namespace InfiniCrafterLocal.Common.Runtime;

// An exact physical-NPC snapshot, never a slot-only immunity grant. The countdown
// follows the historical child-spawn counter: AI decrements before collision.
// Thus 1 suppresses contact before the first AI, 10 suppresses the next 9 post-AI
// collision opportunities. Callers author this counter in native updates.
internal readonly record struct RuntimeInitialNpcExclusion(int NpcSlot, uint Generation, int RemainingUpdates)
{
    internal const int MaxUpdates = 600;
    internal static RuntimeInitialNpcExclusion None => new(-1, 0, 0);
    internal bool IsEmpty => RemainingUpdates == 0;
    internal bool IsValid => RemainingUpdates == 0
        ? NpcSlot == -1 && Generation == 0
        : RemainingUpdates > 0 && RemainingUpdates <= MaxUpdates
            && NpcSlot >= 0 && NpcSlot < Main.maxNPCs && Generation != 0;

    internal static bool TryCapture(NPC? npc, int updates, out RuntimeInitialNpcExclusion snapshot)
    {
        snapshot = None;
        if (updates < 0 || updates > MaxUpdates) return false;
        if (updates == 0) return true;
        if (npc is null || npc.whoAmI < 0 || npc.whoAmI >= Main.maxNPCs
            || !ReferenceEquals(Main.npc[npc.whoAmI], npc)) return false;
        uint generation = RuntimeHitNpcGeneration.Get(npc);
        if (generation == 0) return false;
        snapshot = new(npc.whoAmI, generation, updates);
        return true;
    }

    internal bool CanApply => IsValid && (IsEmpty || Main.npc[NpcSlot] is { } npc
        && RuntimeHitNpcGeneration.Get(npc) == Generation);

    internal bool AppliesTo(NPC npc) => !IsEmpty && IsValid
        && npc.whoAmI == NpcSlot && ReferenceEquals(Main.npc[NpcSlot], npc)
        && RuntimeHitNpcGeneration.Get(npc) == Generation;

    internal RuntimeInitialNpcExclusion AfterUpdate()
        => RemainingUpdates <= 1 ? None : this with { RemainingUpdates = RemainingUpdates - 1 };

    internal void Write(BinaryWriter writer)
    {
        if (!IsValid) throw new InvalidDataException("invalid initial NPC exclusion snapshot");
        writer.Write((short)NpcSlot);
        writer.Write(Generation);
        writer.Write((ushort)RemainingUpdates);
    }

    internal static RuntimeInitialNpcExclusion Read(BinaryReader reader)
    {
        var snapshot = new RuntimeInitialNpcExclusion(reader.ReadInt16(), reader.ReadUInt32(), reader.ReadUInt16());
        if (!snapshot.IsValid) throw new InvalidDataException("invalid initial NPC exclusion payload");
        return snapshot;
    }
}
