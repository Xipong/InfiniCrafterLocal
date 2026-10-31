#nullable enable
using System.Collections.Generic;
using System.IO;
using Microsoft.Xna.Framework;
using ResonanceLattice.Content.NPCs;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Core;

/// <summary>
/// Packet layer for the lattice. All packets are this mod's <see cref="ModPacket"/> with a
/// leading sub-type byte. Server-authoritative: clients send bounded requests
/// (charge injection, wisp summon), the server validates them and answers/relays.
/// </summary>
internal static class LatticeNet
{
    internal enum LatticeMsg : byte
    {
        InjectRequest = 1,   // client -> server: worldPos + amount
        InjectResult = 2,    // server -> client: applied amount (0 = no network in range / rejected)
        ChargeDelta = 3,     // server -> clients: node charge updates
        TopologyFull = 4,    // server -> clients: full node snapshot
        SummonWispRequest = 5, // client -> server: worldPos
        SummonWispResult = 6,  // server -> client: ok flag
    }

    private static ModPacket NewPacket(LatticeMsg msg, int capacity = 256)
    {
        ModPacket packet = ResonanceLatticeMod.Instance.GetPacket(capacity);
        packet.Write((byte)msg);
        return packet;
    }

    // ------------------------------------------------------------------
    // Sends
    // ------------------------------------------------------------------

