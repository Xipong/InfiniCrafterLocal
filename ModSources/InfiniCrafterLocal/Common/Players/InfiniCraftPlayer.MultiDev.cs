#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

// AGENT MAP: admin-unlocked multi-dev lanes 2 and 3.
// Lane 1 deliberately remains the proven legacy craft state machine. These two
// isolated jobs add independent A/B escrows, request ids, tasks and refunds while
// reusing the same server-authoritative commit path. Each lane pins its exact
// LocalGenerator profile (llm_2 / llm_3); it never asks code to choose gameplay.
public sealed partial class InfiniCraftPlayer
{
    private sealed class MultiDevCraftJob
    {
        public int LaneIndex;
        public GeneratorClient.PreparedGenerationRequest Request = null!;
        public Task<GeneratedItemData?>? Task;
        public string Label = "";
        public string RequestId = "";
        public bool AwaitingServerCommit;
        public int ElapsedTicks;
        public int WaitTicks;
    }

    private readonly MultiDevCraftJob?[] _multiDevJobs = new MultiDevCraftJob?[2];
    private int _multiDevWindowCount = 1;

    public Item InputC = new();
    public Item InputD = new();
    public Item InputE = new();
    public Item InputF = new();

    public int MultiDevWindowCount => Math.Clamp(_multiDevWindowCount, 1, 3);
    public bool MultiDevCraftEnabled => MultiDevWindowCount > 1;
    public bool HasPendingExtraCrafts => _multiDevJobs[0] is not null || _multiDevJobs[1] is not null;
    public bool HasAnyCraftLanePending => HasPendingCraft || HasPendingExtraCrafts;

    public bool IsCraftLaneVisible(int laneIndex)
        => laneIndex >= 0 && laneIndex < MultiDevWindowCount;

    public bool IsCraftLanePending(int laneIndex)
        => laneIndex == 0 ? HasPendingCraft : laneIndex is 1 or 2 && _multiDevJobs[laneIndex - 1] is not null;

    public bool CanStartStationCraftLane(int laneIndex)
    {
        if (!IsCraftLaneVisible(laneIndex) || IsCraftLanePending(laneIndex) || HasPendingStationEscrowOperation)
            return false;
        int first = laneIndex * 2;
        return HasInputAt(first) && HasInputAt(first + 1);
    }

    public string CraftLaneLabel(int laneIndex)
    {
        if (laneIndex == 0)
            return CraftLabel;
        MultiDevCraftJob? job = laneIndex is 1 or 2 ? _multiDevJobs[laneIndex - 1] : null;
        return string.IsNullOrWhiteSpace(job?.Label) ? $"LLM {laneIndex + 1}" : job!.Label;
    }

    public float CraftLaneProgress(int laneIndex)
    {
        if (laneIndex == 0)
            return CraftProgress;
        MultiDevCraftJob? job = laneIndex is 1 or 2 ? _multiDevJobs[laneIndex - 1] : null;
        return job is null ? 0f : Math.Clamp(job.ElapsedTicks / (float)CraftDurationTicks, 0f, 1f);
    }

    public string CraftLaneStatus(int laneIndex)
    {
        if (laneIndex == 0)
        {
            if (!HasPendingCraft)
                return CanStartStationCraftLane(0) ? "Ready" : "Need A+B";
            if (IsWaitingForRetry)
                return $"Retry #{GenerationAttempt + 1} in {RetrySecondsLeft}s";
            return IsWaitingForModel ? "Waiting for LLM 1" : $"LLM 1 · {Math.Ceiling(TicksLeft / 60f)}s";
        }
        MultiDevCraftJob? job = laneIndex is 1 or 2 ? _multiDevJobs[laneIndex - 1] : null;
        if (job is null)
            return CanStartStationCraftLane(laneIndex) ? "Ready" : "Need A+B";
        if (job.AwaitingServerCommit)
            return $"Host · LLM {laneIndex + 1}";
        if (job.Task is null || !job.Task.IsCompleted)
            return job.ElapsedTicks >= CraftDurationTicks
                ? $"Waiting for LLM {laneIndex + 1}"
                : $"LLM {laneIndex + 1} · {Math.Ceiling(Math.Max(0, CraftDurationTicks - job.ElapsedTicks) / 60f)}s";
        return "Committing";
    }

