from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "ModSources" / "InfiniCrafterLocal" / "InfiniCrafterLocal.csproj"


def _assert_external_reference_policy(source: str) -> None:
    # XML formatting/attribute order is not an MSBuild contract. Keep the actual
    # configurable references and environment fallback, not a source snapshot.
    project = ET.fromstring(source)
    assert project.get("Sdk", "").split("/", 1)[0] == "Tomat.Terraria.ModLoader.Sdk"
    roots = project.findall("./PropertyGroup/InfiniExternalDepsRoot")
    assert any((root.text or "").strip() == "$(INFINI_TML_DEPS_SRC)" for root in roots)
    for library in ("ParticleLibrary", "Luminance"):
        refs = [ref for ref in project.findall("./ItemGroup/Reference") if ref.get("Include") == library]
        assert len(refs) == 1
        assert refs[0].get("HintPath") == f"$(Infini{library}Dll)"
    assert "tmp\\tml-deps-src" not in ET.tostring(project, encoding="unicode")
    assert any(target.get("Name") == "InfiniValidateExternalModReferences"
               for target in project.findall("Target"))


def test_tml_sdk_external_reference_policy_is_explicit() -> None:
    # CI execution is covered through the shared runner and real PowerShell seam.
    _assert_external_reference_policy(PROJECT.read_text(encoding="utf-8"))


def test_reference_policy_accepts_xml_formatting_and_rejects_missing_configuration():
    project = ET.parse(PROJECT).getroot()
    for element in project.iter():
        element.attrib = dict(reversed(list(element.attrib.items())))
    ET.indent(project, space="\t")
    reformatted = ET.tostring(project, encoding="unicode").replace('="', ' = "')
    _assert_external_reference_policy(reformatted)
    for broken in (
        reformatted.replace("$(InfiniParticleLibraryDll)", "hardcoded.dll"),
        reformatted.replace("$(INFINI_TML_DEPS_SRC)", "hardcoded-dependencies"),
        reformatted.replace("InfiniValidateExternalModReferences", "RemovedValidation"),
    ):
        with pytest.raises(AssertionError):
            _assert_external_reference_policy(broken)
