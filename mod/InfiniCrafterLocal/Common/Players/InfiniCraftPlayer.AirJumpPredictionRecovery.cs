#nullable enable
using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private Guid _airJumpPredictionFence;
    private long _airJumpPredictionFenceGeneration;
    private long _airJumpPredictionRecoveryGeneration;
    private long _airJumpPredictionLastRetiredGeneration;
    private int _airJumpPredictionFenceRetryTicks;
    private Guid _airJumpPredictionServerFence;
    private object? _airJumpPredictionServerSocket;
    private string _airJumpPredictionServerWorld = "";

    private bool AirJumpUtilityIsQuiescent()
        => Player.itemAnimation == 0 && Player.itemTime == 0 && !Player.controlUseItem
            && !GeneratedQuickUtilityActivation.HasPendingUtility(Player)
            && !RuntimeDelayedActionScheduler.HasPendingGeneratedBuff(Player);

    private void TickAirJumpPredictionRecovery()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer
            || !Player.active || Player.dead || _generatedUtilityAwaitingRespawnSync) return;
        EnsureAirJumpAuthorityScope();
        if (!_airJumpPredictionHistoryOverflow && _retiredAirJumpPredictions.Count == 0) return;
        if (_airJumpPredictionFence == Guid.Empty)
        {
            if (!AirJumpUtilityIsQuiescent()) return;
            _airJumpPredictionFence = Guid.NewGuid();
            // This tick follows gameplay sends on the ordered uplink. Correlate
            // only predictions already allocated, never later in-flight ones.
            _airJumpPredictionFenceGeneration = _nextGeneratedBuffSourceGeneration * 2;
        }
        else if (++_airJumpPredictionFenceRetryTicks < 60) return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.RequestAirJumpPredictionFence);
        packet.Write((byte)Player.whoAmI);
        packet.Write(_airJumpPredictionFence.ToByteArray());
        packet.Send();
        _airJumpPredictionFenceRetryTicks = 0;
    }

    public static void HandleAirJumpPredictionFenceRequest(BinaryReader reader, int whoAmI)
    {
        byte playerId = reader.ReadByte();
        Guid nonce = ReadGeneratedUtilityRespawnNonce(reader);
        if (Main.netMode != NetmodeID.Server || playerId != whoAmI || playerId >= Main.maxPlayers
            || nonce == Guid.Empty) return;
        Player player = Main.player[playerId];
        if (player is null || !player.active || player.dead) return;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        // An ordered packet alone cannot drain Prepare/Ready/Commit or delayed
        // actions. Keep one bounded request; acknowledge only after a complete
        // native world update has drained all prior utility producers.
        owner._airJumpPredictionServerFence = nonce;
        owner._airJumpPredictionServerSocket = Netplay.Clients[playerId]?.Socket;
        owner._airJumpPredictionServerWorld = GeneratedItemRegistryService.CurrentWorldIdString();
    }

    internal void CompleteAirJumpPredictionFence()
    {
        if (Main.netMode != NetmodeID.Server || _airJumpPredictionServerFence == Guid.Empty) return;
        if (!Player.active || Player.dead
            || !ReferenceEquals(_airJumpPredictionServerSocket, Netplay.Clients[Player.whoAmI]?.Socket)
            || _airJumpPredictionServerWorld != GeneratedItemRegistryService.CurrentWorldIdString())
        {
            _airJumpPredictionServerFence = Guid.Empty;
            return;
        }
        if (!AirJumpUtilityIsQuiescent()) return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.AirJumpPredictionFence);
        packet.Write((byte)Player.whoAmI);
        packet.Write(_airJumpPredictionServerFence.ToByteArray());
        // Include retired authority generations as well as currently live rows.
        packet.Write(_nextGeneratedBuffSourceGeneration == 0 ? 0L
            : _nextGeneratedBuffSourceGeneration * 2 + 1);
        _airJumpPredictionServerFence = Guid.Empty;
        packet.Send(Player.whoAmI);
    }

    public static void HandleAirJumpPredictionFence(BinaryReader reader, int whoAmI)
    {
        byte playerId = reader.ReadByte();
        Guid nonce = ReadGeneratedUtilityRespawnNonce(reader);
        long generation = reader.ReadInt64();
        if (Main.netMode != NetmodeID.MultiplayerClient || whoAmI != 256
            || playerId != Main.myPlayer || playerId >= Main.maxPlayers
            || generation > 0 || generation < 0 && (generation & 1) == 0) return;
        Player player = Main.player[playerId];
        if (player is null || !player.active || player.dead) return;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        owner.EnsureGeneratedUtilityRespawnScope();
        owner.EnsureAirJumpAuthorityScope();
        if (owner._generatedUtilityAwaitingRespawnSync || nonce == Guid.Empty
            || owner._airJumpPredictionFence != nonce) return;
        // Earlier server snapshots precede this reply on the same downlink.
        // They can never confirm future predictions, even if their rows expired
        // before the reply. Existing ambiguous lifetimes never gain an alias.
        owner._lastAuthoritativeBuffGeneration = Math.Min(owner._lastAuthoritativeBuffGeneration, generation);
        owner._airJumpPredictionRecoveryGeneration = owner._airJumpPredictionFenceGeneration;
        foreach (var key in owner._retiredAirJumpPredictions.Where(pair =>
            pair.Value >= owner._airJumpPredictionRecoveryGeneration).Select(pair => pair.Key).ToArray())
            owner._retiredAirJumpPredictions.Remove(key);
        if (owner._airJumpPredictionLastRetiredGeneration >= owner._airJumpPredictionRecoveryGeneration)
            owner._airJumpPredictionHistoryOverflow = false;
        owner._airJumpPredictionFence = Guid.Empty;
    }
}
