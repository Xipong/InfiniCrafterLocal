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

// AGENT MAP: local craft lifecycle and recovery state machine.
// Owns in-flight generator task, retry/cache recovery, refunds, and commit cleanup.
// It should call GeneratorClient/registry services; it should not author gameplay
// or accept client-generated authoritative data.
public sealed partial class InfiniCraftPlayer
{
    private const string ReadOnlyRemoteStationClaimSaveKey = "infiniReadOnlyRemoteStationClaimV1";
    private const string DormantRemoteStationClaimsSaveKey = "infiniDormantRemoteStationClaimsV1";
    private const string StationOriginScopeSaveKey = "infiniStationEscrowOriginScopeV1";
    private string _stationEscrowOriginScope = "";
    private TagCompound? _readOnlyRemoteStationClaim;
    private readonly List<TagCompound> _dormantRemoteStationClaims = new();
    private TagCompound? _activeRemoteStationClaim;

    private IEnumerable<TagCompound> DormantRemoteStationClaims()
    {
        if (_readOnlyRemoteStationClaim is not null) yield return _readOnlyRemoteStationClaim;
        foreach (TagCompound claim in _dormantRemoteStationClaims) yield return claim;
    }

    private void RetainDormantRemoteStationClaim(TagCompound claim)
    {
        if (_readOnlyRemoteStationClaim is null) _readOnlyRemoteStationClaim = claim;
        else _dormantRemoteStationClaims.Add(claim);
    }

