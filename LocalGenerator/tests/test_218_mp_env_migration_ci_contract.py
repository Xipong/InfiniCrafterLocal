from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return read_text_with_partial_bundles(ROOT / rel)


def _contract_check_mp_server_authoritative_craft_spends_real_server_inventory_slots():
    src = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")
    packet_ids = read("ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs")
    assert "PacketCancelServerCraft = InfiniNetPacketIds.CancelServerCraft" in src
    assert "PacketRequestStationEscrow = InfiniNetPacketIds.RequestStationEscrow" in src
    assert "PacketStationEscrowResult = InfiniNetPacketIds.StationEscrowResult" in src
    assert "CancelServerCraft = 12" in packet_ids
    assert "RequestStationEscrow = 14" in packet_ids
    assert "StationEscrowResult = 15" in packet_ids
    assert "HandleStationEscrowRequestPacket" in src
    assert "HandleStationEscrowResultPacket" in src
    assert "HandleCancelServerCraftPacket" in src
    assert "SendRemoteServerCraftCancel" in src
    assert "TryTakeServerEscrowInput" in src
    assert "Player.inventory[58]" in src
    assert "SyncEquipment" in src
    request_body = src[src.index("public static void HandleRequestServerCraftPacket"):src.index("public static void HandleCancelServerCraftPacket")]
    assert "TryReconstructCraftItem" not in request_body
    assert "TryTakeServerSideIngredient" not in request_body
    assert "TryTakeServerEscrowInput" in request_body
    assert "Generator.Prepare(itemA, itemB, player)" in request_body


def _contract_check_mp_station_owns_inputs_via_server_mouse_slot_escrow():
    station = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Station.cs")
    start = station.index("public bool TryPutMouseItemIntoInput")
    end = station.index("public bool TryTakeInputToMouse", start)
    block = station[start:end]
    mp_guard = block.index("Main.netMode == NetmodeID.MultiplayerClient")
    local_debit = block.index("Main.mouseItem.stack--")
    assert mp_guard < local_debit
    mp_branch = block[mp_guard:]
    assert "target = Main.mouseItem.Clone();" in mp_branch
    assert "target.stack = 1;" in mp_branch
    assert "Player.inventory[58] = Main.mouseItem.Clone();" in mp_branch
    assert "MessageID.SyncEquipment" in mp_branch
    assert "SendStationEscrowRequest" in mp_branch
    assert "inventory or an open Void Bag" in mp_branch
    assert "сначала верните выбранный предмет" not in station

    craft_state = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.CraftState.cs")
    assert "Main.netMode != NetmodeID.Server && !Main.playerInventory" in craft_state

    save_start = craft_state.index("private List<TagCompound> PendingRefundTagsForSave()")
    save_end = craft_state.index("private static void AddRefundTag", save_start)
    save_block = craft_state[save_start:save_end]
    assert "non-owning selections" not in save_block
    assert "_request.RefundA" in save_block
    assert "_request.RefundB" in save_block
    assert "if (HasInputA) AddRefundTag" in save_block
    assert "if (HasInputB) AddRefundTag" in save_block


