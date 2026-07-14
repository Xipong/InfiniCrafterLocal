from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return read_text_with_partial_bundles(ROOT / rel)


def _contract_check_mp_server_authoritative_craft_spends_real_server_inventory_slots():
    src = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")
    assert "PacketCancelServerCraft = InfiniNetPacketIds.CancelServerCraft" in src
    assert "CancelServerCraft = 12" in read("ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs")
    assert "HandleCancelServerCraftPacket" in src
    assert "SendRemoteServerCraftCancel" in src
    assert "TryTakeServerSideIngredient" in src
    assert "player.inventory" in src
    assert "InfiniCore.IsValidIngredient(slot)" in src
    assert "slot.favorited" in src
    assert "SyncEquipment" in src
    assert "нет совпадающего предмета в server-side inventory slots 0..49" in src
    request_body = src[src.index("public static void HandleRequestServerCraftPacket"):src.index("public static void HandleCancelServerCraftPacket")]
    assert "TryReconstructCraftItem" not in request_body
    assert "Generator.Prepare(itemA, itemB, player)" in request_body


def _contract_check_client_timeout_cancels_host_request_without_local_refund_dup_path():
    src = read("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")
    timeout_block = src[src.index("if (_awaitingServerCommit)"):src.index("if (_request is null && _task is null)")]
    assert "SendRemoteServerCraftCancel(\"client_timeout\")" in timeout_block
    assert "RefundIngredients();" not in timeout_block
    result_body = src[src.index("public void HandleCraftCommitResult"):src.index("private static void RunLocalCraftReveal")]
    assert "server is authoritative for ingredient ownership" in result_body
    assert "RefundIngredients();" not in result_body
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
            '_contract_check_client_timeout_cancels_host_request_without_local_refund_dup_path',
            '_contract_check_env_parsing_is_centralized_for_endpoint_and_main_pipeline_configs',
            '_contract_check_generated_json_compat_migration_code_is_removed_for_test_worlds_only',
            '_contract_check_ci_contains_pytest_and_real_tml_build_job',
            '_contract_check_contract_stamp_mentions_218_hardening',
        ),
    )
