"""Independent charge channels, world-time orbit, and literal tile restitution."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness


def fixture(fn):
    doc = build_capability_witness(fn)
    call = next(c for c in doc['runtimeProgram']['calls'] if c['id'] == 'witness_call')
    return doc, call


def entity(wire):
    return next(e for e in wire['runtimeProgram']['entities'] if e['id'] == 'witness_entity')


@pytest.mark.parametrize('updates', [1, 2, 6])
@pytest.mark.parametrize('rate', [-3.3, 0, 3.3])
def test_orbit_rate_projects_world_time_and_keeps_launch_speed_independent(updates, rate):
    doc, call = fixture('move_orbit')
    call['params']['turnRadiansPerSecond'] = rate
    collision = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'set_projectile_collision')
    collision['params']['updatesPerTick'] = updates
    wire = compile_runtime_program(doc)
    projected = entity(wire)['movement']['params']['orbitRadiansPerUpdate']
    assert projected == pytest.approx(rate / (60 * updates))
    assert entity(wire)['movement']['params']['rangeTiles'] == call['params']['radiusTiles']
    assert validate_runtime_wire(wire)['ok']
    rows = [r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
            and r['authoredPath'].endswith('.params.turnRadiansPerSecond')]
    assert len(rows) == 1 and rows[0]['value'] == projected
    assert rows[0]['finalPath'].endswith('.movement.params.orbitRadiansPerUpdate')


def test_charge_three_channels_project_without_coupling():
    doc, call = fixture('charge_then_release')
    call['params'].update(damageMultiplier=3, knockbackMultiplier=0.25, speedMultiplier=0.5)
    wire = compile_runtime_program(doc)
    params = entity(wire)['controller']['params']
    assert params['chargeDamageMultiplier'] == 3 and params['knockbackMultiplier'] == 0.25 and params['speedMultiplier'] == 0.5
    assert validate_runtime_wire(wire)['ok']
    for source, target in [('damageMultiplier', 'chargeDamageMultiplier'), ('knockbackMultiplier', 'knockbackMultiplier'), ('speedMultiplier', 'speedMultiplier')]:
        receipt = next(r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
                       and r['authoredPath'].endswith('.params.' + source))
        assert receipt['finalPath'].endswith('.controller.params.' + target)
        assert receipt['value'] == call['params'][source]
    call['params']['powerMultiplier'] = call['params'].pop('damageMultiplier')
    assert not validate_runtime_program(doc)['ok']  # retired fresh spelling is not another design branch


@pytest.mark.parametrize('retention', [0, 0.5, 1])
def test_bounce_retention_and_declared_omission_have_exact_provenance(retention):
    doc, call = fixture('set_projectile_collision')
    call['params'].update(bounceCount=3, bounceSpeedRetention=retention)
    wire = compile_runtime_program(doc)
    assert entity(wire)['collision']['bounceSpeedRetention'] == retention
    assert validate_runtime_wire(wire)['ok']
    call['params'].pop('bounceSpeedRetention')
    neutral = compile_runtime_program(doc)
    assert entity(neutral)['collision']['bounceSpeedRetention'] == 1
    row = next(r for r in neutral['runtimeContract']['finalWireReceipts']
               if r.get('callId') == call['id'] and r['authoredPath'].endswith('.params.bounceSpeedRetention'))
    assert row['value'] == 1 and row['status'] == 'declared_neutral_omission'


@pytest.mark.parametrize('fn,key,value', [
    ('move_orbit', 'turnRadiansPerSecond', None), ('move_orbit', 'turnRadiansPerSecond', True),
    ('move_orbit', 'turnRadiansPerSecond', float('inf')),
    ('charge_then_release', 'damageMultiplier', 0.5), ('charge_then_release', 'speedMultiplier', 0),
    ('charge_then_release', 'knockbackMultiplier', -0.1),
    ('set_projectile_collision', 'bounceSpeedRetention', 1.01),
    ('set_projectile_collision', 'bounceSpeedRetention', None),
])
def test_invalid_present_choice_is_not_replaced(fn, key, value):
    doc, call = fixture(fn)
    call['params'][key] = value
    assert not validate_runtime_program(doc)['ok']
    with pytest.raises(ValueError): compile_runtime_program(doc)


def test_retained_wire_absence_is_read_only_and_foreign_or_incomplete_extensions_refuse():
    for fn, component, fields in [('charge_then_release', 'controller', ('chargeDamageMultiplier', 'knockbackMultiplier', 'speedMultiplier')),
                                   ('move_orbit', 'movement', ('orbitRadiansPerUpdate',)),
                                   ('set_projectile_collision', 'collision', ('bounceSpeedRetention',))]:
        doc, _ = fixture(fn)
        wire = compile_runtime_program(doc)
        wire.pop('runtimeContract')
        selected = entity(wire)[component]
        params = selected['params'] if component != 'collision' else selected
        for field in fields: params.pop(field)
        before = deepcopy(wire)
        assert validate_runtime_wire(wire)['ok'] and wire == before
        params[fields[0]] = None
        assert not validate_runtime_wire(wire)['ok']
    doc, _ = fixture('charge_then_release')
    wire = compile_runtime_program(doc); wire.pop('runtimeContract')
    entity(wire)['controller']['params'].pop('speedMultiplier')
    assert not validate_runtime_wire(wire)['ok']
    doc, _ = fixture('move_orbit'); wire = compile_runtime_program(doc); wire.pop('runtimeContract')
    entity(wire)['movement'].update(name='move_straight', code=0)
    assert not validate_runtime_wire(wire)['ok']


def test_repair_only_changes_invalid_channel_and_keeps_valid_charge_channels_frozen():
    good, call = fixture('charge_then_release')
    call['params'].update(damageMultiplier=3, knockbackMultiplier=0.25, speedMultiplier=0.5)
    broken = deepcopy(good)
    bad = next(c for c in broken['runtimeProgram']['calls'] if c['id'] == call['id'])
    bad['params']['speedMultiplier'] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)['errors'])
    assert scope['fieldPermissions']['calls'] == [{'id': call['id'], 'paths': ['params.speedMultiplier']}]
    hostile = deepcopy(call); hostile['params']['damageMultiplier'] = 4
    patch, audit = filter_repair_patch_scope(broken, {'callsUpsert': [hostile], 'note': 'one channel'}, scope)
    assert audit['ignoredChanges'] and apply_repair_patch(broken, patch) == good


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_actual_author_packet_teaches_native_semantics_and_independent_choices(monkeypatch, mode):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    _, user, _ = build_initial_author_request({}, {}, 'projectile-controls', model_name='test-model')
    cards = {c['fn']: c for c in json.loads(user)['runtimeCapabilityContract']['catalog']['capabilities']}
    assert 'powerMultiplier' not in cards['charge_then_release']['params']
    assert {'damageMultiplier', 'knockbackMultiplier', 'speedMultiplier'} <= cards['charge_then_release']['params'].keys()
    assert 'clockwise' in cards['move_orbit']['does'] and 'counterclockwise' in cards['move_orbit']['does']
    meaning = cards['set_projectile_collision']['params']['bounceSpeedRetention']['meaning']
    assert 'collided velocity axis' in meaning and 'Tangential speed is unchanged' in meaning
    assert 'No friction' in meaning
    assert set(CAPABILITY_REGISTRY['move_orbit'].params) <= cards['move_orbit']['params'].keys()


@pytest.mark.parametrize('field', ['damageMultiplier', 'knockbackMultiplier', 'speedMultiplier'])
@pytest.mark.parametrize('value', [1.0000000001, 0.9999999999])
def test_charge_cannot_collapse_nonneutral_author_input_to_neutral_float(field, value):
    doc, call = fixture('charge_then_release')
    call['params'][field] = value
    assert not validate_runtime_program(doc)['ok']
    with pytest.raises(ValueError): compile_runtime_program(doc)


@pytest.mark.parametrize('mutation', ['duration', 'mixed_coupled'])
def test_independent_wire_rejects_pre_normalization_errors(mutation):
    doc, _ = fixture('charge_then_release')
    wire = compile_runtime_program(doc); wire.pop('runtimeContract')
    params = entity(wire)['controller']['params']
    if mutation == 'duration': params['chargeTicks'] = 700
    else: params['powerMultiplier'] = 2
    assert not validate_runtime_wire(wire)['ok']