def _contract_check_mp_station_escrow_idempotent_recovering_transaction():
    """Single outstanding station escrow op: same operationId retry + server replay + safe rollback."""
    src = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")

    assert "StationEscrowRetryIntervalTicks" in src
    assert "TickPendingStationEscrow" in src
    assert "ResendPendingStationEscrowRequest" in src
    assert "MaxStationEscrowResultCacheEntries" in src
    assert "TryReplayStationEscrowResult" in src
    assert "RememberStationEscrowResult" in src
    assert "ClearStationEscrowResultCache" in src
    assert "_stationEscrowResultCache" in src
    assert "_stationEscrowResultOrder" in src
    assert "_pendingStationEscrowItem" in src
    assert "_pendingStationEscrowWaitTicks" in src


    # Client keeps one pending op and resends the SAME operationId (no new Guid on retry).
    send_start = src.index("private bool SendStationEscrowRequest")
    send_end = src.index("private void RestoreRejectedLocalDeposit", send_start)
    send_block = src[send_start:send_end]
    assert 'Guid.NewGuid().ToString("N")' in send_block
    assert "_pendingStationEscrowOperationId = operationId" in send_block
    assert "FlushPendingStationEscrowRequest" in send_block
    resend_start = src.index("private bool ResendPendingStationEscrowRequest")
    resend_block = src[resend_start:src.index("private void RestoreRejectedLocalDeposit", resend_start)]
    assert 'Guid.NewGuid()' not in resend_block
    assert "FlushPendingStationEscrowRequest" in resend_block
    assert "_pendingStationEscrowOperationId" in resend_block

    # Deposit reject restores the exact pending item; never blind mouseItem.stack++ alone.
    restore_start = src.index("private void RestoreRejectedLocalDeposit")
    restore_end = src.index("private void ClearPendingStationEscrowOperation", restore_start)
    restore_block = src[restore_start:restore_end]
    assert "_pendingStationEscrowItem" in restore_block
    assert "CanRestoreRejectedDepositOntoMouse" in restore_block
    assert "RefundOne" in restore_block
    assert "Main.mouseItem.stack++" in restore_block  # only after identity match
    assert "CanRestoreRejectedDepositOntoMouse" in src[src.index("CanRestoreRejectedDepositOntoMouse"):]

    can_start = src.index("private bool CanRestoreRejectedDepositOntoMouse")
    can_block = src[can_start:src.index("private void ClearStationEscrowResultCache", can_start) if "private void ClearStationEscrowResultCache" in src[can_start:] else can_start + 1200]
    # Prefer locating by next method after CanRestore
    can_end_marker = "private static bool StationEscrowGeneratedIdsMatch"
    if can_end_marker in src[can_start:]:
        can_block = src[can_start:src.index(can_end_marker, can_start)]
    assert "Main.mouseItem.type != restored.type" in can_block or "restored.type" in can_block
    assert "prefix" in can_block

    # Server handler replays any still-cached result before apply. This covers a
    # delayed retry of op1 arriving after op2 has already completed.
    handle_start = src.index("public static void HandleStationEscrowRequestPacket")
    handle_end = src.index("private void WriteGeneratedBuffState", handle_start)
    handle_block = src[handle_start:handle_end]
    assert "TryReplayStationEscrowResult" in handle_block
    assert "RememberStationEscrowResult" in handle_block
    replay_before_apply = handle_block.index("TryReplayStationEscrowResult")
    deposit_apply = handle_block.index("TryDepositServerMouseItem")
    assert replay_before_apply < deposit_apply

    # Lifecycle resets pending + bounded replay caches.
    init_block = src[src.index("public override void Initialize()"):src.index("public override void OnEnterWorld()")]
    assert "ClearPendingStationEscrowOperation" in init_block
    assert "ClearStationEscrowResultCache" in init_block
    enter_block = src[src.index("public override void OnEnterWorld()"):src.index("public override void SaveData")]
    assert "ClearPendingStationEscrowOperation" in enter_block
    clear_cache = src[src.index("public static void ClearServerCommitCache"):src.index("private static void SendStationEscrowResult")]
    assert "ClearStationEscrowResultCache" in clear_cache

    craft_state = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.CraftState.cs")
    assert "TickPendingStationEscrow()" in craft_state


def _contract_check_client_timeout_cancels_host_request_without_local_refund_dup_path():
    src = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")
    timeout_block = src[src.index("if (_awaitingServerCommit)"):src.index("if (_request is null && _task is null)")]
    assert "SendRemoteServerCraftCancel(\"client_timeout\")" in timeout_block
    assert "RefundIngredients();" not in timeout_block
    result_body = src[src.index("public void HandleCraftCommitResult"):src.index("private static void RunLocalCraftReveal")]
    assert "server is authoritative for ingredient ownership" in result_body
    assert "RefundIngredients();" not in result_body

    station = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Station.cs")
    refund_start = station.index("private void RefundOne(Item original)")
    refund_block = station[refund_start:]
    assert refund_block.count("SyncRefundedInventorySlot(i);") >= 2
    assert "MessageID.SyncEquipment" in refund_block
    assert "Player.whoAmI, slotIndex" in refund_block
