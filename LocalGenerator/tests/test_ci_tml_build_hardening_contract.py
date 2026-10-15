from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tml_sdk_external_reference_policy_is_explicit() -> None:
    # CI execution is covered through the shared runner and real PowerShell seam.
    csproj = (ROOT / "ModSources" / "InfiniCrafterLocal" / "InfiniCrafterLocal.csproj").read_text(encoding="utf-8")
    assert "Tomat.Terraria.ModLoader.Sdk" in csproj
    assert "InfiniExternalDepsRoot" in csproj
    assert 'HintPath="$(InfiniParticleLibraryDll)"' in csproj
    assert 'HintPath="$(InfiniLuminanceDll)"' in csproj
    assert "tmp\\tml-deps-src" not in csproj
    assert "INFINI_TML_DEPS_SRC" in csproj
    assert "InfiniValidateExternalModReferences" in csproj