    internal bool EnsureRemoteStationAuthority()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return false;
        string current = Common.Systems.GeneratedStationEscrowStateSystem.AuthorityScope;
        if (!Common.Systems.GeneratedStationEscrowStateSystem.IsExactAuthorityScope(current))
            return false;
        if (_stationEscrowUsesRemoteAuthority && !string.Equals(_stationEscrowOriginScope, current, StringComparison.Ordinal))
            ParkRemoteStationClaim();
        if (!_stationEscrowUsesRemoteAuthority)
        {
            // Foreign/unscoped history stays raw and cannot confer authority, but
            // it must not disable unrelated fresh inventory work on this world.
            TagCompound[] matching = DormantRemoteStationClaims().Where(claim =>
                claim.ContainsKey(StationOriginScopeSaveKey) && claim[StationOriginScopeSaveKey] is string scope
                && string.Equals(scope, current, StringComparison.Ordinal)).ToArray();
            if (matching.Length > 1) return false; // Never choose/merge ambiguous claims.
            if (matching.Length == 1)
            {
                if (HasAnyInput || HasAnyCraftLanePending || HasPendingStationEscrowOperation) return false;
                TagCompound retained = matching[0];
                try { RestoreScopedRemoteStationClaim(retained); }
                catch
                {
                    for (int index = 0; index < 6; index++) InputSlot(index).TurnToAir();
                    ClearPendingStationEscrowOperation(); ClearCraft(); InitializeMultiDevCraftState();
                    _stationEscrowUsesRemoteAuthority = false; _stationEscrowOriginScope = "";
                    return false;
                }
                _activeRemoteStationClaim = (TagCompound)retained.Clone();
                if (ReferenceEquals(retained, _readOnlyRemoteStationClaim)) _readOnlyRemoteStationClaim = null;
                else _dormantRemoteStationClaims.Remove(retained);
            }
        }
        _stationEscrowOriginScope = current;
        return true;
    }

    private bool CanMutateStationInputs()
    {
        if (Main.netMode == NetmodeID.MultiplayerClient)
            return EnsureRemoteStationAuthority();
        return Main.netMode == NetmodeID.Server || !_stationEscrowUsesRemoteAuthority;
    }

    private TagCompound CaptureRemoteStationClaim()
    {
        // Keep unknown literal fields from an exactly restored claim through its
        // next park; refresh only live bookkeeping, never a foreign claim.
        var claim = _activeRemoteStationClaim is null ? new TagCompound() : (TagCompound)_activeRemoteStationClaim.Clone();
        claim.Remove("infiniPendingStationEscrow");
        claim["infiniStationEscrowClientId"] = _stationEscrowClientId;
        claim["infiniStationEscrowRemoteAuthority"] = true;
        claim[StationOriginScopeSaveKey] = _stationEscrowOriginScope;
        var mirror = new List<TagCompound>();
        for (int index = 0; index < 6; index++)
            if (HasInputAt(index)) mirror.Add(new TagCompound { ["index"] = index, ["item"] = ItemIO.Save(InputSlot(index)) });
        claim["infiniStationEscrowMirror"] = mirror;
        if (HasPendingStationEscrowOperation)
        {
            var pending = new TagCompound { ["operationId"] = _pendingStationEscrowOperationId,
                ["action"] = (int)_pendingStationEscrowAction, ["index"] = _pendingStationEscrowIndex };
            if (_pendingStationEscrowItem is not null && !_pendingStationEscrowItem.IsAir)
                pending["item"] = ItemIO.Save(_pendingStationEscrowItem);
            claim["infiniPendingStationEscrow"] = pending;
        }
        claim["infiniPendingRemoteCrafts"] = SavePendingRemoteCrafts();
        return claim;
    }

    private void ParkRemoteStationClaim()
    {
        if (!_stationEscrowUsesRemoteAuthority || Main.netMode == NetmodeID.Server)
            return;
        // Capture before retiring the active mirror. There is no local refund and
        // no cancellation against whichever unrelated server is now connected.
        RetainDormantRemoteStationClaim(CaptureRemoteStationClaim());
        _activeRemoteStationClaim = null;
        for (int index = 0; index < 6; index++) InputSlot(index).TurnToAir();
        ClearPendingStationEscrowOperation();
        ClearCraft();
        InitializeMultiDevCraftState();
        _stationEscrowUsesRemoteAuthority = false;
        _stationEscrowOriginScope = "";
    }

    private void RefreshRemoteStationAuthority()
    {
        if (_stationEscrowUsesRemoteAuthority && Main.netMode != NetmodeID.Server
            && (Main.netMode != NetmodeID.MultiplayerClient
                || !Common.Systems.GeneratedStationEscrowStateSystem.IsExactAuthorityScope(_stationEscrowOriginScope)))
            ParkRemoteStationClaim();
        if (Main.netMode == NetmodeID.MultiplayerClient) EnsureRemoteStationAuthority();
    }

    private void RestoreScopedRemoteStationClaim(TagCompound tag)
    {
        _stationEscrowClientId = Common.Systems.GeneratedStationEscrowStateSystem.NormalizeClientId(tag.GetString("infiniStationEscrowClientId"));
        if (_stationEscrowClientId.Length == 0)
            throw new InvalidOperationException("Invalid remote claim owner");
        _stationEscrowOriginScope = tag.GetString(StationOriginScopeSaveKey);
        _stationEscrowUsesRemoteAuthority = true;
        foreach (TagCompound row in tag.GetList<TagCompound>("infiniStationEscrowMirror"))
        {
            int index = row.GetInt("index");
            if (index is < 0 or > 5 || !row.ContainsKey("item")) continue;
            Item item = ItemIO.Load(row.GetCompound("item"));
            if (item is not null && !item.IsAir && item.stack > 0) InputSlot(index) = item.Clone();
        }
        if (tag.ContainsKey("infiniPendingStationEscrow"))
        {
            TagCompound pending = tag.GetCompound("infiniPendingStationEscrow");
            string operationId = pending.GetString("operationId");
            int action = pending.GetInt("action"), index = pending.GetInt("index");
            if (operationId.Length == 32 && operationId.All(Uri.IsHexDigit) && action is >= 1 and <= 4 && index is >= -1 and <= 5)
            {
                _pendingStationEscrowOperationId = operationId; _pendingStationEscrowAction = (byte)action;
                _pendingStationEscrowIndex = index; _pendingStationEscrowWaitTicks = 0;
                _pendingStationEscrowItem = pending.ContainsKey("item") ? ItemIO.Load(pending.GetCompound("item")) : null;
            }
        }
        if (tag.ContainsKey("infiniPendingRemoteCrafts")) RestorePendingRemoteCrafts(tag.GetList<TagCompound>("infiniPendingRemoteCrafts"));
    }

    private static string NormalizeCraftRequestId(string? requestId)
        => (requestId ?? string.Empty).Trim();

    private static bool HasCraftRequestId(string? requestId)
        => NormalizeCraftRequestId(requestId).Length > 0;

    private static int NormalizeCraftStack(int stack)
        => stack < 1 ? 1 : stack;


    public override void Initialize()
    {
        InputA = NewAirItem();
        InputB = NewAirItem();
        InitializeMultiDevCraftState();
        _stationEscrowClientId = Guid.NewGuid().ToString("N");
        _stationEscrowUsesRemoteAuthority = false;
        _stationEscrowOriginScope = "";
        _readOnlyRemoteStationClaim = null;
        _dormantRemoteStationClaims.Clear();
        _activeRemoteStationClaim = null;
        ClearPendingStationEscrowOperation();
    }

    public override void OnEnterWorld()
    {
        if (InputA is null) InputA = NewAirItem();
        if (InputB is null) InputB = NewAirItem();
        // A half-open remote escrow operation is durable and must resend the same
        // operationId after reconnect. Clearing it here loses the exact optimistic unit.
        _pendingStationEscrowWaitTicks = 0;
        RefreshRemoteStationAuthority();
        if (Main.netMode == NetmodeID.MultiplayerClient)
            ResendPendingRemoteCrafts();
        // Late-join catch-up: make sure this client has the generated-item registry
        // before it sees someone else use an already-crafted item.
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
        _registrySyncRetryTicks = 5 * 60;
        _registrySyncRetryStep = 0;
        RememberPositiveAudioSettings();
        RestoreDeferredExitRefunds();
    }

    public override void SaveData(TagCompound tag)
    {
        _pendingRefundSavedForWorldExit = false;
        _pendingRemoteCraftSavedForWorldExit = false;
        try
        {
            RefreshRemoteStationAuthority();
            if (_readOnlyRemoteStationClaim is not null)
                tag[ReadOnlyRemoteStationClaimSaveKey] = _readOnlyRemoteStationClaim.Clone();
            if (_dormantRemoteStationClaims.Count > 0)
                tag[DormantRemoteStationClaimsSaveKey] = _dormantRemoteStationClaims.Select(claim => (TagCompound)claim.Clone()).ToList();
            if (_stationEscrowUsesRemoteAuthority)
                foreach (var entry in CaptureRemoteStationClaim()) tag[entry.Key] = entry.Value;
            if (string.IsNullOrWhiteSpace(_stationEscrowClientId))
                _stationEscrowClientId = Guid.NewGuid().ToString("N");
            tag["infiniStationEscrowClientId"] = _stationEscrowClientId;
            tag["infiniStationEscrowRemoteAuthority"] = _stationEscrowUsesRemoteAuthority;
            if (_stationEscrowUsesRemoteAuthority) tag[StationOriginScopeSaveKey] = _stationEscrowOriginScope;
            if (_stationEscrowUsesRemoteAuthority)
            {
                var mirror = new List<TagCompound>();
                for (int index = 0; index < 6; index++)
                {
                    ref Item slot = ref InputSlot(index);
                    if (slot is null || slot.IsAir || slot.stack <= 0)
                        continue;
                    mirror.Add(new TagCompound { ["index"] = index, ["item"] = ItemIO.Save(slot) });
                }
                tag["infiniStationEscrowMirror"] = mirror;
            }
            if (HasPendingStationEscrowOperation)
            {
                var pending = new TagCompound
                {
                    ["operationId"] = _pendingStationEscrowOperationId,
                    ["action"] = (int)_pendingStationEscrowAction,
                    ["index"] = _pendingStationEscrowIndex,
                };
                if (_pendingStationEscrowItem is not null && !_pendingStationEscrowItem.IsAir)
                    pending["item"] = ItemIO.Save(_pendingStationEscrowItem);
                tag["infiniPendingStationEscrow"] = pending;
            }
            List<TagCompound> remoteCrafts = SavePendingRemoteCrafts();
            if (remoteCrafts.Count > 0)
            {
                tag["infiniPendingRemoteCrafts"] = remoteCrafts;
                _pendingRemoteCraftSavedForWorldExit = true;
            }
            var refunds = PendingRefundTagsForSave();
            if (refunds.Count > 0)
            {
                tag["infiniPendingCraftRefunds"] = refunds;
                tag["infiniPendingCraftLabel"] = CraftLabel;
                _pendingRefundSavedForWorldExit = true;
            }
        }
        catch
        {
            // Never let the station refund backup corrupt/brick the player file.
            _pendingRefundSavedForWorldExit = false;
            _pendingRemoteCraftSavedForWorldExit = false;
        }
    }

    public override void LoadData(TagCompound tag)
    {
        _deferredExitRefunds.Clear();
        try
        {
            string clientId = tag.ContainsKey("infiniStationEscrowClientId")
                ? tag.GetString("infiniStationEscrowClientId")
                : "";
            _stationEscrowClientId = Common.Systems.GeneratedStationEscrowStateSystem.NormalizeClientId(clientId);
            if (_stationEscrowClientId.Length == 0)
                _stationEscrowClientId = Guid.NewGuid().ToString("N");
            bool remoteClaim = (tag.ContainsKey("infiniStationEscrowRemoteAuthority") && tag.GetBool("infiniStationEscrowRemoteAuthority"))
                || tag.ContainsKey("infiniStationEscrowMirror") || tag.ContainsKey("infiniPendingStationEscrow")
                || tag.GetList<TagCompound>("infiniPendingRemoteCrafts").Count > 0;
            _stationEscrowUsesRemoteAuthority = false;
            _stationEscrowOriginScope = "";
            _readOnlyRemoteStationClaim = null;
            _dormantRemoteStationClaims.Clear();
            _activeRemoteStationClaim = null;
            if (tag.ContainsKey(ReadOnlyRemoteStationClaimSaveKey))
                RetainDormantRemoteStationClaim((TagCompound)tag.GetCompound(ReadOnlyRemoteStationClaimSaveKey).Clone());
            foreach (TagCompound claim in tag.GetList<TagCompound>(DormantRemoteStationClaimsSaveKey))
                RetainDormantRemoteStationClaim((TagCompound)claim.Clone());
            if (remoteClaim)
            {
                TagCompound liveClaim = (TagCompound)tag.Clone();
                // Archive metadata is not part of the separate live authority.
                liveClaim.Remove(ReadOnlyRemoteStationClaimSaveKey);
                liveClaim.Remove(DormantRemoteStationClaimsSaveKey);
                RetainDormantRemoteStationClaim(liveClaim);
            }
            // Unknown old origin is retained literally, never assigned to the
            // currently opened world and never hydrated into material slots.
            if (remoteClaim)
                return;
            foreach (var itemTag in tag.GetList<TagCompound>("infiniPendingCraftRefunds"))
            {
                try
                {
                    Item item = ItemIO.Load(itemTag);
                    if (item is not null && !item.IsAir && item.stack > 0)
                        _deferredExitRefunds.Add(item.Clone());
                }
                catch
                {
                    // Ignore corrupted refund entries; normal inventory loading must not break.
                }
            }
        }
        catch
        {
            _deferredExitRefunds.Clear();
        }
    }

    private List<TagCompound> SavePendingRemoteCrafts()
    {
        var pending = new List<TagCompound>();
        if (_stationEscrowUsesRemoteAuthority && _awaitingServerCommit && _request is not null && HasCraftRequestId(_serverRequestId))
            AddPendingRemoteCraftTag(pending, 0, _serverRequestId, _request);
        AddMultiDevPendingRemoteCrafts(pending);
        return pending;
    }

    private static void AddPendingRemoteCraftTag(
        List<TagCompound> pending,
        int laneIndex,
        string requestId,
        GeneratorClient.PreparedGenerationRequest request)
    {
        if (pending is null || request is null || laneIndex is < 0 or > 2 || !HasCraftRequestId(requestId))
            return;
        Item a = request.RefundA?.Clone() ?? NewAirItem();
        Item b = request.RefundB?.Clone() ?? NewAirItem();
        if (a.IsAir || b.IsAir)
            return;
        a.stack = 1;
        b.stack = 1;
        pending.Add(new TagCompound
        {
            ["laneIndex"] = laneIndex,
            ["requestId"] = NormalizeCraftRequestId(requestId),
            ["parentA"] = request.ParentA ?? "",
            ["parentB"] = request.ParentB ?? "",
            ["itemA"] = ItemIO.Save(a),
            ["itemB"] = ItemIO.Save(b),
        });
    }

    private void RestorePendingRemoteCrafts(IList<TagCompound> pending)
    {
        if (pending is null)
            return;
        foreach (TagCompound row in pending.Take(3))
        {
            int laneIndex = row.GetInt("laneIndex");
            string requestId = NormalizeCraftRequestId(row.GetString("requestId")).ToLowerInvariant();
            if (laneIndex is < 0 or > 2 || requestId.Length != 32 || !requestId.All(Uri.IsHexDigit)
                || !row.ContainsKey("itemA") || !row.ContainsKey("itemB"))
                continue;
            Item a;
            Item b;
            try
            {
                a = ItemIO.Load(row.GetCompound("itemA"));
                b = ItemIO.Load(row.GetCompound("itemB"));
            }
            catch
            {
                continue;
            }
            if (a is null || b is null || a.IsAir || b.IsAir || !InfiniCore.IsValidIngredient(a) || !InfiniCore.IsValidIngredient(b))
                continue;
            a.stack = 1;
            b.stack = 1;
            var request = new GeneratorClient.PreparedGenerationRequest
            {
                PayloadJson = "{}",
                ParentA = row.GetString("parentA") ?? "",
                ParentB = row.GetString("parentB") ?? "",
                RefundA = a.Clone(),
                RefundB = b.Clone(),
            };
            int first = laneIndex * 2;
            InputSlot(first) = a.Clone();
            InputSlot(first + 1) = b.Clone();
            if (laneIndex == 0)
            {
                if (HasPendingCraft)
                    continue;
                _request = request;
                _serverRequestId = requestId;
                _label = $"{request.ParentA} + {request.ParentB}";
                _awaitingServerCommit = true;
                _serverCraftWaitTicks = StationEscrowRetryIntervalTicks - 1;
                _task = null;
            }
            else
            {
                RestoreMultiDevPendingRemoteCraft(laneIndex, requestId, request);
            }
            _stationEscrowUsesRemoteAuthority = true;
        }
    }

    private List<TagCompound> PendingRefundTagsForSave()
    {
        var refunds = new List<TagCompound>();

        bool remoteMainPending = _stationEscrowUsesRemoteAuthority && _awaitingServerCommit;
        if (HasPendingCraft && _request is not null && !remoteMainPending)
        {
            AddRefundTag(refunds, _request.RefundA);
            AddRefundTag(refunds, _request.RefundB);
        }
        AddMultiDevPendingRefunds(refunds, includeRemoteAwaiting: !_stationEscrowUsesRemoteAuthority);

        if (!_stationEscrowUsesRemoteAuthority)
        {
            if (HasInputA) AddRefundTag(refunds, InputA);
            if (HasInputB) AddRefundTag(refunds, InputB);
            for (int index = 2; index < 6; index++)
                if (HasInputAt(index)) AddRefundTag(refunds, InputSlot(index));
        }
        return refunds;
    }

    private static void AddRefundTag(List<TagCompound> refunds, Item item)
    {
        if (item is null || item.IsAir || item.stack <= 0)
            return;
        Item saved = item.Clone();
        saved.stack = Math.Max(1, saved.stack);
        refunds.Add(ItemIO.Save(saved));
    }

    private void RestoreDeferredExitRefunds()
    {
        if (_deferredExitRefunds.Count <= 0)
            return;

        int count = 0;
        foreach (Item item in _deferredExitRefunds)
        {
            if (item is null || item.IsAir || item.stack <= 0)
                continue;
            RefundOne(item);
            count++;
        }
        _deferredExitRefunds.Clear();
        if (count > 0)
            CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, $"InfiniCraft: возвращены предметы незавершённого крафта x{count}");
    }

    public bool BeginCraft(GeneratorClient.PreparedGenerationRequest request, string label)
    {
        if (HasPendingCraft)
            return false;

        CaptureAudioSettingsSnapshot();

        _request = request;
        _label = label;
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;

        // Only the HTTP call runs in the background. Item/Projectile introspection has already
        // happened on the main thread while building PreparedGenerationRequest.
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        StartGenerationTask("initial");
        CombatText.NewText(Player.Hitbox, Color.Cyan, ForgePresentationText("Started"));
        return true;
    }

    private void StartGenerationTask(string reason)
    {
        var request = _request;
        if (request is null)
            return;
        _generationAttempt++;
        _retryWaitTicks = 0;
        _task = Task.Run(() => global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.GeneratePreparedBlocking(request));
        if (_generationAttempt > 1)
            CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, ForgePresentationText("Attempt", _generationAttempt));
    }

    private void ScheduleEarlyRetry(string reason)
    {
        _task = null;
        int backoff = Math.Min(CraftRetryBackoffMaxTicks, CraftRetryBackoffBaseTicks + Math.Max(0, _generationAttempt - 1) * 3 * 60);
        _retryWaitTicks = Math.Max(60, backoff);
        if (_lastRetryNoticeTick <= 0 || _totalCraftTicks - _lastRetryNoticeTick >= 10 * 60)
        {
            _lastRetryNoticeTick = _totalCraftTicks;
            CombatText.NewText(Player.Hitbox, Color.Orange, ForgePresentationText("Recovery", RetrySecondsLeft));
        }
    }

    private void ScheduleGeneratorOfflineRetry(string reason)
    {
        _task = null;
        _retryWaitTicks = Math.Max(30 * 60, _retryWaitTicks);
        // Keep this low-noise: cache recovery can briefly see the endpoint cooling
        // down even when the item is generated successfully a moment later. Do not
        // spam the player with the port number every retry tick.
        if (_totalCraftTicks >= 15 * 60 && (_lastGeneratorOfflineNoticeTick <= 0 || _totalCraftTicks - _lastGeneratorOfflineNoticeTick >= 60 * 60))
        {
            _lastGeneratorOfflineNoticeTick = _totalCraftTicks;
            CombatText.NewText(Player.Hitbox, Color.Orange, ForgePresentationText("Offline", RetrySecondsLeft));
        }
    }


    public override void PostUpdateEquips()
    {
        ApplyGeneratedUtilityBuffEffects();
    }

    public override bool PreItemCheck()
    {
        Common.Systems.GeneratedPlacementLedgerSystem.RefreshPlacementInput(Player);
        return true;
    }

    public override void PostUpdate()
    {
        RefreshRemoteStationAuthority();
        TickCraftAudioGuard();
        TickGeneratedUtilityBuff();
        TickGeneratedRegistryCatchup();
        TickGeneratedInventoryAssetPrefetch();
        TickPendingStationEscrow();
        TickMultiDevCrafts();
        GeneratedHeldItemDrawLayer.MaybeBroadcastLocalHeldItem(Player, ref _heldItemPresentationSyncTick, ref _heldItemPresentationSyncKey);

        if (Main.netMode != NetmodeID.Server && !Main.playerInventory && !HasPendingCraft && HasAnyInput)
            ReturnStationInputs();

        if (_awaitingServerCommit)
        {
            // Multiplayer clients do not run LocalGenerator and do not submit GeneratedItemData.
            // This state only waits for the authoritative host to finish PacketRequestServerCraft.
            _serverCraftWaitTicks++;
            _totalCraftTicks++;
            if (_elapsedTicks < CraftDurationTicks)
                _elapsedTicks++;
            _ticksLeft = Math.Max(0, CraftDurationTicks - _elapsedTicks);
            if (_serverCraftWaitTicks == 2 * 60)
                CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, ForgePresentationText("HostWorking"));
            if (_serverCraftWaitTicks % StationEscrowRetryIntervalTicks == 0)
                ResendPendingRemoteCrafts();
            if (_serverCraftWaitTicks == RemoteServerCraftTimeoutTicks)
                CombatText.NewText(Player.Hitbox, Color.Orange, ForgePresentationText("HostDelayed"));
            return;
        }

        if (_request is null && _task is null)
            return;

        _totalCraftTicks++;
        if (_elapsedTicks < CraftDurationTicks)
            _elapsedTicks++;
        _ticksLeft = Math.Max(0, CraftDurationTicks - _elapsedTicks);
        _announceTick++;

        if (_task is null)
        {
            if (_retryWaitTicks > 0)
            {
                _retryWaitTicks--;
                if (_retryWaitTicks <= 0)
                    StartGenerationTask("early_retry");
                return;
            }

            if (_request is not null && _totalCraftTicks < CraftRecoveryTimeoutTicks)
            {
                if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator?.IsEndpointCoolingDown == true)
                {
                    ScheduleGeneratorOfflineRetry("endpoint_cooldown");
                    return;
                }
                StartGenerationTask("missing_task_retry");
                return;
            }

            FailCraft("InfiniCraft: генератор не завершил крафт — предметы возвращены", "генератор хоста не завершил крафт");
            return;
        }

        // Give the item as soon as the background craft is ready. The 240s timer is a
        // progress estimate/upper UI bar, not an artificial delay.
        if (!_task.IsCompleted)
        {
            // CombatText is now only a low-noise fallback. The inventory station UI is the primary timer.
            if (_ticksLeft > 0 && _announceTick >= 15 * 60)
            {
                _announceTick = 0;
                CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, ForgePresentationText("CountdownNotice", Math.Ceiling(_ticksLeft / 60f)));
            }
            if (_ticksLeft <= 0 && !_lateMessageShown)
            {
                _lateMessageShown = true;
                CombatText.NewText(Player.Hitbox, Color.Orange, ForgePresentationText("LateNotice"));
            }
            return;
        }

        GeneratedItemData? data = null;
        try
        {
            data = _task.Result;
        }
        catch
        {
            data = null;
        }

        if (data is null)
        {
            var generator = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator;
            if (_request?.FailureIsFatal == true)
            {
                string detail = _request.FailureStatusCode > 0
                    ? $"HTTP {_request.FailureStatusCode}"
                    : "ошибка рецепта";
                if (!string.IsNullOrWhiteSpace(_request.FailureMessage))
                    detail += $": {_request.FailureMessage}";
                string playerMessage = !string.IsNullOrWhiteSpace(_request.FailurePlayerMessage)
                    ? _request.FailurePlayerMessage
                    : "InfiniCraft: рецепт не прошёл проверку — предметы возвращены; попробуй скрафтить заново";
                FailCraft(playerMessage, detail);
                return;
            }

            if (_request is not null && _totalCraftTicks < CraftRecoveryTimeoutTicks)
            {
                if (generator?.IsEndpointCoolingDown == true)
                {
                    ScheduleGeneratorOfflineRetry("endpoint_cooldown_after_null");
                    return;
                }
                ScheduleEarlyRetry("null_result_recovery");
                return;
            }

            FailCraft("InfiniCraft: генератор не отдал готовый рецепт — предметы возвращены", "генератор хоста не отдал готовый предмет");
            return;
        }

        SpawnGeneratedItem(data);
    }


    private void FailCraft(string localMessage, string remoteMessage)
    {
        if (IsServerAuthoritativeCraft)
        {
            SendServerAuthoritativeResultIfNeeded(false, "", remoteMessage);
            ClearCraft();
            return;
        }

        RefundIngredients();
        CombatText.NewText(Player.Hitbox, Color.OrangeRed, localMessage);
        ClearCraft();
    }


    private void SpawnGeneratedItem(GeneratedItemData data)
    {
        // Multiplayer craft is server-authoritative. A client must never commit
        // GeneratedItemData to the host; if this path is reached on a client, an old
        // local-generation flow leaked back in, so fail closed and refund.
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            FailCraft("InfiniCraft: клиентский коммит отключён — предметы возвращены", "client-generated commit path is disabled");
            return;
        }

        if (SpawnGeneratedItemServerSide(Player, data, out string error))
        {
            SendServerAuthoritativeResultIfNeeded(true, data.Name, "ok");
            RunLocalCraftReveal(Player, data);
            ClearCraft();
            return;
        }

        FailCraft("InfiniCraft: серверный коммит сорвался — предметы возвращены", string.IsNullOrWhiteSpace(error) ? "хост не создал предмет" : error);
    }


    public void AbortTransientCraftForWorldExit()
    {
        if (_stationEscrowUsesRemoteAuthority && Main.netMode != NetmodeID.Server)
        {
            ParkRemoteStationClaim();
            return;
        }
        // World exit/unload must not eat station inputs or in-flight craft ingredients.
        // If SaveData already persisted a refund bundle, do not also put the same items
        // into inventory here; they will be restored by LoadData/OnEnterWorld.
        if (!_pendingRefundSavedForWorldExit && !_pendingRemoteCraftSavedForWorldExit)
        {
            if (_awaitingServerCommit)
                SendRemoteServerCraftCancel("client_world_exit");
            else if (HasPendingCraft)
                RefundIngredients();

            if (HasInputA || HasInputB)
                ReturnStationInputs();
        }

        AbortMultiDevCraftsForWorldExit(refundLocally: !_pendingRefundSavedForWorldExit && !_pendingRemoteCraftSavedForWorldExit);
        ClearCraft();
    }


    private void CaptureAudioSettingsSnapshot()
    {
        RememberPositiveAudioSettings();
        _craftSoundVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("soundVolume"), _lastGoodSoundVolume);
        _craftMusicVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("musicVolume"), _lastGoodMusicVolume);
        _craftAmbientVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("ambientVolume"), _lastGoodAmbientVolume);
        _craftAudioGuardTicks = Math.Max(_craftAudioGuardTicks, PostCraftAudioGuardTicks);
    }

    private void RestoreSuspiciousAudioMute()
    {
        // Some external/edge craft paths have been observed to leave Terraria's global
        // audio sliders at 0 after a generation finishes. This guard is intentionally
        // narrow: it only restores a setting if it was positive at craft start and is
        // now exactly/suspiciously muted. It does not normalize volumes or touch item
        // sound profiles.
        RestoreMainFloatIfSuspiciouslyMuted("soundVolume", _craftSoundVolumeSnapshot);
        RestoreMainFloatIfSuspiciouslyMuted("musicVolume", _craftMusicVolumeSnapshot);
        RestoreMainFloatIfSuspiciouslyMuted("ambientVolume", _craftAmbientVolumeSnapshot);
        // Keep snapshots alive for a short post-craft window. Some resets happen one
        // or more frames after ClearCraft(), so a single restore at finish was not enough.
    }

    private static float PositiveOrFallback(float current, float fallback)
    {
        if (current > 0.001f)
            return current;
        return fallback > 0.001f ? fallback : current;
    }

    private void RememberPositiveAudioSettings()
    {
        RememberPositiveAudioSetting("soundVolume", ref _lastGoodSoundVolume);
        RememberPositiveAudioSetting("musicVolume", ref _lastGoodMusicVolume);
        RememberPositiveAudioSetting("ambientVolume", ref _lastGoodAmbientVolume);
    }

    private static void RememberPositiveAudioSetting(string name, ref float cache)
    {
        float v = ReadMainFloatSetting(name);
        if (v > 0.001f)
            cache = v;
    }

    private void TickCraftAudioGuard()
    {
        bool active = HasPendingCraft || _craftAudioGuardTicks > 0;
        if (!active)
        {
            RememberPositiveAudioSettings();
            return;
        }

        RestoreSuspiciousAudioMute();
        if (!HasPendingCraft && _craftAudioGuardTicks > 0)
            _craftAudioGuardTicks--;

        if (!HasPendingCraft && _craftAudioGuardTicks <= 0)
        {
            _craftSoundVolumeSnapshot = -1f;
            _craftMusicVolumeSnapshot = -1f;
            _craftAmbientVolumeSnapshot = -1f;
            RememberPositiveAudioSettings();
        }
    }

    private static float ReadMainFloatSetting(string name)
    {
        float main = ReadStaticFloat(typeof(Main), name);
        if (main >= 0f)
            return main;

        // Some tML/audio paths expose the SFX slider through SoundEngine rather
        // than Main.soundVolume.  Reflection keeps this compatible across tML
        // builds and avoids compile-time dependency on a specific property shape.
        if (string.Equals(name, "soundVolume", StringComparison.OrdinalIgnoreCase))
        {
            foreach (string alt in new[] { "SoundVolume", "soundVolume", "Volume" })
            {
                float v = ReadStaticFloat(typeof(Terraria.Audio.SoundEngine), alt);
                if (v >= 0f)
                    return v;
            }
        }
        return -1f;
    }

    private static float ReadStaticFloat(Type type, string name)
    {
        const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
        try
        {
            var field = type.GetField(name, flags);
            if (field is not null && field.GetValue(null) is float fv)
                return fv;

            var prop = type.GetProperty(name, flags);
            if (prop is not null && prop.GetValue(null) is float pv)
                return pv;
        }
        catch { }
        return -1f;
    }

    private static void RestoreMainFloatIfSuspiciouslyMuted(string name, float snapshot)
    {
        if (snapshot <= 0.001f)
            return;

        RestoreStaticFloatIfSuspiciouslyMuted(typeof(Main), name, snapshot);
        if (string.Equals(name, "soundVolume", StringComparison.OrdinalIgnoreCase))
        {
            foreach (string alt in new[] { "SoundVolume", "soundVolume", "Volume" })
                RestoreStaticFloatIfSuspiciouslyMuted(typeof(Terraria.Audio.SoundEngine), alt, snapshot);
        }
    }

    private static void RestoreStaticFloatIfSuspiciouslyMuted(Type type, string name, float snapshot)
    {
        const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
        try
        {
            var field = type.GetField(name, flags);
            if (field is not null && field.GetValue(null) is float current)
            {
                if (current <= 0.001f)
                    field.SetValue(null, Math.Clamp(snapshot, 0f, 1f));
                return;
            }

            var prop = type.GetProperty(name, flags);
            if (prop is not null && prop.CanWrite && prop.GetValue(null) is float currentProp && currentProp <= 0.001f)
                prop.SetValue(null, Math.Clamp(snapshot, 0f, 1f));
        }
        catch { }
    }

    private void ClearCraft()
    {
        RestoreSuspiciousAudioMute();
        _craftAudioGuardTicks = Math.Max(_craftAudioGuardTicks, PostCraftAudioGuardTicks);

        _request = null;
        _task = null;
        _ticksLeft = 0;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _retryWaitTicks = 0;
        _generationAttempt = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;
        _serverRequestId = "";
        _label = "";
        _pendingRefundSavedForWorldExit = false;
        _pendingRemoteCraftSavedForWorldExit = false;
    }

}