    public bool TrySetMultiDevWindowCount(int requested, bool syncServer = true)
    {
        int normalized = Math.Clamp(requested, 1, 3);
        if (normalized < MultiDevWindowCount)
        {
            for (int lane = normalized; lane < 3; lane++)
            {
                if (IsCraftLanePending(lane) || HasInputAt(lane * 2) || HasInputAt(lane * 2 + 1))
                    return false;
            }
        }
        _multiDevWindowCount = normalized;
        if (syncServer && Main.netMode == NetmodeID.MultiplayerClient)
            SendMultiDevModeToServer(normalized);
        return true;
    }

    private void InitializeMultiDevCraftState()
    {
        InputC = NewAirItem();
        InputD = NewAirItem();
        InputE = NewAirItem();
        InputF = NewAirItem();
        _multiDevJobs[0] = null;
        _multiDevJobs[1] = null;
        _multiDevWindowCount = 1;
    }

    private bool HasInputAt(int index)
    {
        Item item = InputSlot(index);
        return item is not null && !item.IsAir;
    }

    private bool TryStartExtraCraftLane(int laneIndex)
    {
        if (laneIndex is < 1 or > 2 || !CanStartStationCraftLane(laneIndex))
            return false;

        int first = laneIndex * 2;
        Item a = InputSlot(first).Clone();
        Item b = InputSlot(first + 1).Clone();
        InputSlot(first).TurnToAir();
        InputSlot(first + 1).TurnToAir();
        string profileId = $"llm_{laneIndex + 1}";
        string requestId = Guid.NewGuid().ToString("N");

        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            var request = new GeneratorClient.PreparedGenerationRequest
            {
                ParentA = LocalParentName(a),
                ParentB = LocalParentName(b),
                RefundA = a.Clone(),
                RefundB = b.Clone(),
            };
            request.RefundA.stack = 1;
            request.RefundB.stack = 1;
            var job = new MultiDevCraftJob
            {
                LaneIndex = laneIndex,
                Request = request,
                Label = $"{request.ParentA} + {request.ParentB}",
                RequestId = requestId,
                AwaitingServerCommit = true,
            };
            _multiDevJobs[laneIndex - 1] = job;
            if (!SendServerCraftRequest(requestId, laneIndex, a, b))
            {
                _multiDevJobs[laneIndex - 1] = null;
                // The server already owns the real station escrow in multiplayer.
                // Restore only the client's mirrored slots so the player can retry;
                // refunding clones here would create a second ownership path.
                ref Item failedA = ref InputSlot(first);
                ref Item failedB = ref InputSlot(first + 1);
                failedA = a;
                failedB = b;
                return false;
            }
            return true;
        }

