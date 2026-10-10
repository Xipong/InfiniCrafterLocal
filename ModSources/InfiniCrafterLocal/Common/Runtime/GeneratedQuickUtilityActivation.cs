#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Runtime;

// Vanilla owner-use trust, not anti-cheat/native-heal proof. Prepare is emitted
// inside the real quick-use utility hook BEFORE native healing/stack decrement.
// The ordered ModPacket stream therefore admits the server's material witness
// before the later native inventory sync, including a final-stack TurnToAir.
// Only canonical utility entries are committed; UseItem/events/native effects
// are NEVER replayed here. A server-issued one-shot ticket supplies server time.
internal static class GeneratedQuickUtilityActivation
{
    private const byte Version = 1, Prepare = 1, Ready = 2, Commit = 3;
    private const int LifetimeTicks = 180, MaxPendingPerOwner = 8;
    private static ulong nextSequence, nextTicket;
    private sealed record Identity(byte Owner, byte Kind, byte Slot, long ItemToken,
        string ItemId, string Definition, string BindingId, ulong Sequence);
    private sealed record Local(Identity Id, Player Owner, object? Socket, ulong Tick);
    private sealed record Pending(Identity Id, Player Owner, object? Socket,
        ulong Ticket, ulong Tick);
    private sealed class OwnerState
    {
        internal readonly Player Owner;
        internal readonly object? Socket;
        internal ulong Sequence;
        internal readonly Dictionary<ulong, Pending> Pending = new();
        internal OwnerState(Player owner, object? socket) { Owner = owner; Socket = socket; }
    }
    private static readonly OwnerState?[] owners = new OwnerState?[Main.maxPlayers];
    private static readonly Dictionary<ulong, Local> local = new();

