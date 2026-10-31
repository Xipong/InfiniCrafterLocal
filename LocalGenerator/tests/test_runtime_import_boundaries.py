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
        "infini_local.pipelines.transport.client", "infini_local.core.config_bootstrap",
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
    "infini_local.core.vfx.validation",
    "infini_local.pipelines.visual.request",
    "infini_local.pipelines.vfx.request",
])
def test_presentation_readers_do_not_import_gameplay_generation(reader: str) -> None:
    loaded = _imported_modules(reader)
    assert reader in loaded
    assert not loaded & {
        PACKAGE + ".compiler", PACKAGE + ".repair_scope",
        "infini_local.pipelines.author.request", "infini_local.pipelines.author.stage",
    }


def test_vfx_contracts_execute_without_generation_packages() -> None:
    """VFX and provider contracts execute without a model-stage installation."""
    from pathlib import Path
    from tests.vfx_material_fixtures import _data

    script = """
import importlib.abc
import json
import sys

class NoGeneration(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'infini_local.pipelines' or fullname.startswith('infini_local.pipelines.'):
            raise ImportError('generation packages intentionally unavailable')

sys.meta_path.insert(0, NoGeneration())
from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA
from infini_local.core.vfx.schema import vfx_director_schema
from infini_local.core.vfx.projection import _compile_manifest
from infini_local.core.vfx.validation import validate_vfx_director_output, validate_vfx_manifest_wire

from infini_local.core.provider_schema import _provider_strict_projection, project_provider_nullable_optionals_to_local
local = {'type': 'object', 'additionalProperties': False,
         'properties': {'required': {'type': 'integer'}, 'optional': {'type': 'string'}},
         'required': ['required']}
transport = {'type': 'json_schema', 'json_schema': {'schema': _provider_strict_projection(local)}}
encoded = {'required': 3, 'optional': None}
assert project_provider_nullable_optionals_to_local(encoded, local, response_format=transport) == {'required': 3}
assert project_provider_nullable_optionals_to_local(encoded, local) == encoded
assert project_provider_nullable_optionals_to_local({'required': None}, local, response_format=transport) == {'required': None}

data = json.load(sys.stdin)
authored = {'schema': VFX_DIRECTOR_SCHEMA, 'slots': []}
assert vfx_director_schema(data)['type'] == 'object'
assert validate_vfx_director_output(authored, data)['ok']
data['vfxManifest'] = _compile_manifest(data, authored, 'offline-contract')
assert validate_vfx_manifest_wire(data)['ok']
data['vfxManifest']['slots'] = [{'id': 'broken', 'rendererKind': 'not-supported'}]
assert not validate_vfx_manifest_wire(data)['ok']
"""
    subprocess.run(
        [sys.executable, "-c", script], input=json.dumps(_data()),
        cwd=Path(__file__).resolve().parents[1], check=True,
        capture_output=True, text=True, timeout=20,
    )