    /// <summary>Client -> server: ask to inject charge at a position (validated server-side).</summary>
    internal static void SendInjectRequest(Vector2 worldPos, float amount)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        // Local rate limit mirrors the server-side one so a client cannot spam packets.
        int now = (int)Main.GameUpdateCount;
        if (now - _lastLocalInjectTick < LatticeLimits.InjectRequestCooldownTicks)
            return;
        _lastLocalInjectTick = now;
        ModPacket packet = NewPacket(LatticeMsg.InjectRequest);
        packet.Write(worldPos.X);
        packet.Write(worldPos.Y);
        packet.Write(amount);
        packet.Send();
    }

    private static int _lastLocalInjectTick = int.MinValue;

    /// <summary>Server -> all clients: full node snapshot (topology change).</summary>
    internal static void SendTopologyFull(IReadOnlyDictionary<Point16, LatticeNode> nodes)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        int count = System.Math.Min(nodes.Count, LatticeLimits.MaxTopologyNodesPerPacket);
        ModPacket packet = NewPacket(LatticeMsg.TopologyFull, 8 + count * 8);
        packet.Write(count);
        int written = 0;
        foreach (KeyValuePair<Point16, LatticeNode> pair in nodes)
        {
            if (written++ >= count)
                break;
            packet.Write((short)pair.Key.X);
            packet.Write((short)pair.Key.Y);
            packet.Write(pair.Value.Charge);
        }
        packet.Send();
    }

    /// <summary>Server -> all clients: bounded charge deltas for nodes whose charge changed.</summary>
    internal static void SendChargeDelta(IReadOnlyDictionary<Point16, LatticeNode> nodes)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        if (nodes.Count > LatticeLimits.MaxDeltaEntriesPerPacket)
        {
            SendTopologyFull(nodes);
            return;
        }
        ModPacket packet = NewPacket(LatticeMsg.ChargeDelta, 8 + nodes.Count * 8);
        packet.Write(nodes.Count);
        foreach (KeyValuePair<Point16, LatticeNode> pair in nodes)
        {
            packet.Write((short)pair.Key.X);
            packet.Write((short)pair.Key.Y);
            packet.Write(pair.Value.Charge);
        }
        packet.Send();
    }

    /// <summary>Client -> server: ask to summon a wisp at a position (validated server-side).</summary>
    internal static void SendSummonWispRequest(Vector2 worldPos)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        ModPacket packet = NewPacket(LatticeMsg.SummonWispRequest);
        packet.Write(worldPos.X);
        packet.Write(worldPos.Y);
        packet.Send();
    }

    private static void SendToClient(LatticeMsg msg, int whoAmI, System.Action<ModPacket> write)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        ModPacket packet = NewPacket(msg);
        write(packet);
        packet.Send(toClient: whoAmI);
    }

    // ------------------------------------------------------------------
    // Receive
    // ------------------------------------------------------------------

    internal static void HandlePacket(BinaryReader reader, int whoAmI)
    {
        var msg = (LatticeMsg)reader.ReadByte();
        switch (msg)
        {
            case LatticeMsg.InjectRequest:
                if (Main.netMode == NetmodeID.Server)
                    HandleInjectRequest(reader, whoAmI);
                break;
            case LatticeMsg.InjectResult:
                if (Main.netMode == NetmodeID.MultiplayerClient)
                    HandleInjectResult(reader);
                break;
            case LatticeMsg.ChargeDelta:
                if (Main.netMode == NetmodeID.MultiplayerClient)
                {
                    int count = reader.ReadInt32();
                    if (count >= 0 && count <= LatticeLimits.MaxNodesPerWorld)
                        LatticeWorldSystem.ApplyChargeDelta(count, reader);
                }
                break;
            case LatticeMsg.TopologyFull:
                if (Main.netMode == NetmodeID.MultiplayerClient)
                {
                    int count = reader.ReadInt32();
                    if (count >= 0 && count <= LatticeLimits.MaxNodesPerWorld)
                        LatticeWorldSystem.ApplyTopologySnapshot(count, reader);
                }
                break;
            case LatticeMsg.SummonWispRequest:
                if (Main.netMode == NetmodeID.Server)
                    HandleSummonWispRequest(reader, whoAmI);
                break;
            case LatticeMsg.SummonWispResult:
                if (Main.netMode == NetmodeID.MultiplayerClient)
                    HandleSummonWispResult(reader);
                break;
        }
    }

    private static void HandleInjectRequest(BinaryReader reader, int whoAmI)
    {
        var pos = new Vector2(reader.ReadSingle(), reader.ReadSingle());
        float amount = reader.ReadSingle();
        bool allowed = LatticeWorldSystem.ValidateInjectRequest(whoAmI, pos, amount, out bool ok);
        float applied = ok ? LatticeWorldSystem.InjectChargeAt(pos, allowed) : 0f;
        SendToClient(LatticeMsg.InjectResult, whoAmI, packet => packet.Write(applied));
    }

    private static void HandleInjectResult(BinaryReader reader)
    {
        float applied = reader.ReadSingle();
        Player player = Main.LocalPlayer;
        if (applied > 0f)
        {
            CombatText.NewText(player.Hitbox, new Color(140, 240, 255), "+" + applied.ToString("0.#") + " ⚡");
        }
        else
        {
            Main.NewText(Terraria.Localization.Language.GetTextValue("Mods.ResonanceLattice.Chat.NoNetwork"), 200, 120, 120);
        }
    }

    private static void HandleSummonWispRequest(BinaryReader reader, int whoAmI)
    {
        var pos = new Vector2(reader.ReadSingle(), reader.ReadSingle());
        bool ok = false;
        if (whoAmI >= 0 && whoAmI < Main.maxPlayers)
        {
            Player player = Main.player[whoAmI];
            if (player.active && !player.dead
                && Vector2.Distance(player.Center, pos) <= LatticeLimits.MaxInjectRequestDistanceTiles * 16f)
            {
                ok = LatticeWispNPC.TrySummon(player, pos);
            }
        }
        SendToClient(LatticeMsg.SummonWispResult, whoAmI, packet => packet.Write(ok));
        if (ok)
            LatticeWorldSystem.SendLocalizedToClient("Mods.ResonanceLattice.Chat.WispSummoned", whoAmI);
        else
            LatticeWorldSystem.SendLocalizedToClient("Mods.ResonanceLattice.Chat.WispLimit", whoAmI);
    }

    private static void HandleSummonWispResult(BinaryReader reader)
    {
        // The server already sends a localized chat line; nothing else to do client-side.
        _ = reader.ReadBoolean();
    }
}
