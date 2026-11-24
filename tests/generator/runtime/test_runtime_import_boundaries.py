"""The standalone VFX and provider contracts work without generation code."""
from __future__ import annotations
import json
import subprocess
import sys

from suite_paths import GENERATOR_ROOT


def test_vfx_contracts_execute_without_generation_packages() -> None:
    """VFX and provider contracts execute without a model-stage installation."""

    from tests.generator.vfx_material_fixtures import _data

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
        cwd=GENERATOR_ROOT, check=True,
        capture_output=True, text=True, timeout=20,
    )


def test_parameter_contract_executes_without_capability_inventory() -> None:
    """Parameter conversions need their declaration, not initialized mechanics."""

    script = """
import importlib.abc
import sys
from types import MappingProxyType

class NoInventory(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname == 'infini_local.core.runtime_authoring.capability_registry'
                or fullname == 'infini_local.pipelines'
                or fullname.startswith('infini_local.pipelines.')):
            raise ImportError('inventory/generation intentionally unavailable')

sys.meta_path.insert(0, NoInventory())
from infini_local.core.runtime_authoring.parameter_contract import ParamSpec, author_parameter_shape

speed = ParamSpec('number', 'Declared speed', wire_name='speedPxPerTick',
                 wire_kind='number', wire_multiplier=16, wire_divisor=60,
                 wire_updates_power=1, wire_minimum=0)
assert speed.to_wire(30, updates_per_tick=2) == 4
assert speed.from_wire(4, updates_per_tick=2) == 30
assert speed.consumer_value_error(-1, updates_per_tick=2) is not None
try:
    speed.to_wire(30)
except ValueError:
    pass
else:
    raise AssertionError('missing explicit update context was accepted')

group = ParamSpec('object', 'Declared component',
                 properties=MappingProxyType({'speed': speed}))
projected = group.projected_fields({'speed': 30}, 'motion', updates_per_tick=2)
assert [(row.authored_path, row.wire_path, row.value) for row in projected] == [
    ('motion.speed', 'speedPxPerTick', 4)]
schema = group.schema()
card = author_parameter_shape(schema)
card['properties']['speed']['meaning'] = 'changed presentation copy'
assert group.schema() == schema
assert speed.description == 'Declared speed'
"""
    subprocess.run(
        [sys.executable, "-c", script], cwd=GENERATOR_ROOT,
        check=True, capture_output=True, text=True, timeout=20,
    )
