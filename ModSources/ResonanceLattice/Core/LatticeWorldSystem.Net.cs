#nullable enable
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Localization;

namespace ResonanceLattice.Core;

/// <summary>
/// Incremental multiplayer sync. The server is authoritative: it broadcasts a full topology
/// snapshot when the node set changes and a bounded charge-delta packet when charges move.
/// Clients never simulate; they merge packets into their local registry for rendering/light.
/// </summary>
public sealed partial class LatticeWorldSystem
{
    private static void SyncTick()
    {
        if (_topologyVersion != _lastSentTopologyVersion)
        {
            _lastSentTopologyVersion = _topologyVersion;
            LatticeNet.SendTopologyFull(Nodes);
        }
        else if (_chargeVersion != _lastSyncedChargeVersion)
        {
            _lastSyncedChargeVersion = _chargeVersion;
            LatticeNet.SendChargeDelta(Nodes);
        }
    }

    /// <summary>Apply a full topology snapshot received from the server (client side).</summary>
    internal static void ApplyTopologySnapshot(int count, System.IO.BinaryReader reader)
    {
        Nodes.Clear();
        for (int i = 0; i < count; i++)
        {
            var tile = new Point16(reader.ReadInt16(), reader.ReadInt16());
            float charge = reader.ReadSingle();
            Nodes.Add(tile, new LatticeNode(tile) { Charge = charge });
        }
        MarkTopologyDirty();
    }

    /// <summary>Apply charge deltas received from the server (client side).</summary>
    internal static void ApplyChargeDelta(int count, System.IO.BinaryReader reader)
    {
        for (int i = 0; i < count; i++)
        {
            var tile = new Point16(reader.ReadInt16(), reader.ReadInt16());
            float charge = reader.ReadSingle();
            if (Nodes.TryGetValue(tile, out LatticeNode? node))
                node.Charge = charge;
            else if (Nodes.Count < LatticeLimits.MaxNodesPerWorld)
                Nodes.Add(tile, new LatticeNode(tile) { Charge = charge });
        }
    }

    /// <summary>
    /// Server-side validation gate for client charge-injection requests: distance to the
    /// sender, per-player cooldown and absolute amount cap. Returns the clamped amount.
    /// </summary>
    internal static float ValidateInjectRequest(int whoAmI, Vector2 worldPos, float requestedAmount, out bool allowed)
    {
        allowed = false;
        if (whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return 0f;
        Player player = Main.player[whoAmI];
        if (!player.active || player.dead)
            return 0f;
        if (Vector2.Distance(player.Center, worldPos) > LatticeLimits.MaxInjectRequestDistanceTiles * 16f)
            return 0f;
        int now = (int)Main.GameUpdateCount;
        if (_lastInjectRequestTick.TryGetValue(whoAmI, out int last) && now - last < LatticeLimits.InjectRequestCooldownTicks)
            return 0f;
        _lastInjectRequestTick[whoAmI] = now;
        allowed = true;
        return MathHelper.Clamp(requestedAmount, 0f, LatticeLimits.MaxInjectPerRequest);
    }

    internal static void SendLocalizedToClient(string key, int whoAmI, params object[] args)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        Terraria.Chat.ChatHelper.SendChatMessageToClient(NetworkText.FromKey(key, args), new Color(140, 240, 255), whoAmI);
    }
}