    internal static bool IsEligible(GeneratedItemData data)
        => data.PrimaryUseEffects.GeneratedBuff?.HasAnyEffect == true
            && (data.PrimaryUseEffects.HealLife > 0 || data.PrimaryUseEffects.HealMana > 0)
            && data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse)?.UsePolicy.Action.Kind
                == RuntimeBindingAction.ApplyItemEffects;

    internal static void Send(Player player, GeneratedItem item, byte kind)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || player.whoAmI != Main.myPlayer
            || player is not { active: true, dead: false } || kind is not (1 or 2)
            || !IsEligible(item.Data) || !GeneratedItemRegistryService.IsCurrentWorldData(item.Data)
            || !HasResource(item.Data, kind)) return;
        Prune();
        if (local.Count >= MaxPendingPerOwner) return; // bounded refusal, never evict a live ticket
        int slot = FindSlot(player, item.Item);
        if (slot < 0) return;
        RuntimeBindingSpec binding = item.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse)!;
        var id = new Identity((byte)player.whoAmI, kind, (byte)slot, item.PresentationToken,
            item.Data.Id, GeneratedItemRegistryService.DefinitionIdentity(item.Data), binding.Id, checked(++nextSequence));
        if (!Valid(id)) return;
        // A just-opened Void Bag is itself a native use prerequisite. Publish the
        // exact inventory witness first; bank4 sync alone cannot update a server
        // which still sees the closed bag (or air). Keep the server useVoidBag gate.
        if (slot >= 58)
        {
            int bagSlot = -1;
            for (int i = 0; i < Math.Min(58, player.inventory.Length); i++)
                if (player.inventory[i].stack > 0 && player.inventory[i].type == ItemID.VoidLens)
                { bagSlot = i; break; } // the installed Player.useVoidBag predicate
            if (bagSlot < 0) return;
            NetMessage.SendData(MessageID.SyncEquipment, number: player.whoAmI,
                number2: PlayerItemSlotID.Inventory0 + bagSlot, number3: player.inventory[bagSlot].prefix);
        }
        // Publish the exact native pre-consumption Item through Terraria's existing
        // owner equipment protocol before the ordered Prepare. This includes the
        // current presentation token and native bank4 slot, even on first use.
        int nativeSlot = slot < 58 ? PlayerItemSlotID.Inventory0 + slot
            : PlayerItemSlotID.Bank4_0 + slot - 58;
        NetMessage.SendData(MessageID.SyncEquipment, number: player.whoAmI,
            number2: nativeSlot, number3: item.Item.prefix);
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null) return;
        local.Add(id.Sequence, new(id, player, Netplay.Connection?.Socket, Main.GameUpdateCount));
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedQuickUtilityActivation);
        packet.Write(Version); packet.Write(Prepare); Write(packet, id); packet.Send();
    }

    private static int FindSlot(Player player, Item item)
    {
        for (int i = 0; i < Math.Min(58, player.inventory.Length); i++)
            if (ReferenceEquals(player.inventory[i], item)) return i;
        if (player.useVoidBag())
            for (int i = 0; i < player.bank4.item.Length && i < 40; i++)
                if (ReferenceEquals(player.bank4.item[i], item)) return 58 + i;
        return -1;
    }
    private static Item? At(Player player, byte slot)
        => slot < 58 ? slot < player.inventory.Length ? player.inventory[slot] : null
            : slot < 98 && player.useVoidBag() ? player.bank4.item[slot - 58] : null;
    private static bool HasResource(GeneratedItemData data, byte kind)
        => kind == 1 ? data.PrimaryUseEffects.HealLife > 0 && data.PrimaryUseEffects.Potion : data.PrimaryUseEffects.HealMana > 0;
    private static bool Fresh(ulong tick)
        => unchecked((uint)(Main.GameUpdateCount - (uint)tick)) <= LifetimeTicks;
    private static bool Valid(Identity id)
        => id.Owner < Main.maxPlayers && id.Kind is 1 or 2 && id.Slot < 98 && id.ItemToken > 0
            && id.Sequence > 0 && Encoding.UTF8.GetByteCount(id.ItemId) is > 0 and <= 96
            && Encoding.UTF8.GetByteCount(id.BindingId) is > 0 and <= 48
            && id.Definition.Length == 64 && IsHash(id.Definition);
    private static bool IsHash(string value)
    {
        foreach (char c in value) if (!(c is >= '0' and <= '9' or >= 'a' and <= 'f')) return false;
        return true;
    }
    private static void Text(BinaryWriter writer, string text)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(text); writer.Write((byte)bytes.Length); writer.Write(bytes);
    }
    private static string Text(BinaryReader reader, int max)
    {
        int length = reader.ReadByte();
        if (length == 0 || length > max) throw new InvalidDataException("quick utility identity length");
        byte[] bytes = reader.ReadBytes(length);
        if (bytes.Length != length) throw new EndOfStreamException();
        return new UTF8Encoding(false, true).GetString(bytes);
    }
    private static void Write(BinaryWriter writer, Identity id)
    {
        writer.Write(id.Owner); writer.Write(id.Kind); writer.Write(id.Slot); writer.Write(id.ItemToken);
        writer.Write(id.Sequence); Text(writer, id.ItemId); Text(writer, id.Definition); Text(writer, id.BindingId);
    }
    private static Identity Read(BinaryReader reader)
    {
        byte owner = reader.ReadByte(), kind = reader.ReadByte(), slot = reader.ReadByte();
        long token = reader.ReadInt64(); ulong sequence = reader.ReadUInt64();
        return new(owner, kind, slot, token, Text(reader, 96), Text(reader, 64), Text(reader, 48), sequence);
    }
    private static GeneratedItemData? Resolve(Identity id)
    {
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null || !registry.TryGet(id.ItemId, out GeneratedItemData data)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data)
            || GeneratedItemData.IsPlayerSaveReferenceOnly(data) || !IsEligible(data) || !HasResource(data, id.Kind)
            || GeneratedItemRegistryService.DefinitionIdentity(data) != id.Definition) return null;
        RuntimeBindingSpec? binding = data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse);
        return binding?.Id == id.BindingId && binding.UsePolicy.Action.TargetId == data.RuntimeProgram.ItemEntityId
            ? data : null;
    }
    internal static void HandlePacket(BinaryReader reader, int sender)
    {
        byte version, op; Identity id; ulong ticket = 0;
        try
        {
            version = reader.ReadByte(); op = reader.ReadByte(); id = Read(reader);
            if (op is Ready or Commit) ticket = reader.ReadUInt64();
        }
        catch (Exception error) when (error is EndOfStreamException or InvalidDataException or DecoderFallbackException) { return; }
        if (version != Version || !Valid(id)) return;
        Prune();
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            if (sender != 256 || op != Ready || ticket == 0 || id.Owner != Main.myPlayer
                || !local.TryGetValue(id.Sequence, out Local? waiting) || waiting.Id != id
                || !ReferenceEquals(Main.player[id.Owner], waiting.Owner) || waiting.Owner.dead
                || !ReferenceEquals(Netplay.Connection?.Socket, waiting.Socket) || !Fresh(waiting.Tick)) return;
            // Native UseItem already ran once, so neither Ready nor its replay can
            // re-run prediction, heal, stack debit, events or VFX.
            local.Remove(id.Sequence);
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
            if (packet is null) return;
            packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedQuickUtilityActivation);
            packet.Write(Version); packet.Write(Commit); Write(packet, id); packet.Write(ticket); packet.Send();
            return;
        }
        if (Main.netMode != NetmodeID.Server || sender != id.Owner
            || Main.player[sender] is not { active: true, dead: false } player || player.whoAmI != sender) return;
        object? socket = Netplay.Clients[sender]?.Socket;
        OwnerState? state = owners[sender];
        if (state is null || !ReferenceEquals(state.Owner, player) || !ReferenceEquals(state.Socket, socket))
            owners[sender] = state = new OwnerState(player, socket);
        if (op == Prepare)
        {
            if (id.Sequence <= state.Sequence) return;
            // Retain high-water even for a refused well-formed claim: replay can
            // never acquire a ticket after an inventory/definition change.
            state.Sequence = id.Sequence;
            if (state.Pending.Count >= MaxPendingPerOwner || Resolve(id) is not { } data
                || At(player, id.Slot) is not { IsAir: false } host || host.stack <= 0
                || host.ModItem is not GeneratedItem generated || generated.PresentationToken != id.ItemToken
                || generated.Data.Id != id.ItemId || !GeneratedItemRegistryService.IsCurrentWorldData(generated.Data)
                || GeneratedItemRegistryService.DefinitionIdentity(generated.Data) != id.Definition) return;
            ulong nonce = checked(++nextTicket);
            state.Pending.Add(id.Sequence, new(id, player, socket, nonce, Main.GameUpdateCount));
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
            if (packet is null) { state.Pending.Remove(id.Sequence); return; }
            packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedQuickUtilityActivation);
            packet.Write(Version); packet.Write(Ready); Write(packet, id); packet.Write(nonce); packet.Send(sender);
        }
        else if (op == Commit)
        {
            if (ticket == 0 || !state.Pending.TryGetValue(id.Sequence, out Pending? pending)
                || pending.Id != id || pending.Ticket != ticket || !Fresh(pending.Tick)
                || !ReferenceEquals(pending.Owner, player) || !ReferenceEquals(pending.Socket, socket)) return;
            // Retire BEFORE invoking the canonical consumer / outgoing snapshot.
            state.Pending.Remove(id.Sequence);
            if (Resolve(id) is not { } data) return;
            // The ownership fence was captured at Prepare. Requiring a live Item
            // now would cancel legitimate native final-stack consumption. A ticket
            // is a short-lived authorization for that occurrence, not a new Item.
            var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
            GeneratedBuffSpec authored = data.PrimaryUseEffects.GeneratedBuff!;
            int elapsed = (int)unchecked((uint)(Main.GameUpdateCount - (uint)pending.Tick));
            int remaining = authored.DurationTicks - elapsed;
            if (remaining <= 0) return;
            // Anchor expiry at server admission, not the later Commit arrival.
            // Never mutate a registry-owned definition to carry remaining time.
            modPlayer.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec {
                DurationTicks = remaining, MiningSpeedMultiplier = authored.MiningSpeedMultiplier,
                EmitLightStrength = authored.EmitLightStrength, LightColorName = authored.LightColorName,
                OreSenseRadiusTiles = authored.OreSenseRadiusTiles, MovementSpeed = authored.MovementSpeed,
                JumpBoost = authored.JumpBoost, ManaRegen = authored.ManaRegen, LifeRegen = authored.LifeRegen,
            }, syncNetwork: true);
        }
    }
    internal static void Prune()
    {
        var remove = new List<ulong>();
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            foreach (var row in local)
                if (!Fresh(row.Value.Tick) || !ReferenceEquals(Netplay.Connection?.Socket, row.Value.Socket)
                    || Main.player[row.Value.Id.Owner] != row.Value.Owner || row.Value.Owner.dead) remove.Add(row.Key);
            foreach (ulong key in remove) local.Remove(key);
        }
        if (Main.netMode != NetmodeID.Server) return;
        for (int i = 0; i < owners.Length; i++)
        {
            OwnerState? state = owners[i]; if (state is null) continue;
            if (Main.player[i] != state.Owner
                || !ReferenceEquals(Netplay.Clients[i]?.Socket, state.Socket)) { owners[i] = null; continue; }
            // Death/inactivity revoke tickets, NOT the ordered-stream replay cursor.
            if (!state.Owner.active || state.Owner.dead) { state.Pending.Clear(); continue; }
            remove.Clear();
            foreach (var row in state.Pending) if (!Fresh(row.Value.Tick)) remove.Add(row.Key);
            foreach (ulong key in remove) state.Pending.Remove(key);
        }
    }
    internal static void Clear()
    {
        Array.Clear(owners); local.Clear();
        // Keep process allocators monotonic: a late in-process old message must
        // not alias a new world ticket. Transport cursors are world-scoped.
    }
}

public sealed class GeneratedQuickUtilityActivationSystem : ModSystem
{
    public override void PostUpdateEverything() => GeneratedQuickUtilityActivation.Prune();
    public override void OnWorldUnload() => GeneratedQuickUtilityActivation.Clear();
    public override void Unload() => GeneratedQuickUtilityActivation.Clear();
}
