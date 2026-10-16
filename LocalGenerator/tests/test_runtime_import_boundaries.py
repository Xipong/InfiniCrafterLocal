"""Imports expose real owners without eagerly starting unrelated runtime layers."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest


PACKAGE = "infini_local.core.runtime_authoring"


def _imported_modules(*names: str) -> set[str]:
    script = (
        "import importlib,json,sys; "
        "[importlib.import_module(name) for name in sys.argv[1:]]; "
        "print(json.dumps(sorted(name for name in sys.modules if name.startswith('infini_local'))))"
    )
    from pathlib import Path
    result = subprocess.run([sys.executable, "-c", script, *names], cwd=Path(__file__).resolve().parents[1],
                            check=True, capture_output=True, text=True, timeout=20)
    return set(json.loads(result.stdout))


def test_registry_import_does_not_load_compilation_repair_or_transport() -> None:
    loaded = _imported_modules(PACKAGE + ".capability_registry")
    assert PACKAGE + ".capability_registry" in loaded
    assert not loaded & {
        PACKAGE + ".compiler", PACKAGE + ".validator", PACKAGE + ".wire_validator",
        PACKAGE + ".repair_scope", PACKAGE + ".program_schema", PACKAGE + ".technical_lowering",
        "infini_local.pipelines.llm_transport", "infini_local.core.config_bootstrap",
    }


@pytest.mark.parametrize("owners", [
    ("compiler", "repair_scope", "wire_validator", "program_schema", "validator"),
    ("wire_validator", "validator", "program_schema", "repair_scope", "compiler"),
    ("repair_scope", "program_schema", "compiler", "validator", "wire_validator"),
])
def test_runtime_owners_import_independently_of_barrel_order(owners: tuple[str, ...]) -> None:
    names = {PACKAGE + "." + name for name in owners}
    assert names <= _imported_modules(*(PACKAGE + "." + name for name in owners))


@pytest.mark.parametrize("reader", [
    PACKAGE + ".wire_views",
    "infini_local.core.vfx_manifest",
    "infini_local.pipelines.visual_generation_pipeline",
    "infini_local.pipelines.vfx_generation_pipeline",
])
def test_presentation_readers_do_not_import_gameplay_generation(reader: str) -> None:
    loaded = _imported_modules(reader)
    assert reader in loaded
    assert not loaded & {
        PACKAGE + ".compiler", PACKAGE + ".repair_scope",
        "infini_local.pipelines.llm_authoring_pipeline", "infini_local.pipelines.gameplay_stage",
    }
