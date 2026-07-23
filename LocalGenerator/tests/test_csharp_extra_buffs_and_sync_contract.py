from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs"
ITEM = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs"
GENERATOR = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratorClient.cs"
PROJECTILE = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs"


def _check_csharp_extra_buffs_are_real_use_item_fields() -> None:
    model = read_text_with_partial_bundles(MODEL)
    item = ITEM.read_text(encoding="utf-8")
    assert "public BuffEntrySpec[] ExtraBuffs" in model
    assert "NormalizeExtraBuffs" in model
    assert "player.AddBuff(buff.BuffCode, buff.BuffTime)" in item


def _check_generator_restamps_asset_transport_metadata_unconditionally() -> None:
    src = GENERATOR.read_text(encoding="utf-8")
    assert "data.RecipeMeta.AssetBaseUrl = AssetBaseUrlForSharing(data.RecipeMeta.AssetBaseUrl);" in src
    assert 'new Uri(combineUri, "/mp_connect.json")' in src
    assert "if (string.IsNullOrWhiteSpace(data.RecipeMeta.AssetBaseUrl))" not in src


def _check_projectile_warning_logger_has_single_catch_block() -> None:
    src = PROJECTILE.read_text(encoding="utf-8")
    assert "catch { }\n        catch { }" not in src

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_csharp_extra_buffs_are_real_use_item_fields',
    '_check_generator_restamps_asset_transport_metadata_unconditionally',
    '_check_projectile_warning_logger_has_single_catch_block'
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


def test_csharp_extra_buffs_and_sync_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
