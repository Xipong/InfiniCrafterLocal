from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
PLAYER_SOURCE = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
MOD_SOURCE = (ROOT / "ModSources" / "InfiniCrafterLocal" / "InfiniCrafterLocal.cs").read_text(encoding="utf-8")


def _check_multiplayer_client_sends_craft_intent_not_generated_payload() -> None:
    assert "PacketRequestServerCraft = InfiniNetPacketIds.RequestServerCraft" in PLAYER_SOURCE
    assert "RequestServerCraft = 5" in (ROOT / "ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs").read_text(encoding="utf-8")
    assert "BeginRemoteServerCraft" in PLAYER_SOURCE
    assert "Main.netMode == NetmodeID.MultiplayerClient" in PLAYER_SOURCE
    assert "packet.Write(PacketRequestServerCraft)" in PLAYER_SOURCE
    assert "WriteCraftItemRef(packet, a)" in PLAYER_SOURCE
    assert "WriteCraftItemRef(packet, b)" in PLAYER_SOURCE
    assert "Generator.Prepare(a, b, Player)" in PLAYER_SOURCE


def _check_server_consumes_escrow_items_and_runs_generator_on_host() -> None:
    assert "HandleRequestServerCraftPacket" in PLAYER_SOURCE
    assert "TryReconstructCraftItem" not in PLAYER_SOURCE
    assert "TryTakeServerEscrowInput" in PLAYER_SOURCE
    assert "Generator.Prepare(itemA, itemB, player)" in PLAYER_SOURCE
    assert "BeginServerAuthoritativeCraft" in PLAYER_SOURCE
    assert "StartGenerationTask(\"server_authoritative\")" in PLAYER_SOURCE
    assert "SendServerAuthoritativeResultIfNeeded(true" in PLAYER_SOURCE
    assert "InfiniCraftPlayer.HandleRequestServerCraftPacket" in MOD_SOURCE


def _check_client_waits_for_host_result_and_does_not_need_local_generator() -> None:
    assert "хост генерирует предмет" in PLAYER_SOURCE
    assert "RemoteServerCraftTimeoutTicks = CraftRecoveryTimeoutTicks" in PLAYER_SOURCE
    assert "clients never commit authoritative GeneratedItemData" in PLAYER_SOURCE
    assert "Packet id 2 is intentionally retired" not in PLAYER_SOURCE
    assert "PacketSubmitGeneratedItem" not in PLAYER_SOURCE
    assert "HandleSubmitGeneratedItemPacket" not in PLAYER_SOURCE
    assert "GeneratedIdentityMatches" in PLAYER_SOURCE


def _check_server_authoritative_craft_hydrates_assets_automatically() -> None:
    assert "StampHostAssetSyncMetadata" in PLAYER_SOURCE
    assert "StampAssetTransportMetadata(data, refreshBaseUrl: true)" in PLAYER_SOURCE
    assert "GeneratedAssetSyncService.AssetFilesFromData(data).ToArray()" in PLAYER_SOURCE
    assert "compressed definition chunks" in PLAYER_SOURCE
    assert "no second filename/base-URL broadcast" in PLAYER_SOURCE
    assert "writer.Write(NormalizeCraftStack(item?.stack ?? 1));" in PLAYER_SOURCE
    assert "writer.Write((int)(item?.prefix ?? 0));\n        writer.Write((int)(item?.prefix ?? 0));" not in PLAYER_SOURCE


def _check_projectile_packets_stay_light_but_restore_visual_assets_from_registry() -> None:
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    send_start = projectile_source.index("public override void SendExtraAI(BinaryWriter writer)")
    receive_start = projectile_source.index("public override void ReceiveExtraAI(BinaryReader reader)", send_start)
    send = projectile_source[send_start:receive_start]
    assert "private const int ProjectileSyncVersion = 20" in projectile_source
    assert "writer.Write(ShortNet(_generatedItemId, 96));" in send
    assert "writer.Write((byte)_runtimeVariant);" in send
    assert "_spec." not in send
    assert "VfxManifestJson = ShortNet" not in projectile_source
    assert "writer.Write(ShortNet(payload.VfxManifestJson" not in projectile_source
    assert "TryHydrateRuntimeVariantFromRegistry" in projectile_source
    assert "GeneratedChildSpecPolicy.TryCreateRuntimeVariant" in projectile_source
    assert "HydratePresentationFromRegistryIfPossible" in projectile_source
    assert "TryGetAttack(_generatedItemId)" in projectile_source
    assert "CopyMissingPresentationPaths(parent)" in projectile_source
    assert "GeneratedItems.TryGetVfxManifest(_generatedItemId)" in projectile_source


def _check_station_ui_describes_mp_host_authority_not_local_client_llm() -> None:
    ui_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "UI" / "InfiniCraftStationUISystem.cs").read_text(encoding="utf-8")
    assert "MP: host generates, assets auto-download" in ui_source
    assert "Uses the local LLM" not in ui_source


def _check_server_validates_and_spends_real_server_side_escrow() -> None:
    request_body = PLAYER_SOURCE[PLAYER_SOURCE.index("public static void HandleRequestServerCraftPacket"):PLAYER_SOURCE.index("public static void HandleCancelServerCraftPacket")]
    assert "TryTakeServerEscrowInput(0, aRef" in request_body
    assert "TryTakeServerEscrowInput(1, bRef" in request_body
    assert "Generator.Prepare(itemA, itemB, player)" in request_body
    assert "TryReconstructCraftItem(aRef" not in request_body
    assert "TryDepositServerMouseItem" in PLAYER_SOURCE
    assert "Player.inventory[58]" in PLAYER_SOURCE
    assert "InfiniCore.IsValidIngredient(slot)" in PLAYER_SOURCE


# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_multiplayer_client_sends_craft_intent_not_generated_payload',
    '_check_server_consumes_escrow_items_and_runs_generator_on_host',
    '_check_client_waits_for_host_result_and_does_not_need_local_generator',
    '_check_server_authoritative_craft_hydrates_assets_automatically',
    '_check_projectile_packets_stay_light_but_restore_visual_assets_from_registry',
    '_check_station_ui_describes_mp_host_authority_not_local_client_llm',
    '_check_server_validates_and_spends_real_server_side_escrow'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_multiplayer_server_authoritative_craft_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