def _contract_check_env_parsing_is_centralized_for_endpoint_and_main_pipeline_configs():
    env_utils = read("LocalGenerator/infini_local/core/env_utils.py")
    assert "def env_int" in env_utils
    assert "def env_float" in env_utils
    assert "def env_bool" in env_utils
    assert "def env_path" in env_utils
    endpoint = read("LocalGenerator/infini_local/services/combine_endpoint.py")
    assert "from infini_local.core.env_utils import env_int" in endpoint
    assert "COMBINE_CONCURRENCY = env_int(" in endpoint
    assert "COMBINE_BUSY_WAIT_SECONDS = env_int(" in endpoint
    assert "int(os.environ.get(\"INFINI_COMBINE" not in endpoint
    llm_config = read("LocalGenerator/infini_local/core/llm_config.py")
    assert "LLM_MAX_TOKENS = env_int(" in llm_config
    assert "USE_LLM = env_bool(" in llm_config
    bootstrap = read("LocalGenerator/infini_local/core/config_bootstrap.py")
    assert "CACHE_DIR =" in bootstrap
    server = read("LocalGenerator/infini_local/web/server.py")
    assert "from infini_local.core.config_bootstrap import (" in server
    assert "from infini_local.core.llm_config import (" in server
    assert "USE_LLM = env_bool(" not in server
    assert "LLM_MAX_TOKENS = env_int(" not in server
    visual = read("LocalGenerator/infini_local/pipelines/pipeline_visual_config.py")
    assert "env_bool" in visual and "env_float" in visual and "env_int" in visual


def _contract_check_generated_json_compat_migration_code_is_removed_for_test_worlds_only():
    src = read("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs")
    assert not (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Compat.cs").exists()
    for removed in [
        "ApplyCompatMigrations",
        "CompatNeedsRuntimeFamilyBackfill",
        "CompatLooksLikeShootRuntime",
        "CompatNeedsUseStyleBackfill",
        "CompatUseStyleForRuntimeFamily",
        "AttackRuntimeFamilyCompat",
        "Attack.RuntimeFamily = delivery",
        "AltMobilityRangeTiles = Gameplay.MobilityRangeTiles",
    ]:
        assert removed not in src
    assert "Attack.RuntimeFamily = NormalizeRuntimeFamily(Attack.RuntimeFamily);" in src


def _contract_check_ci_contains_pytest_and_real_tml_build_job():
    workflow = read(".github/workflows/ci.yml")
    assert "tools/run_pytest_shards.py" in workflow
    assert "tools/check_project_hygiene.py" in workflow
    assert "tools/check_csharp_contracts.py" in workflow
    assert "windows-latest" in workflow
    assert "build_tml_windows.ps1" in workflow
    assert "InfiniCrafterLocal.csproj" in workflow


def _contract_check_contract_stamp_mentions_218_hardening():
    from infini_local.core.contract_versions import build_contract_versions
    stamp = build_contract_versions(app_version="0.4.218", recipe_identity_version="r", runtime_api_version="v", visual_pipeline_profile="p")
    assert stamp["mpServerAuthorityEnvMigrationCiContract"] == "server_side_slot_spend_env_migration_ci_hardening_v0.4.218"


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_218_mp_env_migration_ci_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_mp_server_authoritative_craft_spends_real_server_inventory_slots',
            '_contract_check_mp_station_owns_inputs_via_server_mouse_slot_escrow',
            '_contract_check_mp_station_escrow_idempotent_recovering_transaction',
            '_contract_check_client_timeout_cancels_host_request_without_local_refund_dup_path',
            '_contract_check_env_parsing_is_centralized_for_endpoint_and_main_pipeline_configs',
            '_contract_check_generated_json_compat_migration_code_is_removed_for_test_worlds_only',
            '_contract_check_ci_contains_pytest_and_real_tml_build_job',
            '_contract_check_contract_stamp_mentions_218_hardening',
        ),
    )
