from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def test_client_persists_pending_operation_exact_item_and_station_mirror() -> None:
    state = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")
    player = _read("Common/Players/InfiniCraftPlayer.cs")

    assert "_stationEscrowClientId" in player
    assert '"infiniStationEscrowClientId"' in state
    assert '"infiniStationEscrowMirror"' in state
    assert '"infiniPendingStationEscrow"' in state
    assert "ItemIO.Save(_pendingStationEscrowItem" in state
    enter = state.split("public override void OnEnterWorld()")[1].split("public override void SaveData")[0]
    assert "ClearPendingStationEscrowOperation" not in enter


def test_server_station_state_and_replay_outcomes_are_world_owned() -> None:
    system = _read("Common/Systems/GeneratedStationEscrowStateSystem.cs")
    player = _read("Common/Players/InfiniCraftPlayer.cs")

    assert "class GeneratedStationEscrowStateSystem : ModSystem" in system
    assert "public override void SaveWorldData" in system
    assert "public override void LoadWorldData" in system
    assert "RestoreOwnerState" in system
    assert "CaptureOwnerState" in system
    assert "TryReplay" in system
    assert "CanAcceptNewOperation" in system
    assert "Remove(" not in system.split("RememberOutcome")[1]
    assert "_stationEscrowResultCache" not in player


def test_packets_carry_stable_client_token_before_operation_id() -> None:
    multiplayer = _read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    sender = multiplayer.split("private bool FlushPendingStationEscrowRequest")[1].split("private void TickPendingStationEscrow")[0]
    handler = multiplayer.split("public static void HandleStationEscrowRequestPacket")[1].split("private void WriteGeneratedBuffState")[0]

    assert "packet.Write(_stationEscrowClientId)" in sender
    assert "string clientId = reader.ReadString();" in handler
    assert "GeneratedStationEscrowStateSystem.RestoreOwnerState" in handler
    assert "GeneratedStationEscrowStateSystem.TryReplay" in handler
    assert "GeneratedStationEscrowStateSystem.RememberOutcome" in handler
    apply_result = multiplayer.split("private void ApplyStationEscrowResult")[1].split("public static void HandleStationEscrowResultPacket")[0]
    assert "for (int slotIndex = 0; slotIndex < 6; slotIndex++)" in apply_result


def test_remote_craft_uses_world_owned_stable_identity_lease_and_replay() -> None:
    system = _read("Common/Systems/GeneratedStationEscrowStateSystem.cs")
    multiplayer = _read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    craft_state = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")

    assert "CraftTransactionsSaveKey" in system
    assert "TryBeginCraft" in system
    assert "TryReplayCraft" in system
    assert "IsCraftPending" in system
    assert "CompleteCraft" in system
    assert "GetList<TagCompound>(CraftTransactionsSaveKey).Take(MaxCraftTransactions)" in system
    assert '"infiniPendingRemoteCrafts"' in craft_state
    assert "RestorePendingRemoteCrafts" in craft_state
    assert "ResendPendingRemoteCrafts" in multiplayer
    assert '"servercraft:"' not in multiplayer
    assert "ServerCommittedCraftRequests" not in multiplayer
    assert "ServerCancelledCraftRequests" not in multiplayer


def test_remote_station_mirror_is_not_also_saved_as_inventory_refund() -> None:
    craft_state = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")
    refunds = craft_state.split("private List<TagCompound> PendingRefundTagsForSave()")[1].split("private static void AddRefundTag")[0]

    assert "if (!_stationEscrowUsesRemoteAuthority)" in refunds
    guarded = refunds.split("if (!_stationEscrowUsesRemoteAuthority)", 1)[1]
    assert "if (HasInputA) AddRefundTag(refunds, InputA);" in guarded
    assert "if (HasInputB) AddRefundTag(refunds, InputB);" in guarded
    assert "for (int index = 2; index < 6; index++)" in guarded


def test_remote_pending_inputs_are_reconciled_not_blind_refunded() -> None:
    craft_state = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")
    multiplayer = _read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")

    refunds = craft_state.split("private List<TagCompound> PendingRefundTagsForSave()")[1].split("private static void AddRefundTag")[0]
    assert "_awaitingServerCommit" in refunds
    assert "_stationEscrowUsesRemoteAuthority" in refunds
    assert "SavePendingRemoteCrafts" in craft_state
    assert "RestoreRemoteCraftMirror" in multiplayer
    assert "ClearRemoteCraftMirror" in multiplayer


def test_saved_multidev_pending_request_is_not_cancelled_during_world_exit_cleanup() -> None:
    multi = _read("Common/Players/InfiniCraftPlayer.MultiDev.cs")
    abort = multi.split("private void AbortMultiDevCraftsForWorldExit(bool refundLocally)")[1].split("private void AddMultiDevPendingRefunds")[0]

    assert "refundLocally && Main.netMode == NetmodeID.MultiplayerClient && job.AwaitingServerCommit" in abort


def test_station_return_replay_materializes_from_durable_client_mirror() -> None:
    multiplayer = _read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")

    server_one = multiplayer.split(
        "private bool TryReturnServerEscrowToInventory", 1
    )[1].split("private bool TryReturnServerEscrowLaneToInventory", 1)[0]
    server_all = multiplayer.split(
        "private bool TryReturnAllServerEscrowToInventory", 1
    )[1].split("private bool TrySnapshotServerEscrowInput", 1)[0]
    apply = multiplayer.split(
        "private void ApplyStationEscrowResult", 1
    )[1].split("public static void HandleStationEscrowResultPacket", 1)[0]
    client_one = apply.split(
        "else if (action == StationEscrowAction.ReturnOne", 1
    )[1].split("else if (action == StationEscrowAction.ReturnAll", 1)[0]
    client_all = apply.split(
        "else if (action == StationEscrowAction.ReturnAll", 1
    )[1]

    # The world journal can replay only authoritative success after a disconnect.
    # A refund placed in the old connection's Player.inventory can vanish with
    # that connection, so the server releases escrow and the client materializes
    # its persisted exact mirror once.
    assert "RefundOne(" not in server_one
    assert "RefundOne(" not in server_all
    assert "RefundOne(slot);" in client_one
    assert "RefundOne(slot);" in client_all