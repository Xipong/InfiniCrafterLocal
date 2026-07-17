from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def _check_generated_item_loaddata_does_not_start_registry_or_asset_sync() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    assert "SetData(GeneratedItemData.FromPlayerSaveJson(json) ?? GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false)" in source
    assert "private static string SafeGetString(TagCompound tag, string key)" in source
    assert "RegisterLocal(Data, ensureAssets: ensureAssets)" in source
    assert "tag[\"infiniJson\"] = (Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson();" in source
    save_start = source.index("public override void SaveData(TagCompound tag)")
    save_end = source.index("public override void LoadData(TagCompound tag)", save_start)
    assert "ToNetworkJson()" not in source[save_start:save_end]
    data_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "MaxPlayerSaveTagStringPayloadBytes = 4 * 1024" in data_source
    assert "TagIO stores strings through signed Int16 lengths" in data_source
    assert "MaxNetworkStringPayloadBytes = 100000" in data_source
    assert "Network generated-item packets allow up to 100 KB" in data_source
    assert "public static GeneratedItemData? FromPlayerSaveJson(string? json)" in data_source
    assert "public static bool IsPlayerSaveReferenceOnly(GeneratedItemData? data)" in data_source


def _check_player_save_payload_is_compact_reference_not_runtime_definition() -> None:
    data_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    start = data_source.index("public string ToPlayerSaveJson()")
    end = data_source.index("public static GeneratedItemData? FromPlayerSaveJson", start)
    save_block = data_source[start:end]
    assert "generatedItemRef" in save_block
    assert "ToNetworkJson()" not in save_block
    for forbidden in [
        "Gameplay =", "Accessory =", "Armor =", "Attack =", "Visual =", "VfxManifest",
        "AssetBaseUrl", "AssetFiles", "Debug", "ExtensionData", "SourceRepresentation",
        "ImagePrompt", "ProjectileSpritePrompt", "VfxManifestJson",
    ]:
        assert forbidden not in save_block


def _check_generated_item_runtime_hydrates_playersave_ref_from_local_cache() -> None:
    item = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    start = item.index("private void EnsureRuntimeHydration")
    end = item.index("public override void NetSend", start)
    hydration_block = item[start:end]
    assert "SetData(cachedData, ensureAssets: false, registerLocal: false, notifyNetState: false);" in hydration_block
    assert "GeneratedItemData.IsPlayerSaveReferenceOnly(Data)" in hydration_block
    assert "!GeneratedItemData.IsPlayerSaveReferenceOnly(Data)" in hydration_block
    for method_name in ["ModifyTooltips"]:
        method_start = item.index(f"public override void {method_name}")
        method_end = item.index("GeneratedItemData data =", method_start)
        assert "EnsureRuntimeHydration();" in item[method_start:method_end]



def _check_registry_register_local_can_skip_asset_hydration() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedItemRegistryService.cs").read_text(encoding="utf-8")
    assert "RegisterLocal(GeneratedItemData? data, bool persist = true, bool ensureAssets = true)" in source
    assert "if (ensureAssets)" in source
    assert "EnsureAssetsForData(data)" in source


def _check_player_save_reference_cannot_replace_or_persist_canonical_registry_data() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedItemRegistryService.cs").read_text(encoding="utf-8")
    start = source.index("public void RegisterLocal")
    end = source.index("public void PublishGeneratedItem", start)
    block = source[start:end]
    guard = block.index("GeneratedItemData.IsPlayerSaveReferenceOnly(data)")
    normalize = block.index("data.Normalize()")
    persist = block.index("PersistOne(data)")
    assert guard < normalize < persist
    guarded = block[guard:normalize]
    assert "_byId.TryGetValue(data.Id" in guarded
    assert "EnsureAssetsForData(canonical" in guarded
    assert "return;" in guarded
    assert "PersistOne" not in guarded


def _check_generated_item_data_rejects_old_runtime_versions_and_caps_strings() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert '"v0.4.28"' not in source and '"v0.4.29"' not in source
    assert "private static string SafeText" in source
    assert "private static string[] SafeTextArray" in source
    assert "Name = string.IsNullOrWhiteSpace(Name) ? \"Generated Item\" : SafeText(Name, 80);" in source
    assert "Tooltip = SafeText(Tooltip, 240);" in source


def _check_generated_item_clone_deep_copies_runtime_payload_without_asset_side_effects():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    assert "public override ModItem Clone(Item newEntity)" in src
    assert "base.Clone(newEntity)" in src
    assert "ToNetworkJson()" in src
    assert "GeneratedItemData.FromJson(json)" in src
    clone_block = src[src.index("public override ModItem Clone(Item newEntity)"):src.index("public void SetData", src.index("public override ModItem Clone(Item newEntity)"))]
    assert "RegisterLocal" not in clone_block
    assert "EnsureAssets" not in clone_block

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_generated_item_loaddata_does_not_start_registry_or_asset_sync',
    '_check_registry_register_local_can_skip_asset_hydration',
    '_check_player_save_reference_cannot_replace_or_persist_canonical_registry_data',
    '_check_player_save_payload_is_compact_reference_not_runtime_definition',
    '_check_generated_item_runtime_hydrates_playersave_ref_from_local_cache',

    '_check_generated_item_data_rejects_old_runtime_versions_and_caps_strings',
    '_check_generated_item_clone_deep_copies_runtime_payload_without_asset_side_effects'
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


def test_csharp_player_load_guard_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
