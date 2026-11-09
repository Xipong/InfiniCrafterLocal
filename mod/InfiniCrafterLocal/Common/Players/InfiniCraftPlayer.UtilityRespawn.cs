#nullable enable
using System;
using System.IO;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private bool _generatedUtilityAwaitingRespawnSync;
    private bool _generatedUtilityServerRespawnObserved;
    private Guid _generatedUtilityRespawnRequest;
    private int _generatedUtilityRespawnRetryTicks;
    private object? _generatedUtilityRespawnSocket;
    private string _generatedUtilityRespawnWorld = "";

    private object? GeneratedUtilityRespawnSocket => Main.netMode == NetmodeID.Server
        ? Netplay.Clients[Player.whoAmI]?.Socket : Netplay.Connection?.Socket;

    private void CaptureGeneratedUtilityRespawnScope()
    {
        _generatedUtilityRespawnSocket = GeneratedUtilityRespawnSocket;
        _generatedUtilityRespawnWorld = GeneratedItemRegistryService.CurrentWorldIdString();
    }

    private void EnsureGeneratedUtilityRespawnScope()
    {
        if ((_generatedUtilityAwaitingRespawnSync || _generatedUtilityServerRespawnObserved)
            && (!ReferenceEquals(_generatedUtilityRespawnSocket, GeneratedUtilityRespawnSocket)
                || _generatedUtilityRespawnWorld != GeneratedItemRegistryService.CurrentWorldIdString()))
            ClearGeneratedUtilityRespawnSync();
    }

    private void ClearGeneratedUtilityRespawnSync()
    {
        _generatedUtilityAwaitingRespawnSync = false;
        _generatedUtilityServerRespawnObserved = false;
        _generatedUtilityRespawnRequest = Guid.Empty;
        _generatedUtilityRespawnRetryTicks = 0;
        _generatedUtilityRespawnSocket = null;
        _generatedUtilityRespawnWorld = "";
    }

    private void CloseGeneratedUtilityRespawnSync()
    {
        _generatedUtilityServerRespawnObserved = false;
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer) return;
        _generatedUtilityAwaitingRespawnSync = true;
        CaptureGeneratedUtilityRespawnScope();
        // Repeated dead ticks invalidate the previous life's acknowledgement too.
        _generatedUtilityRespawnRequest = Guid.Empty;
        _generatedUtilityRespawnRetryTicks = 0;
    }

    public override void OnRespawn()
    {
        // Native Player.Spawn invokes this while dead is still true. Death and
        // spawn packets can be consumed without an intervening UpdateDead frame.
        // Idempotent retirement here is therefore required before acknowledging
        // a new life; <=20-minute contributions retain their existing policy.
        ClearAirJumpState();
        RetireGeneratedUtilityOnDeath();
        CaptureGeneratedUtilityRespawnScope();
        if (Main.netMode == NetmodeID.Server)
        {
            _generatedUtilityServerRespawnObserved = true;
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer) return;
        _generatedUtilityAwaitingRespawnSync = true;
        _generatedUtilityRespawnRequest = Guid.NewGuid();
        SendGeneratedUtilityRespawnRequest();
    }

    private void SendGeneratedUtilityRespawnRequest()
    {
        // Player.Spawn has already sent native message 12 on this same ordered
        // uplink before OnRespawn. The server may answer only after its spawn hook.
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.RequestGeneratedUtilityRespawnSync);
        packet.Write((byte)Player.whoAmI);
        packet.Write(_generatedUtilityRespawnRequest.ToByteArray());
        packet.Send();
        _generatedUtilityRespawnRetryTicks = 0;
    }

    private void TickGeneratedUtilityRespawnSync()
    {
        EnsureGeneratedUtilityRespawnScope();
        TickAirJumpPredictionRecovery();
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer
            || Player.dead || !_generatedUtilityAwaitingRespawnSync
            || _generatedUtilityRespawnRequest == Guid.Empty) return;
        // This counter only schedules retries. It never identifies a life or
        // reopens the barrier, and every retry retains the exact same nonce.
        if (++_generatedUtilityRespawnRetryTicks >= 60) SendGeneratedUtilityRespawnRequest();
    }

    private static Guid ReadGeneratedUtilityRespawnNonce(BinaryReader reader)
    {
        byte[] bytes = reader.ReadBytes(16);
        if (bytes.Length != 16) throw new EndOfStreamException();
        return new Guid(bytes);
    }

    public static void HandleGeneratedUtilityRespawnRequest(BinaryReader reader, int whoAmI)
    {
        byte playerId = reader.ReadByte();
        Guid nonce = ReadGeneratedUtilityRespawnNonce(reader);
        if (Main.netMode != NetmodeID.Server || playerId != whoAmI || playerId >= Main.maxPlayers
            || nonce == Guid.Empty) return;
        Player player = Main.player[playerId];
        if (player is null || !player.active || player.dead) return;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        owner.EnsureGeneratedUtilityRespawnScope();
        if (!owner._generatedUtilityServerRespawnObserved) return;
        // A nonce is correlation only, not client gameplay authority. The entire
        // reply is built from the server table after its native life transition.
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.GeneratedUtilityRespawnSync);
        packet.Write(nonce.ToByteArray());
        owner.WriteGeneratedBuffState(packet);
        packet.Send(whoAmI);
    }

    public static void HandleGeneratedUtilityRespawnSync(BinaryReader reader, int whoAmI)
    {
        Guid nonce = ReadGeneratedUtilityRespawnNonce(reader);
        byte playerId = reader.ReadByte();
        if (Main.netMode != NetmodeID.MultiplayerClient || whoAmI != 256
            || playerId != Main.myPlayer || playerId >= Main.maxPlayers) return;
        Player player = Main.player[playerId];
        if (player is null || !player.active || player.dead) return;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        owner.EnsureGeneratedUtilityRespawnScope();
        if (!owner._generatedUtilityAwaitingRespawnSync || nonce == Guid.Empty
            || owner._generatedUtilityRespawnRequest != nonce) return;
        // Decode atomically before clearing the fence. On this ordered downlink,
        // all snapshots emitted before this reply have already been consumed.
        owner.ReadGeneratedBuffStateCore(reader, acceptsRespawn: true);
    }
}
