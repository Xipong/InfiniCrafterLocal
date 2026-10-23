#nullable enable
using System;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public enum CraftLaneOutcomeKind { None, Succeeded, Failed, Cancelled, TimedOut }
    public enum CraftLaneMaterialDisposition { Unobserved, LocalRefund, ServerRetained }
    public readonly record struct CraftLaneOutcome(CraftLaneOutcomeKind Kind, string Message, CraftLaneMaterialDisposition Materials = CraftLaneMaterialDisposition.Unobserved);
    private readonly CraftLaneOutcome[] _craftLaneOutcomes = new CraftLaneOutcome[3];
    private readonly int[] _craftLaneOutcomeTicks = new int[3];
    private readonly bool[] _remoteCraftCancelRequested = new bool[3];

    // Presentation only: never refresh authority, move materials, or retire workers.
    public CraftLaneOutcome GetCraftLaneOutcome(int laneIndex)
        => laneIndex is >= 0 and <= 2 ? _craftLaneOutcomes[laneIndex] : default;

    public bool HasPendingCraftRefunds => _deferredExitRefunds.Count > 0;

    public bool IsCraftLaneCancellationPending(int laneIndex)
        => laneIndex is >= 0 and <= 2 && _remoteCraftCancelRequested[laneIndex]
            && (laneIndex == 0 ? _awaitingServerCommit : _multiDevJobs[laneIndex - 1]?.AwaitingServerCommit == true);

    public bool IsCraftLaneWaitingForDelivery(int laneIndex)
        => Main.netMode != NetmodeID.MultiplayerClient && !_stationEscrowUsesRemoteAuthority
            && laneIndex is >= 0 and <= 2 && IsCraftLanePending(laneIndex)
            && !(laneIndex == 0 ? _awaitingServerCommit : _multiDevJobs[laneIndex - 1]?.AwaitingServerCommit == true)
            && HasReadyCraftResult(laneIndex == 0 ? _task : _multiDevJobs[laneIndex - 1]?.Task)
            && !HasReusableWorldItemSlot();

    private static bool HasReadyCraftResult(Task<GeneratedItemData?>? task)
        => task?.Status == TaskStatus.RanToCompletion && task.Result is not null;

    private void SetCraftLaneOutcome(int laneIndex, CraftLaneOutcomeKind kind, string message, CraftLaneMaterialDisposition materials = CraftLaneMaterialDisposition.Unobserved)
    {
        if (laneIndex is < 0 or > 2) return;
        string bounded = (message ?? "").Replace('\r', ' ').Replace('\n', ' ');
        if (kind is CraftLaneOutcomeKind.Failed or CraftLaneOutcomeKind.Cancelled or CraftLaneOutcomeKind.TimedOut
            && IsCraftLanePending(laneIndex) && (Main.netMode == NetmodeID.Server || _stationEscrowUsesRemoteAuthority))
            materials = CraftLaneMaterialDisposition.ServerRetained;
        if (kind == CraftLaneOutcomeKind.Succeeded && _craftLaneOutcomes[laneIndex].Kind != kind
            && !Main.dedServ && Main.netMode != NetmodeID.Server && Player.whoAmI == Main.myPlayer
            && Terraria.ModLoader.ModContent.GetInstance<Common.Config.InfiniGameplayQolConfig>().PlayCraftCompletionSound)
            Terraria.Audio.SoundEngine.PlaySound(SoundID.ResearchComplete, Player.Center);
        var outcome = new CraftLaneOutcome(kind, bounded[..Math.Min(bounded.Length, 240)], materials);
        RecordCraftHistory(laneIndex, outcome);
        _craftLaneOutcomes[laneIndex] = outcome;
        _craftLaneOutcomeTicks[laneIndex] = kind == CraftLaneOutcomeKind.None ? 0 : 30 * 60;
    }

    private void TickCraftLanePresentation()
    {
        // Count visible reading time, not time spent fighting or in another window.
        if (Main.netMode != NetmodeID.Server && (!Main.playerInventory || !Main.hasFocus
            || Main.hideUI || Main.mapFullscreen || Main.ingameOptionsWindow || Main.inFancyUI
            || Common.UI.RecipeJournalUISystem.IsOpen || Player.chest != -1 || Main.npcShop != 0)) return;
        for (int lane = 0; lane < 3; lane++)
            if (_craftLaneOutcomeTicks[lane] > 0 && --_craftLaneOutcomeTicks[lane] == 0)
                _craftLaneOutcomes[lane] = default;
    }

    // MP cancellation retains the exact request/mirror until the host outcome.
    // No new refund authority, packet type, or client-side material decision.
    public bool TryCancelCraftLane(int laneIndex)
    {
        if (laneIndex is < 0 or > 2 || !CanMutateStationInputs() || !IsCraftLanePending(laneIndex)) return false;
        return RetireCraftLane(laneIndex, "craft cancelled", CraftLaneOutcomeKind.Cancelled);
    }

    private bool RetireCraftLane(int laneIndex, string reason, CraftLaneOutcomeKind kind)
    {
        if (!IsCraftLanePending(laneIndex)) return false;
        if (laneIndex == 0)
        {
            if (_awaitingServerCommit)
            {
                _remoteCraftCancelRequested[0] = true;
                SendRemoteServerCraftCancel(reason);
                return true;
            }
            _request?.Cancel();
            if (IsServerAuthoritativeCraft) SendServerAuthoritativeResultIfNeeded(false, "", reason);
            else if (!_stationEscrowUsesRemoteAuthority) RefundIngredients();
            SetCraftLaneOutcome(0, kind, reason, !IsServerAuthoritativeCraft && !_stationEscrowUsesRemoteAuthority
                ? CraftLaneMaterialDisposition.LocalRefund : CraftLaneMaterialDisposition.Unobserved);
            ClearCraft();
            return true;
        }
        MultiDevCraftJob job = _multiDevJobs[laneIndex - 1]!;
        if (job.AwaitingServerCommit)
        {
            _remoteCraftCancelRequested[laneIndex] = true;
            SendExtraCraftCancel(job, reason);
            return true;
        }
        job.Request.Cancel();
        if (Main.netMode == NetmodeID.Server) CompleteExtraServerCraft(job, false, "", reason);
        else if (!_stationEscrowUsesRemoteAuthority)
        {
            RefundOne(job.Request.RefundA);
            RefundOne(job.Request.RefundB);
        }
        SetCraftLaneOutcome(laneIndex, kind, reason, Main.netMode != NetmodeID.Server && !_stationEscrowUsesRemoteAuthority
            ? CraftLaneMaterialDisposition.LocalRefund : CraftLaneMaterialDisposition.Unobserved);
        _multiDevJobs[laneIndex - 1] = null;
        return true;
    }
}
