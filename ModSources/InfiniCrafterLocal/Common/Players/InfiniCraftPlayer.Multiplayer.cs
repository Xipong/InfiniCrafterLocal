#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

// AGENT MAP: server-authoritative multiplayer craft protocol.
// Client station deposits are transferred through synchronized mouse slot 58 into
// server-owned A/B escrow. Craft requests carry compact refs, but the host consumes
// only those escrow slots, runs GeneratorClient, then sends ACK/FAIL.
// Never add a client-authored GeneratedItemData commit path here.
public sealed partial class InfiniCraftPlayer
{
    private enum StationEscrowAction : byte
    {
        Deposit = 1,
        TakeToMouse = 2,
        ReturnOne = 3,
        ReturnAll = 4,
    }

    private bool BeginRemoteServerCraft(Item a, Item b)
    {
        if (HasPendingCraft)
            return false;

        CaptureAudioSettingsSnapshot();

        string requestId = Guid.NewGuid().ToString("N");
        string parentA = LocalParentName(a);
        string parentB = LocalParentName(b);

        var refundA = a.Clone();
        refundA.stack = 1;
        var refundB = b.Clone();
        refundB.stack = 1;

        _request = new GeneratorClient.PreparedGenerationRequest
        {
            PayloadJson = "{}",
            ParentA = parentA,
            ParentB = parentB,
            RefundA = refundA,
            RefundB = refundB
        };
        _label = $"{parentA} + {parentB}";
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _serverRequestId = requestId;
        _awaitingServerCommit = true;
        _serverCraftWaitTicks = 0;
        _task = null;

        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketRequestServerCraft);
            packet.Write(requestId);
            WriteCraftItemRef(packet, a);
            WriteCraftItemRef(packet, b);
            packet.Send();
        }
        catch
        {
            ClearCraft();
            return false;
        }

        CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, "InfiniCraft: запрос крафта отправлен хосту");
        return true;
    }

    private bool BeginServerAuthoritativeCraft(GeneratorClient.PreparedGenerationRequest request, string label, string requestId)
    {
        if (HasPendingCraft)
            return false;

        _request = request;
        _label = label;
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _serverRequestId = requestId ?? "";
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;
        _task = null;

        StartGenerationTask("server_authoritative");
        return true;
    }

    private bool SendStationEscrowRequest(StationEscrowAction action, int index, Item item)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || HasPendingCraft || HasPendingStationEscrowOperation)
            return false;
        if (action != StationEscrowAction.ReturnAll && index is < 0 or > 1)
            return false;

        string operationId = Guid.NewGuid().ToString("N");
        _pendingStationEscrowOperationId = operationId;
        _pendingStationEscrowAction = (byte)action;
        _pendingStationEscrowIndex = index;
        _pendingStationEscrowWaitTicks = 0;
        if (action == StationEscrowAction.Deposit && item is not null && !item.IsAir)
        {
            _pendingStationEscrowItem = item.Clone();
            _pendingStationEscrowItem.stack = 1;
        }
        else
        {
            _pendingStationEscrowItem = null;
        }

        if (!FlushPendingStationEscrowRequest())
        {
            ClearPendingStationEscrowOperation();
            return false;
        }
        return true;
    }

    private bool ResendPendingStationEscrowRequest()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !HasPendingStationEscrowOperation || HasPendingCraft)
            return false;
        return FlushPendingStationEscrowRequest();
    }

    private bool FlushPendingStationEscrowRequest()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !HasPendingStationEscrowOperation)
            return false;
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketRequestStationEscrow);
            packet.Write(_pendingStationEscrowOperationId);
            packet.Write(_pendingStationEscrowAction);
            packet.Write((sbyte)_pendingStationEscrowIndex);
            if ((StationEscrowAction)_pendingStationEscrowAction == StationEscrowAction.Deposit)
            {
                Item refItem = _pendingStationEscrowItem is not null && !_pendingStationEscrowItem.IsAir
                    ? _pendingStationEscrowItem
                    : NewAirItem();
                WriteCraftItemRef(packet, refItem);
            }
            packet.Send();
            _pendingStationEscrowWaitTicks = 0;
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void TickPendingStationEscrow()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !HasPendingStationEscrowOperation)
            return;
        _pendingStationEscrowWaitTicks++;
        if (_pendingStationEscrowWaitTicks < StationEscrowRetryIntervalTicks)
            return;
        _pendingStationEscrowWaitTicks = 0;
        // Network drop / lost result: resend the same operationId until ACK/FAIL.
        ResendPendingStationEscrowRequest();
    }

    private void RestoreRejectedLocalDeposit(int index)
    {
        if (index is < 0 or > 1)
            return;

        Item restored;
        if (_pendingStationEscrowItem is not null && !_pendingStationEscrowItem.IsAir)
        {
            restored = _pendingStationEscrowItem.Clone();
            restored.stack = 1;
        }
        else
        {
            ref Item slot = ref InputSlot(index);
            if (slot is null || slot.IsAir)
                return;
            restored = slot.Clone();
            restored.stack = 1;
        }

        ref Item optimistic = ref InputSlot(index);
        if (optimistic is not null && !optimistic.IsAir)
            optimistic.TurnToAir();

        // Never blind-increment whatever currently sits on the cursor: only merge
        // onto a matching stack, put on empty mouse, or refund exact clone to inventory.
        if (CanRestoreRejectedDepositOntoMouse(restored))
        {
            if (Main.mouseItem is null || Main.mouseItem.IsAir)
                Main.mouseItem = restored;
            else
                Main.mouseItem.stack++;
            if (Player.inventory.Length > 58)
                Player.inventory[58] = Main.mouseItem.Clone();
            return;
        }

        RefundOne(restored);
    }

    private bool CanRestoreRejectedDepositOntoMouse(Item restored)
    {
        if (restored is null || restored.IsAir)
            return false;
        if (Main.mouseItem is null || Main.mouseItem.IsAir)
            return true;
        if (Main.mouseItem.type != restored.type || Main.mouseItem.prefix != restored.prefix)
            return false;
        if (Main.mouseItem.stack <= 0 || Main.mouseItem.stack >= Main.mouseItem.maxStack)
            return false;
        if (Main.mouseItem.ModItem is not null || restored.ModItem is not null)
        {
            // Generated/modded units only merge when stable generated ids match.
            if (!StationEscrowGeneratedIdsMatch(Main.mouseItem, restored))
                return false;
        }
        return true;
    }

    private static bool StationEscrowGeneratedIdsMatch(Item a, Item b)
    {
        string idA = "";
        string idB = "";
        try
        {
            if (a?.ModItem is GeneratedItem ga)
                idA = ga.Data?.Id ?? "";
            if (b?.ModItem is GeneratedItem gb)
                idB = gb.Data?.Id ?? "";
        }
        catch { }
        return string.Equals(idA ?? "", idB ?? "", StringComparison.Ordinal);
    }

    private void ClearPendingStationEscrowOperation()
    {
        _pendingStationEscrowOperationId = "";
        _pendingStationEscrowAction = 0;
        _pendingStationEscrowIndex = -1;
        _pendingStationEscrowItem = null;
        _pendingStationEscrowWaitTicks = 0;
    }

    private void ClearStationEscrowResultCache()
    {
        _stationEscrowResultCache.Clear();
        _stationEscrowResultOrder.Clear();
    }

    private void RememberStationEscrowResult(string operationId, StationEscrowAction action, int index, bool success, string message)
    {
        string key = operationId ?? "";
        if (string.IsNullOrWhiteSpace(key))
            return;
        if (!_stationEscrowResultCache.ContainsKey(key))
            _stationEscrowResultOrder.Enqueue(key);
        _stationEscrowResultCache[key] = new StationEscrowResultCacheEntry(
            (byte)action,
            index,
            success,
            message ?? "");
        while (_stationEscrowResultOrder.Count > MaxStationEscrowResultCacheEntries)
        {
            string expired = _stationEscrowResultOrder.Dequeue();
            _stationEscrowResultCache.Remove(expired);
        }
    }

    private bool TryReplayStationEscrowResult(
        string operationId,
        out StationEscrowAction action,
        out int index,
        out bool success,
        out string message)
    {
        action = 0;
        index = -1;
        success = false;
        message = "";
        if (string.IsNullOrWhiteSpace(operationId)
            || !_stationEscrowResultCache.TryGetValue(operationId, out StationEscrowResultCacheEntry? cached)
            || cached is null)
            return false;
        action = (StationEscrowAction)cached.Action;
        index = cached.Index;
        success = cached.Success;
        message = cached.Message ?? "";
        return true;
    }

    private void ApplyStationEscrowResult(string operationId, StationEscrowAction action, int index, bool success, string message)
    {
        if (!string.Equals(_pendingStationEscrowOperationId, operationId, StringComparison.Ordinal)
            || _pendingStationEscrowAction != (byte)action
            || _pendingStationEscrowIndex != index)
            return;

        if (!success)
        {
            if (action == StationEscrowAction.Deposit)
                RestoreRejectedLocalDeposit(index);
            ClearPendingStationEscrowOperation();
            Main.NewText(string.IsNullOrWhiteSpace(message) ? "InfiniCraft: escrow отклонён сервером" : $"InfiniCraft: {message}", 255, 120, 90);
            return;
        }

        if (action == StationEscrowAction.TakeToMouse && index is >= 0 and <= 1)
        {
            ref Item slot = ref InputSlot(index);
            Main.mouseItem = slot.Clone();
            slot.TurnToAir();
            if (Player.inventory.Length > 58)
                Player.inventory[58] = Main.mouseItem.Clone();
        }
        else if (action == StationEscrowAction.ReturnOne && index is >= 0 and <= 1)
        {
            ref Item slot = ref InputSlot(index);
            slot.TurnToAir();
        }
        else if (action == StationEscrowAction.ReturnAll)
        {
            InputA.TurnToAir();
            InputB.TurnToAir();
        }
        ClearPendingStationEscrowOperation();
    }

    public static void HandleStationEscrowResultPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        string operationId = reader.ReadString();
        StationEscrowAction action = (StationEscrowAction)reader.ReadByte();
        int index = reader.ReadSByte();
        bool success = reader.ReadBoolean();
        string message = reader.ReadString();
        if (Main.netMode != NetmodeID.MultiplayerClient || Main.LocalPlayer is null)
            return;
        Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().ApplyStationEscrowResult(operationId, action, index, success, message);
    }

    public static void HandleStationEscrowRequestPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        string operationId = reader.ReadString();
        StationEscrowAction action = (StationEscrowAction)reader.ReadByte();
        int index = reader.ReadSByte();
        CraftItemRef itemRef = action == StationEscrowAction.Deposit ? ReadCraftItemRef(reader) : default;
        if (Main.netMode != NetmodeID.Server || whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
        {
            SendStationEscrowResult(whoAmI, operationId, action, index, false, "игрок неактивен");
            return;
        }
        if (string.IsNullOrWhiteSpace(operationId))
        {
            SendStationEscrowResult(whoAmI, operationId, action, index, false, "пустой operationId");
            return;
        }

        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (modPlayer.TryReplayStationEscrowResult(operationId, out StationEscrowAction replayAction, out int replayIndex, out bool replaySuccess, out string replayMessage))
        {
            LogServerCraftTransaction(whoAmI, "station", "escrow_replay", $"op={operationId} action={(byte)replayAction} success={replaySuccess}");
            SendStationEscrowResult(whoAmI, operationId, replayAction, replayIndex, replaySuccess, replayMessage);
            return;
        }

        if (modPlayer.HasPendingCraft)
        {
            SendStationEscrowResult(whoAmI, operationId, action, index, false, "крафт уже запущен");
            return;
        }

        bool success;
        string error;
        switch (action)
        {
            case StationEscrowAction.Deposit:
                success = modPlayer.TryDepositServerMouseItem(index, itemRef, out error);
                break;
            case StationEscrowAction.TakeToMouse:
                success = modPlayer.TryTakeServerEscrowToMouse(index, out error);
                break;
            case StationEscrowAction.ReturnOne:
                success = modPlayer.TryReturnServerEscrowToInventory(index, out error);
                break;
            case StationEscrowAction.ReturnAll:
                success = modPlayer.TryReturnAllServerEscrowToInventory(out error);
                break;
            default:
                success = false;
                error = "неизвестное escrow-действие";
                break;
        }
        modPlayer.RememberStationEscrowResult(operationId, action, index, success, success ? "" : error);
        SendStationEscrowResult(whoAmI, operationId, action, index, success, success ? "" : error);
    }


    private void WriteGeneratedBuffState(System.IO.BinaryWriter writer)
    {
        writer.Write((byte)Player.whoAmI);
        writer.Write((byte)4); // state version
        writer.Write(_generatedBuffTicks);
        writer.Write(_generatedMiningSpeedMultiplier);
        writer.Write(_generatedLightStrength);
        writer.Write(_generatedLightColorName ?? "");
        writer.Write(_generatedOreSenseRadiusTiles);
        writer.Write(_generatedMovementSpeed);
        writer.Write(_generatedJumpBoost);
        writer.Write(_generatedManaRegen);
        writer.Write(_generatedLifeRegen);
        writer.Write(_generatedMobilityCooldownTicks);
        int buffCount = Math.Min(32, _activeGeneratedUtilityBuffs.Count);
        writer.Write((byte)buffCount);
        for (int index = 0; index < buffCount; index++)
            WriteGeneratedUtilityBuffEntry(writer, _activeGeneratedUtilityBuffs[index]);
    }

    private void ReadGeneratedBuffState(System.IO.BinaryReader reader)
    {
        byte version = reader.ReadByte();
        if (version != 4)
            throw new System.IO.InvalidDataException($"Unsupported generated utility state version {version}");
        _generatedBuffTicks = reader.ReadInt32();
        _generatedMiningSpeedMultiplier = reader.ReadSingle();
        _generatedLightStrength = reader.ReadSingle();
        _generatedLightColorName = reader.ReadString();
        _generatedOreSenseRadiusTiles = reader.ReadInt32();
        _generatedMovementSpeed = reader.ReadSingle();
        _generatedJumpBoost = reader.ReadSingle();
        _generatedManaRegen = reader.ReadInt32();
        _generatedLifeRegen = reader.ReadInt32();
        _generatedMobilityCooldownTicks = reader.ReadInt32();
        ClampGeneratedBuffState();
        _activeGeneratedUtilityBuffs.Clear();
        int buffCount = Math.Min(32, (int)reader.ReadByte());
        for (int index = 0; index < buffCount; index++)
            _activeGeneratedUtilityBuffs.Add(ReadGeneratedUtilityBuffEntry(reader));
    }

    private static void DiscardGeneratedBuffState(System.IO.BinaryReader reader)
    {
        byte version = reader.ReadByte();
        if (version != 4)
            throw new System.IO.InvalidDataException($"Unsupported generated utility state version {version}");
        _ = reader.ReadInt32();
        _ = reader.ReadSingle();
        _ = reader.ReadSingle();
        _ = reader.ReadString();
        _ = reader.ReadInt32();
        _ = reader.ReadSingle();
        _ = reader.ReadSingle();
        _ = reader.ReadInt32();
        _ = reader.ReadInt32();
        _ = reader.ReadInt32();
        int buffCount = Math.Min(32, (int)reader.ReadByte());
        for (int index = 0; index < buffCount; index++)
            DiscardGeneratedUtilityBuffEntry(reader);
    }

    private static void WriteGeneratedUtilityBuffEntry(System.IO.BinaryWriter writer, ActiveGeneratedUtilityBuff buff)
    {
        writer.Write(buff.Ticks);
        writer.Write(buff.MiningSpeedMultiplier);
        writer.Write(buff.EmitLightStrength);
        writer.Write(buff.LightColorName ?? "");
        writer.Write(buff.OreSenseRadiusTiles);
        writer.Write(buff.MovementSpeed);
        writer.Write(buff.JumpBoost);
        writer.Write(buff.ManaRegen);
        writer.Write(buff.LifeRegen);
    }

    private static ActiveGeneratedUtilityBuff ReadGeneratedUtilityBuffEntry(System.IO.BinaryReader reader)
    {
        int ticks = reader.ReadInt32();
        float miningSpeedMultiplier = reader.ReadSingle();
        float lightStrength = reader.ReadSingle();
        string lightColor = reader.ReadString().Trim();
        return new ActiveGeneratedUtilityBuff
        {
            Ticks = Math.Clamp(ticks, 1, 21600),
            MiningSpeedMultiplier = Math.Clamp(miningSpeedMultiplier, 0.25f, 4f),
            EmitLightStrength = Math.Clamp(lightStrength, 0f, 1.5f),
            LightColorName = lightColor[..Math.Min(lightColor.Length, 32)],
            OreSenseRadiusTiles = Math.Clamp(reader.ReadInt32(), 0, 60),
            MovementSpeed = Math.Clamp(reader.ReadSingle(), -0.5f, 2f),
            JumpBoost = Math.Clamp(reader.ReadSingle(), 0f, 8f),
            ManaRegen = Math.Clamp(reader.ReadInt32(), 0, 120),
            LifeRegen = Math.Clamp(reader.ReadInt32(), 0, 120),
        };
    }

    private static void DiscardGeneratedUtilityBuffEntry(System.IO.BinaryReader reader)
    {
        _ = reader.ReadInt32();
        _ = reader.ReadSingle();
        _ = reader.ReadSingle();
        _ = reader.ReadString();
        _ = reader.ReadInt32();
        _ = reader.ReadSingle();
        _ = reader.ReadSingle();
        _ = reader.ReadInt32();
        _ = reader.ReadInt32();
    }

    private void ClampGeneratedBuffState()
    {
        _generatedBuffTicks = Math.Clamp(_generatedBuffTicks, 0, 21600);
        _generatedMiningSpeedMultiplier = Math.Clamp(_generatedMiningSpeedMultiplier <= 0f ? 1f : _generatedMiningSpeedMultiplier, 0.25f, 4f);
        _generatedLightStrength = Math.Clamp(_generatedLightStrength, 0f, 1.5f);
        _generatedLightColorName = string.IsNullOrWhiteSpace(_generatedLightColorName) ? "" : _generatedLightColorName.Trim()[..Math.Min(_generatedLightColorName.Trim().Length, 32)];
        _generatedOreSenseRadiusTiles = Math.Clamp(_generatedOreSenseRadiusTiles, 0, 60);
        _generatedMovementSpeed = Math.Clamp(_generatedMovementSpeed, -0.5f, 2f);
        _generatedJumpBoost = Math.Clamp(_generatedJumpBoost, 0f, 8f);
        _generatedManaRegen = Math.Clamp(_generatedManaRegen, 0, 120);
        _generatedLifeRegen = Math.Clamp(_generatedLifeRegen, 0, 120);
        _generatedMobilityCooldownTicks = Math.Clamp(_generatedMobilityCooldownTicks, 0, 36000);
    }

    private bool GeneratedBuffStateDiffers(InfiniCraftPlayer other)
    {
        if (other is null) return true;

        bool activeNow = _generatedBuffTicks > 0;
        bool activeOld = other._generatedBuffTicks > 0;
        bool cooldownNow = _generatedMobilityCooldownTicks > 0;
        bool cooldownOld = other._generatedMobilityCooldownTicks > 0;
        // Do not sync every countdown tick. Remote clients can decrement their local
        // copy after one start/end packet; per-tick SendClientChanges would spam MP.
        if (activeNow != activeOld || cooldownNow != cooldownOld)
            return true;
        if (Math.Abs(_generatedBuffTicks - other._generatedBuffTicks) > 30)
            return true;
        if (Math.Abs(_generatedMobilityCooldownTicks - other._generatedMobilityCooldownTicks) > 30)
            return true;
        return Math.Abs(_generatedMiningSpeedMultiplier - other._generatedMiningSpeedMultiplier) > 0.001f
            || Math.Abs(_generatedLightStrength - other._generatedLightStrength) > 0.001f
            || !string.Equals(_generatedLightColorName, other._generatedLightColorName, StringComparison.Ordinal)
            || _generatedOreSenseRadiusTiles != other._generatedOreSenseRadiusTiles
            || Math.Abs(_generatedMovementSpeed - other._generatedMovementSpeed) > 0.001f
            || Math.Abs(_generatedJumpBoost - other._generatedJumpBoost) > 0.001f
            || _generatedManaRegen != other._generatedManaRegen
            || _generatedLifeRegen != other._generatedLifeRegen;
    }

    private void SendGeneratedBuffState(int toWho = -1, int fromWho = -1)
    {
        if (Main.netMode == NetmodeID.SinglePlayer)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketSyncGeneratedUtilityBuff);
        WriteGeneratedBuffState(packet);
        packet.Send(toWho, fromWho);
    }

    public override void SyncPlayer(int toWho, int fromWho, bool newPlayer)
    {
        SendGeneratedBuffState(toWho, fromWho);
    }

    public override void CopyClientState(ModPlayer targetCopy)
    {
        if (targetCopy is InfiniCraftPlayer clone)
        {
            clone._generatedBuffTicks = _generatedBuffTicks;
            clone._generatedMiningSpeedMultiplier = _generatedMiningSpeedMultiplier;
            clone._generatedLightStrength = _generatedLightStrength;
            clone._generatedLightColorName = _generatedLightColorName;
            clone._generatedOreSenseRadiusTiles = _generatedOreSenseRadiusTiles;
            clone._generatedMovementSpeed = _generatedMovementSpeed;
            clone._generatedJumpBoost = _generatedJumpBoost;
            clone._generatedManaRegen = _generatedManaRegen;
            clone._generatedLifeRegen = _generatedLifeRegen;
            clone._generatedMobilityCooldownTicks = _generatedMobilityCooldownTicks;
        }
    }

    public override void SendClientChanges(ModPlayer clientPlayer)
    {
        if (clientPlayer is InfiniCraftPlayer oldState && GeneratedBuffStateDiffers(oldState))
            SendGeneratedBuffState();
    }

    public static void HandleGeneratedUtilityBuffSyncPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        byte playerId = reader.ReadByte();
        if (playerId >= Main.maxPlayers)
        {
            DiscardGeneratedBuffState(reader);
            return;
        }
        if (Main.netMode == NetmodeID.Server && playerId != whoAmI)
        {
            DiscardGeneratedBuffState(reader);
            return;
        }
        Player player = Main.player[playerId];
        if (player is null || !player.active)
        {
            DiscardGeneratedBuffState(reader);
            return;
        }
        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (Main.netMode == NetmodeID.Server)
        {
            // Clients may request a resync by sending their predicted snapshot,
            // but none of its numbers are authoritative. Consume the packet and
            // rebroadcast the server-owned state built from canonical item data.
            DiscardGeneratedBuffState(reader);
            modPlayer.SendGeneratedBuffState(-1, whoAmI);
            return;
        }
        modPlayer.ReadGeneratedBuffState(reader);
    }

    private bool IsServerAuthoritativeCraft => Main.netMode == NetmodeID.Server && !_awaitingServerCommit && !string.IsNullOrWhiteSpace(_serverRequestId);

    private void SendServerAuthoritativeResultIfNeeded(bool success, string itemName, string message)
    {
        if (!IsServerAuthoritativeCraft)
            return;
        if (success)
            RememberServerCraftCommit(ServerCraftKey(Player.whoAmI, _serverRequestId), string.IsNullOrWhiteSpace(itemName) ? "Generated Item" : itemName);
        LogServerCraftTransaction(
            Player.whoAmI,
            _serverRequestId,
            success ? "committed" : "refunded",
            success ? $"item={SafeCraftLogValue(itemName, 80)}" : $"reason={SafeCraftLogValue(message, 120)}");
        SendCraftCommitResult(Player.whoAmI, _serverRequestId, success, itemName ?? "", message ?? "");
    }


    public void HandleCraftCommitResult(string requestId, bool success, string itemName, string message)
    {
        if (!_awaitingServerCommit || !string.Equals(_serverRequestId, requestId, StringComparison.Ordinal))
            return;

        if (success)
        {
            CombatText.NewText(Player.Hitbox, Color.Cyan, $"Discovered: {(string.IsNullOrWhiteSpace(itemName) ? "Generated Item" : itemName)}");
            ClearCraft();
            return;
        }

        // In multiplayer the server is authoritative for ingredient ownership.
        // Do not refund the client's transient UI escrow here: if the host rejected
        // before taking real slots, its inventory state will resync; if it already
        // took slots, it refunds server-side. Local refund here would reopen dup paths.
        CombatText.NewText(Player.Hitbox, Color.OrangeRed, string.IsNullOrWhiteSpace(message)
            ? "InfiniCraft: сервер отклонил крафт"
            : $"InfiniCraft: {message}");
        ClearCraft();
    }

    private static void RunLocalCraftReveal(Player player, GeneratedItemData data)
    {
        if (player is null || data is null) return;
        string name = string.IsNullOrWhiteSpace(data.Name) ? "Generated Item" : data.Name;

        CombatText.NewText(player.Hitbox, Color.Cyan, $"Discovered: {name}");
    }

    public static void HandleCraftCommitResultPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;

        string requestId = reader.ReadString();
        bool success = reader.ReadBoolean();
        string itemName = reader.ReadString();
        string message = reader.ReadString();
        Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().HandleCraftCommitResult(requestId, success, itemName, message);
    }

    public static void HandleRequestServerCraftPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        if (whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        string requestId = reader.ReadString();
        CraftItemRef aRef = ReadCraftItemRef(reader);
        CraftItemRef bRef = ReadCraftItemRef(reader);
        LogServerCraftTransaction(whoAmI, requestId, "received", $"aType={aRef.Type} bType={bRef.Type}");
        if (string.IsNullOrWhiteSpace(requestId))
        {
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", "reason=empty_request_id");
            SendCraftCommitResult(whoAmI, requestId, false, "", "пустой requestId");
            return;
        }

        string dedupeKey = "servercraft:" + whoAmI + ":" + requestId;
        lock (ServerCommittedCraftRequestsLock)
        {
            if (ServerCommittedCraftRequests.TryGetValue(dedupeKey, out string? knownName))
            {
                LogServerCraftTransaction(whoAmI, requestId, "committed", "result=duplicate_ack");
                SendCraftCommitResult(whoAmI, requestId, true, knownName ?? "", "duplicate ack");
                return;
            }
        }

        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
        {
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", "reason=inactive_player");
            SendCraftCommitResult(whoAmI, requestId, false, "", "игрок неактивен");
            return;
        }

        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (modPlayer.HasPendingCraft)
        {
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", "reason=already_pending");
            SendCraftCommitResult(whoAmI, requestId, false, "", "у игрока уже есть активный InfiniCraft");
            return;
        }
        if (IsServerCraftCancelled(whoAmI, requestId))
        {
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", "reason=already_cancelled");
            SendCraftCommitResult(whoAmI, requestId, false, "", "запрос уже отменён клиентом");
            return;
        }

        if (!modPlayer.TryTakeServerEscrowInput(0, aRef, out Item itemA, out string errorA))
        {
            modPlayer.TryReturnAllServerEscrowToInventory(out _);
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", $"ingredient=a source=stationA reason={SafeCraftLogValue(errorA, 120)}");
            SendCraftCommitResult(whoAmI, requestId, false, "", "сервер не подтвердил первый escrow-ингредиент: " + errorA);
            return;
        }
        if (!modPlayer.TryTakeServerEscrowInput(1, bRef, out Item itemB, out string errorB))
        {
            modPlayer.RefundOne(itemA);
            modPlayer.TryReturnAllServerEscrowToInventory(out _);
            LogServerCraftTransaction(whoAmI, requestId, "reserve_rejected", $"ingredient=b source=stationB aRefunded=true reason={SafeCraftLogValue(errorB, 120)}");
            SendCraftCommitResult(whoAmI, requestId, false, "", "сервер не подтвердил второй escrow-ингредиент: " + errorB);
            return;
        }
        LogServerCraftTransaction(whoAmI, requestId, "reserved", $"aSlot=stationA bSlot=stationB aType={itemA.type} bType={itemB.type}");

        GeneratorClient.PreparedGenerationRequest request;
        try
        {
            request = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.Prepare(itemA, itemB, player);
        }
        catch (Exception ex)
        {
            modPlayer.RefundOne(itemA);
            modPlayer.RefundOne(itemB);
            LogServerCraftTransaction(whoAmI, requestId, "refunded", $"reason=prepare_failed detail={SafeCraftLogValue(ex.Message, 120)}");
            SendCraftCommitResult(whoAmI, requestId, false, "", "хост не подготовил запрос: " + ex.Message);
            return;
        }
        if (!modPlayer.BeginServerAuthoritativeCraft(request, $"{request.ParentA} + {request.ParentB}", requestId))
        {
            modPlayer.RefundOne(itemA);
            modPlayer.RefundOne(itemB);
            LogServerCraftTransaction(whoAmI, requestId, "refunded", "reason=begin_failed");
            SendCraftCommitResult(whoAmI, requestId, false, "", "хост не начал server-authoritative craft");
            return;
        }
    }


    public static void HandleCancelServerCraftPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        if (whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        string requestId = reader.ReadString();
        try { _ = reader.ReadString(); } catch { } // optional cancel reason, protocol v0.4.218
        if (!HasCraftRequestId(requestId))
            return;

        MarkServerCraftCancelled(whoAmI, requestId);
        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
            return;
        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (modPlayer.IsServerAuthoritativeCraft && string.Equals(modPlayer._serverRequestId, requestId, StringComparison.Ordinal))
            modPlayer.CancelActiveServerAuthoritativeCraft("client cancelled/timeout");
        else
            SendCraftCommitResult(whoAmI, requestId, false, "", "запрос отменён");
    }

    private void SendRemoteServerCraftCancel(string reason)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !_awaitingServerCommit || !HasCraftRequestId(_serverRequestId))
            return;
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketCancelServerCraft);
            packet.Write(_serverRequestId);
            packet.Write(reason ?? "client_cancel");
            packet.Send();
        }
        catch { }
    }

    private void CancelActiveServerAuthoritativeCraft(string reason)
    {
        if (!IsServerAuthoritativeCraft)
            return;
        RefundIngredients();
        SendServerAuthoritativeResultIfNeeded(false, "", string.IsNullOrWhiteSpace(reason) ? "server craft cancelled" : reason);
        ClearCraft();
    }

    private static string ServerCraftKey(int playerId, string requestId)
        => "servercraft:" + playerId + ":" + NormalizeCraftRequestId(requestId);

    private static string SafeCraftLogValue(string? value, int maxLength)
    {
        string safe = (value ?? "").Replace('\r', ' ').Replace('\n', ' ').Trim();
        if (safe.Length > maxLength)
            safe = safe[..maxLength];
        return safe;
    }

    private static void LogServerCraftTransaction(int playerId, string requestId, string phase, string details)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        try
        {
            string rid = SafeCraftLogValue(requestId, 64);
            string safePhase = SafeCraftLogValue(phase, 32);
            string safeDetails = SafeCraftLogValue(details, 240);
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger.Info(
                $"[InfiniCraftTx] player={playerId} request={rid} phase={safePhase} {safeDetails}");
        }
        catch { }
    }

    private static void RememberServerCraftCommit(string key, string itemName)
    {
        lock (ServerCommittedCraftRequestsLock)
        {
            if (!ServerCommittedCraftRequests.ContainsKey(key))
                ServerCommittedCraftRequestOrder.Enqueue(key);
            ServerCommittedCraftRequests[key] = itemName;
            while (ServerCommittedCraftRequestOrder.Count > MaxServerCraftRequestCacheEntries)
                ServerCommittedCraftRequests.Remove(ServerCommittedCraftRequestOrder.Dequeue());
        }
    }

    private static void MarkServerCraftCancelled(int playerId, string requestId)
    {
        if (!HasCraftRequestId(requestId))
            return;
        lock (ServerCommittedCraftRequestsLock)
        {
            string key = ServerCraftKey(playerId, requestId);
            if (ServerCancelledCraftRequests.Add(key))
                ServerCancelledCraftRequestOrder.Enqueue(key);
            while (ServerCancelledCraftRequestOrder.Count > MaxServerCraftRequestCacheEntries)
                ServerCancelledCraftRequests.Remove(ServerCancelledCraftRequestOrder.Dequeue());
        }
    }

    private static bool IsServerCraftCancelled(int playerId, string requestId)
    {
        if (!HasCraftRequestId(requestId))
            return false;
        lock (ServerCommittedCraftRequestsLock)
            return ServerCancelledCraftRequests.Contains(ServerCraftKey(playerId, requestId));
    }

    private readonly struct CraftItemRef
    {
        public CraftItemRef(int type, int prefix, int stack, string generatedId, string displayName)
        {
            Type = type;
            Prefix = prefix;
            Stack = stack;
            GeneratedId = generatedId ?? "";
            DisplayName = displayName ?? "";
        }

        public int Type { get; }
        public int Prefix { get; }
        public int Stack { get; }
        public string GeneratedId { get; }
        public string DisplayName { get; }
    }

    private static string LocalParentName(Item item)
    {
        try
        {
            if (item?.ModItem is GeneratedItem generated && !string.IsNullOrWhiteSpace(generated.Data?.Name))
                return generated.Data.Name;
            return string.IsNullOrWhiteSpace(item?.Name) ? "Unknown" : item.Name;
        }
        catch { return "Unknown"; }
    }

    private static void WriteCraftItemRef(System.IO.BinaryWriter writer, Item item)
    {
        string generatedId = "";
        string displayName = "";
        try
        {
            displayName = LocalParentName(item);
            if (item?.ModItem is GeneratedItem generated)
                generatedId = generated.Data?.Id ?? "";
        }
        catch { }

        writer.Write(item?.type ?? ItemID.None);
        writer.Write((int)(item?.prefix ?? InfiniTerrariaSentinels.NoPrefix));
        writer.Write(NormalizeCraftStack(item?.stack ?? 1));
        writer.Write(generatedId ?? "");
        writer.Write(displayName ?? "");
    }

    private static CraftItemRef ReadCraftItemRef(System.IO.BinaryReader reader)
    {
        return new CraftItemRef(
            reader.ReadInt32(),
            reader.ReadInt32(),
            reader.ReadInt32(),
            reader.ReadString(),
            reader.ReadString());
    }

    private bool TryDepositServerMouseItem(int index, CraftItemRef itemRef, out string error)
    {
        error = "";
        if (Main.netMode != NetmodeID.Server || index is < 0 or > 1 || Player.inventory.Length <= 58)
        {
            error = "некорректный server escrow deposit";
            return false;
        }
        ref Item target = ref InputSlot(index);
        if (target is not null && !target.IsAir)
        {
            error = "escrow-слот уже занят";
            return false;
        }

        Item source = Player.inventory[58];
        if (source is null || source.IsAir || source.stack <= 0)
        {
            error = "server mouse slot 58 пуст";
            return false;
        }
        if (source.type != itemRef.Type || source.prefix != itemRef.Prefix || !InfiniCore.IsValidIngredient(source))
        {
            error = "server mouse item не совпал с deposit intent";
            return false;
        }
        if (!GeneratedIdentityMatches(source, itemRef.GeneratedId, out _))
        {
            error = "generated id mouse item не совпал с registry";
            return false;
        }

        target = source.Clone();
        target.stack = 1;
        source.stack--;
        if (source.stack <= 0)
            source.TurnToAir();
        SyncServerMouseSlot();
        LogServerCraftTransaction(Player.whoAmI, "station", "escrow_deposited", $"input={index} type={target.type} mouseSlot=58");
        return true;
    }

    private bool TryTakeServerEscrowToMouse(int index, out string error)
    {
        error = "";
        if (Main.netMode != NetmodeID.Server || index is < 0 or > 1 || Player.inventory.Length <= 58)
        {
            error = "некорректный server escrow withdraw";
            return false;
        }
        if (!Player.inventory[58].IsAir)
        {
            error = "курсор уже занят";
            return false;
        }
        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
        {
            error = "escrow-слот пуст";
            return false;
        }
        Player.inventory[58] = slot.Clone();
        slot.TurnToAir();
        SyncServerMouseSlot();
        return true;
    }

    private bool TryReturnServerEscrowToInventory(int index, out string error)
    {
        error = "";
        if (Main.netMode != NetmodeID.Server || index is < 0 or > 1)
        {
            error = "некорректный server escrow return";
            return false;
        }
        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
        {
            error = "escrow-слот пуст";
            return false;
        }
        Item refund = slot.Clone();
        slot.TurnToAir();
        RefundOne(refund);
        return true;
    }

    private bool TryReturnAllServerEscrowToInventory(out string error)
    {
        error = "";
        bool returned = false;
        if (HasInputA)
        {
            Item refund = InputA.Clone();
            InputA.TurnToAir();
            RefundOne(refund);
            returned = true;
        }
        if (HasInputB)
        {
            Item refund = InputB.Clone();
            InputB.TurnToAir();
            RefundOne(refund);
            returned = true;
        }
        if (!returned)
            error = "server escrow уже пуст";
        return returned;
    }

    private bool TryTakeServerEscrowInput(int index, CraftItemRef itemRef, out Item ingredient, out string error)
    {
        ingredient = NewAirItem();
        error = "";
        if (index is < 0 or > 1)
        {
            error = "некорректный escrow index";
            return false;
        }
        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir || slot.stack <= 0)
        {
            error = $"server escrow input {index} пуст";
            return false;
        }
        if (slot.type != itemRef.Type || slot.prefix != itemRef.Prefix || !InfiniCore.IsValidIngredient(slot))
        {
            error = $"server escrow input {index} не совпал с craft intent";
            return false;
        }
        if (!GeneratedIdentityMatches(slot, itemRef.GeneratedId, out _))
        {
            error = $"generated id escrow input {index} не совпал";
            return false;
        }
        ingredient = slot.Clone();
        ingredient.stack = 1;
        slot.TurnToAir();
        return true;
    }

    private void SyncServerMouseSlot()
    {
        if (Player.inventory.Length <= 58)
            return;
        Player.inventory[58].NetStateChanged();
        NetMessage.SendData(MessageID.SyncEquipment, -1, -1, null, Player.whoAmI, 58);
    }

    private static bool GeneratedIdentityMatches(Item slot, string generatedId, out bool generatedMismatch)
    {
        generatedMismatch = false;
        string expected = (generatedId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(expected))
            return slot.ModItem is not GeneratedItem;

        if (slot.ModItem is not GeneratedItem generated)
        {
            generatedMismatch = true;
            return false;
        }
        string actual = generated.Data?.Id ?? "";
        bool ok = string.Equals(actual, expected, StringComparison.Ordinal);
        generatedMismatch = !ok;
        return ok;
    }

    public static void ClearServerCommitCache()
    {
        lock (ServerCommittedCraftRequestsLock)
        {
            ServerCommittedCraftRequests.Clear();
            ServerCancelledCraftRequests.Clear();
            ServerCommittedCraftRequestOrder.Clear();
            ServerCancelledCraftRequestOrder.Clear();
        }

        // Also drop per-player escrow replay caches on unload/world teardown.
        try
        {
            for (int i = 0; i < Main.maxPlayers; i++)
            {
                Player player = Main.player[i];
                if (player is null || !player.active)
                    continue;
                player.GetModPlayer<InfiniCraftPlayer>().ClearStationEscrowResultCache();
            }
        }
        catch { }
    }

    private static void SendStationEscrowResult(int toClient, string operationId, StationEscrowAction action, int index, bool success, string message)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketStationEscrowResult);
        packet.Write(operationId ?? "");
        packet.Write((byte)action);
        packet.Write((sbyte)index);
        packet.Write(success);
        packet.Write(message ?? "");
        packet.Send(toClient);
    }

    private static void SendCraftCommitResult(int toClient, string requestId, bool success, string itemName, string message)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketCraftCommitResult);
        packet.Write(requestId ?? "");
        packet.Write(success);
        packet.Write(itemName ?? "");
        packet.Write(message ?? "");
        packet.Send(toClient);
    }

    private static void StampHostAssetSyncMetadata(GeneratedItemData data)
    {
        // Server-authoritative MP craft: the host owns LocalGenerator and the
        // source item/projectile dumps. Clients receive the finished generated
        // item plus final asset filenames/base URL, then hydrate PNG/JSON from
        // the host over HTTP automatically.
        if (data is null)
            return;

        data.RecipeMeta ??= new RecipeMetaSpec();
        // Transport metadata is not gameplay authorship.  Always restamp it on the
        // host before MP commit so old localhost/Radmin URLs from earlier sessions do
        // not strand already-generated sprites on friends.
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.StampAssetTransportMetadata(data, refreshBaseUrl: true);

        var files = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
        if (files.Length > 0)
            data.RecipeMeta.AssetFiles = files;
    }

    private static bool SpawnGeneratedItemServerSide(Player player, GeneratedItemData data, out string error)
    {
        error = "";
        try
        {
            if (data is null)
            {
                error = "пустой предмет";
                return false;
            }

            StampHostAssetSyncMetadata(data);

            bool asArmorProxy = global::InfiniCrafterLocal.Content.Items.GeneratedArmorItemTypes.CanRepresent(data);
            int itemType = asArmorProxy
                ? global::InfiniCrafterLocal.Content.Items.GeneratedArmorItemTypes.ItemTypeFor(data)
                : ModContent.ItemType<GeneratedItem>();
            int index = Item.NewItem(player.GetSource_Misc("InfiniCraft"), player.Hitbox, itemType);
            if (index < 0 || index >= Main.maxItems)
            {
                error = "Item.NewItem не вернул предмет";
                return false;
            }

            if (Main.item[index].ModItem is not GeneratedItem generated)
            {
                error = "Item.NewItem не вернул GeneratedItem";
                return false;
            }
            generated.SetData(data);
            int craftYield = Math.Clamp(data.Gameplay?.CraftYield ?? 1, 1, Math.Max(1, data.Gameplay?.MaxStack ?? 1));
            Main.item[index].stack = craftYield;

            // Commit the canonical definition before vanilla item sync. The registry queues
            // compressed definition chunks; clients request only hash-verified final PNGs.
            // There is deliberately no second filename/base-URL broadcast.
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.PublishGeneratedItem(data);
            if (Main.netMode != NetmodeID.SinglePlayer)
                NetMessage.SendData(MessageID.SyncItem, -1, -1, null, index);
            return true;
        }
        catch (Exception ex)
        {
            error = ex.Message;
            return false;
        }
    }

}
