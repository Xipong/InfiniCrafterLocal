from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def test_partial_contract_reader_tracks_split_logical_types() -> None:
    model = read_text_with_partial_bundles(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    projectile = read_text_with_partial_bundles(MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    player = read_text_with_partial_bundles(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")

    assert "public ArmorSpec Armor" in model
    assert "RecordAppliedItemTrace" in model
    assert "SanitizeRuntimeSize(_spec)" in projectile
    assert "HandleCancelServerCraftPacket" in player


def test_tml_sdk_project_uses_configurable_external_reference_paths() -> None:
    csproj = (MOD / "InfiniCrafterLocal.csproj").read_text(encoding="utf-8")

    assert "Tomat.Terraria.ModLoader.Sdk" in csproj
    assert "InfiniExternalDepsRoot" in csproj
    assert "InfiniParticleLibraryDll" in csproj
    assert "InfiniLuminanceDll" in csproj
    assert 'HintPath="$(InfiniParticleLibraryDll)"' in csproj
    assert 'HintPath="$(InfiniLuminanceDll)"' in csproj
    assert "tmp\\tml-deps-src" not in csproj
    assert "INFINI_TML_DEPS_SRC" in csproj
    assert "InfiniValidateExternalModReferences" in csproj


def test_release_archive_excludes_local_tml_build_logs() -> None:
    # Local workspace may keep denied/non-source build_logs; release archives and
    # normal hygiene ignore that cache tree. Strict archive mode is the destructive
    # cleanup gate before packaging.
    hygiene = (ROOT / "tools" / "check_project_hygiene.py").read_text(encoding="utf-8")
    assert '"build_logs"' in hygiene
    assert "strict_archive" in hygiene