        try
        {
            GeneratorClient.PreparedGenerationRequest request = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.Prepare(
                a,
                b,
                Player,
                profileId,
                multiDevCraft: true);
            bool began = BeginExtraCraftLane(request, $"{request.ParentA} + {request.ParentB}", requestId, laneIndex, serverAuthoritative: false);
            if (!began)
            {
                RefundOne(a);
                RefundOne(b);
            }
            return began;
        }
        catch
        {
            RefundOne(a);
            RefundOne(b);
            return false;
        }
    }

    private bool BeginExtraCraftLane(
        GeneratorClient.PreparedGenerationRequest request,
        string label,
        string requestId,
        int laneIndex,
        bool serverAuthoritative)
    {
        if (laneIndex is < 1 or > 2 || _multiDevJobs[laneIndex - 1] is not null)
            return false;
        _multiDevJobs[laneIndex - 1] = new MultiDevCraftJob
        {
            LaneIndex = laneIndex,
            Request = request,
            Label = label,
            RequestId = requestId ?? "",
            AwaitingServerCommit = false,
            Task = Task.Run(() => global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.GeneratePreparedBlocking(request)),
        };
        return true;
    }

    private void TickMultiDevCrafts()
    {
        for (int slot = 0; slot < _multiDevJobs.Length; slot++)
        {
            MultiDevCraftJob? job = _multiDevJobs[slot];
            if (job is null)
                continue;
            job.ElapsedTicks++;
            job.WaitTicks++;

            if (job.AwaitingServerCommit)
            {
                if (job.WaitTicks % StationEscrowRetryIntervalTicks == 0)
                    SendServerCraftRequest(job.RequestId, job.LaneIndex, job.Request.RefundA, job.Request.RefundB);
                if (job.WaitTicks == RemoteServerCraftTimeoutTicks)
                    CombatText.NewText(Player.Hitbox, Color.Orange, $"Multi-dev lane {job.LaneIndex + 1}: ждём durable host outcome");
                continue;
            }
            if (job.Task is null || !job.Task.IsCompleted)
                continue;

            GeneratedItemData? data = null;
            try { data = job.Task.Result; } catch { }
            if (data is null)
            {
                string reason = job.Request.FailureIsFatal
                    ? (string.IsNullOrWhiteSpace(job.Request.FailureMessage) ? "recipe rejected" : job.Request.FailureMessage)
                    : "generator unavailable";
                if (Main.netMode == NetmodeID.Server && !string.IsNullOrWhiteSpace(job.RequestId))
                    CompleteExtraServerCraft(job, false, "", reason);
                else
                {
                    RefundOne(job.Request.RefundA);
                    RefundOne(job.Request.RefundB);
                }
                if (Main.netMode != NetmodeID.Server)
                    CombatText.NewText(Player.Hitbox, Color.OrangeRed, $"Multi-dev lane {job.LaneIndex + 1}: {reason}");
                _multiDevJobs[slot] = null;
                continue;
            }

            if (Main.netMode == NetmodeID.MultiplayerClient)
            {
                _multiDevJobs[slot] = null;
                continue;
            }
            if (SpawnGeneratedItemServerSide(Player, data, out string error))
            {
                CompleteExtraServerCraft(job, true, data.Name, "ok");
                RunLocalCraftReveal(Player, data);
            }
            else
            {
                string reason = string.IsNullOrWhiteSpace(error) ? "server commit failed" : error;
                if (Main.netMode == NetmodeID.Server && !string.IsNullOrWhiteSpace(job.RequestId))
                    CompleteExtraServerCraft(job, false, "", reason);
                else
                {
                    RefundOne(job.Request.RefundA);
                    RefundOne(job.Request.RefundB);
                }
            }
            _multiDevJobs[slot] = null;
        }
    }

    private void CompleteExtraServerCraft(MultiDevCraftJob job, bool success, string itemName, string message)
    {
        if (Main.netMode != NetmodeID.Server || string.IsNullOrWhiteSpace(job.RequestId))
            return;
        if (!CompleteServerCraftTransaction(job.RequestId, job.LaneIndex, success, itemName, message))
            return;
        SendCraftCommitResult(Player.whoAmI, job.RequestId, success, itemName ?? "", message ?? "");
    }

    private bool TryHandleExtraCraftCommit(string requestId, bool success, string itemName, string message)
    {
        for (int slot = 0; slot < _multiDevJobs.Length; slot++)
        {
            MultiDevCraftJob? job = _multiDevJobs[slot];
            if (job is null || !job.AwaitingServerCommit || !string.Equals(job.RequestId, requestId, StringComparison.Ordinal))
                continue;
            if (success)
            {
                ClearRemoteCraftMirror(job.LaneIndex);
                CombatText.NewText(Player.Hitbox, Color.Cyan, $"Lane {job.LaneIndex + 1}: {(string.IsNullOrWhiteSpace(itemName) ? "Generated Item" : itemName)}");
            }
            else
            {
                RestoreRemoteCraftMirror(job.LaneIndex, job.Request);
                CombatText.NewText(Player.Hitbox, Color.OrangeRed, $"Lane {job.LaneIndex + 1}: {(string.IsNullOrWhiteSpace(message) ? "craft failed" : message)}");
            }
            _multiDevJobs[slot] = null;
            return true;
        }
        return false;
    }

    private bool TryCancelExtraServerCraft(string requestId, string reason)
    {
        for (int slot = 0; slot < _multiDevJobs.Length; slot++)
        {
            MultiDevCraftJob? job = _multiDevJobs[slot];
            if (job is null || !string.Equals(job.RequestId, requestId, StringComparison.Ordinal))
                continue;
            CompleteExtraServerCraft(job, false, "", string.IsNullOrWhiteSpace(reason) ? "cancelled" : reason);
            _multiDevJobs[slot] = null;
            return true;
        }
        return false;
    }

    private void AbortMultiDevCraftsForWorldExit(bool refundLocally)
    {
        for (int slot = 0; slot < _multiDevJobs.Length; slot++)
        {
            MultiDevCraftJob? job = _multiDevJobs[slot];
            if (job is null)
                continue;
            if (refundLocally && Main.netMode == NetmodeID.MultiplayerClient && job.AwaitingServerCommit)
                SendExtraCraftCancel(job, "client_world_exit");
            else if (refundLocally)
            {
                RefundOne(job.Request.RefundA);
                RefundOne(job.Request.RefundB);
            }
            _multiDevJobs[slot] = null;
        }
    }

    private void AddMultiDevPendingRefunds(List<Terraria.ModLoader.IO.TagCompound> refunds, bool includeRemoteAwaiting)
    {
        foreach (MultiDevCraftJob? job in _multiDevJobs)
        {
            if (job is null || (job.AwaitingServerCommit && !includeRemoteAwaiting))
                continue;
            AddRefundTag(refunds, job.Request.RefundA);
            AddRefundTag(refunds, job.Request.RefundB);
        }
    }

    private void AddMultiDevPendingRemoteCrafts(List<Terraria.ModLoader.IO.TagCompound> pending)
    {
        foreach (MultiDevCraftJob? job in _multiDevJobs)
        {
            if (job is null || !job.AwaitingServerCommit)
                continue;
            AddPendingRemoteCraftTag(pending, job.LaneIndex, job.RequestId, job.Request);
        }
    }

    private void RestoreMultiDevPendingRemoteCraft(
        int laneIndex,
        string requestId,
        GeneratorClient.PreparedGenerationRequest request)
    {
        if (laneIndex is < 1 or > 2 || _multiDevJobs[laneIndex - 1] is not null)
            return;
        _multiDevWindowCount = Math.Max(_multiDevWindowCount, laneIndex + 1);
        _multiDevJobs[laneIndex - 1] = new MultiDevCraftJob
        {
            LaneIndex = laneIndex,
            Request = request,
            Label = $"{request.ParentA} + {request.ParentB}",
            RequestId = requestId,
            AwaitingServerCommit = true,
            WaitTicks = StationEscrowRetryIntervalTicks - 1,
        };
    }

    private void SendExtraCraftCancel(MultiDevCraftJob job, string reason)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || string.IsNullOrWhiteSpace(job.RequestId))
            return;
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketCancelServerCraft);
            packet.Write(job.RequestId);
            packet.Write(reason ?? "client_cancel");
            packet.Send();
        }
        catch { }
    }

    private bool SendServerCraftRequest(string requestId, int laneIndex, Item a, Item b)
    {
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketRequestServerCraft);
            packet.Write(_stationEscrowClientId);
            packet.Write(requestId ?? "");
            packet.Write((byte)Math.Clamp(laneIndex, 0, 2));
            WriteCraftItemRef(packet, a);
            WriteCraftItemRef(packet, b);
            packet.Send();
            return true;
        }
        catch { return false; }
    }

    private void SendMultiDevModeToServer(int count)
    {
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(InfiniNetPacketIds.SetMultiDevCraftMode);
            packet.Write((byte)Math.Clamp(count, 1, 3));
            packet.Send();
        }
        catch { }
    }

    public static void HandleSetMultiDevCraftModePacket(System.IO.BinaryReader reader, int whoAmI)
    {
        int count = Math.Clamp((int)reader.ReadByte(), 1, 3);
        if (Main.netMode != NetmodeID.Server || whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;
        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
            return;
        player.GetModPlayer<InfiniCraftPlayer>().TrySetMultiDevWindowCount(count, syncServer: false);
    }
}
