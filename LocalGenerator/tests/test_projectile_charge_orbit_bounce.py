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
    doc, call = fixture('orbit_projectile')
    call['params']['radiansPerSecond'] = rate
    collision = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'set_projectile_collision')
    collision['params']['updatesPerTick'] = updates
    wire = compile_runtime_program(doc)
    projected = entity(wire)['orbit']['radiansPerUpdate']
    assert projected == pytest.approx(rate / (60 * updates))
    assert entity(wire)['orbit']['radiusPx'] == call['params']['radiusBlocks'] * 16
    assert entity(wire)['spawn']['speedPxPerTick'] == pytest.approx(8 / updates)
    assert entity(wire)['collision']['tileCollide'] is True
    assert validate_runtime_wire(wire)['ok']
    rows = [r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
            and r['authoredPath'].endswith('.params.radiansPerSecond')]
    assert len(rows) == 1 and rows[0]['value'] == projected
    assert rows[0]['finalPath'].endswith('.orbit.radiansPerUpdate')


def test_charge_three_channels_project_without_coupling():
    doc, call = fixture('apply_projectile_charge_release')
    call['params'].update(damageMultiplier=3, knockbackMultiplier=0.25, speedMultiplier=0.5)
    wire = compile_runtime_program(doc)
    params = entity(wire)['chargeRelease']
    assert params['damageMultiplier'] == 3 and params['knockbackMultiplier'] == 0.25 and params['speedMultiplier'] == 0.5
    assert validate_runtime_wire(wire)['ok']
    for source, target in [('damageMultiplier', 'damageMultiplier'), ('knockbackMultiplier', 'knockbackMultiplier'), ('speedMultiplier', 'speedMultiplier')]:
        receipt = next(r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
                       and r['authoredPath'].endswith('.params.' + source))
        assert receipt['finalPath'].endswith('.chargeRelease.' + target)
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
    ('orbit_projectile', 'radiansPerSecond', None), ('orbit_projectile', 'radiansPerSecond', True),
    ('orbit_projectile', 'radiansPerSecond', float('inf')),
    ('apply_projectile_charge_release', 'damageMultiplier', 0.5), ('apply_projectile_charge_release', 'speedMultiplier', 0),
    ('apply_projectile_charge_release', 'knockbackMultiplier', -0.1),
    ('set_projectile_collision', 'bounceSpeedRetention', 1.01),
    ('set_projectile_collision', 'bounceSpeedRetention', None),
])
def test_invalid_present_choice_is_not_replaced(fn, key, value):
    doc, call = fixture(fn)
    call['params'][key] = value
    assert not validate_runtime_program(doc)['ok']
    with pytest.raises(ValueError): compile_runtime_program(doc)


def retained_wire(component):
    # Honest minimal synthetic saved-wire controls. No obsolete Author compilation.
    doc, _ = fixture('move_straight')
    wire = compile_runtime_program(doc)
    wire.pop('runtimeContract')
    if component == 'controller':
        wire['runtimeProgram']['itemUse']['channel'] = True
        wire['gameplay']['channel'] = True
        entity(wire)['kind'] = 'owner_attached_projectile'
        entity(wire)['controller'] = {
            'name': 'charge_then_release', 'code': 2,
            'params': {'chargeTicks': 60, 'chargeDamageMultiplier': 3,
                       'knockbackMultiplier': 0.25, 'speedMultiplier': 0.5},
        }
    elif component == 'movement':
        entity(wire)['movement'] = {'name': 'move_orbit', 'code': 4,
                                    'params': {'rangeTiles': 8, 'orbitRadiansPerUpdate': 0.1}}
    assert validate_runtime_wire(wire)['ok']
    return wire


def test_retained_wire_absence_is_read_only_and_foreign_or_incomplete_extensions_refuse():
    for component, fields in [('controller', ('chargeDamageMultiplier', 'knockbackMultiplier', 'speedMultiplier')),
                              ('movement', ('orbitRadiansPerUpdate',)),
                              ('collision', ('bounceSpeedRetention',))]:
        wire = retained_wire(component)
        selected = entity(wire)[component]
        params = selected['params'] if component != 'collision' else selected
        for field in fields:
            params.pop(field)
        before = deepcopy(wire)
        assert validate_runtime_wire(wire)['ok'] and wire == before
        params[fields[0]] = None
        assert not validate_runtime_wire(wire)['ok']
    wire = retained_wire('controller')
    entity(wire)['controller']['params'].pop('speedMultiplier')
    assert not validate_runtime_wire(wire)['ok']
    wire = retained_wire('movement')
    entity(wire)['movement'].update(name='move_straight', code=0)
    assert not validate_runtime_wire(wire)['ok']


def test_repair_only_changes_invalid_channel_and_keeps_valid_charge_channels_frozen():
    good, call = fixture('apply_projectile_charge_release')
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
    assert 'powerMultiplier' not in cards['apply_projectile_charge_release']['params']
    assert {'damageMultiplier', 'knockbackMultiplier', 'speedMultiplier'} <= cards['apply_projectile_charge_release']['params'].keys()
    assert {'charge_then_release', 'move_orbit'}.isdisjoint(cards)
    orbit = cards['orbit_projectile']
    assert 'Signed angular rate' in orbit['params']['radiansPerSecond']['meaning']
    assert 'zero holds phase' in orbit['params']['radiansPerSecond']['meaning']
    assert 'tile collision remains independently authored' in orbit['does']
    meaning = cards['set_projectile_collision']['params']['bounceSpeedRetention']['meaning']
    assert 'collided velocity axis' in meaning and 'Tangential speed is unchanged' in meaning
    assert 'No friction' in meaning
    assert set(CAPABILITY_REGISTRY['orbit_projectile'].params) <= cards['orbit_projectile']['params'].keys()


@pytest.mark.parametrize('field', ['damageMultiplier', 'knockbackMultiplier', 'speedMultiplier'])
@pytest.mark.parametrize('value', [1.0000000001, 0.9999999999])
def test_independent_charge_preserves_native_double_precision_near_neutral(field, value):
    doc, call = fixture('apply_projectile_charge_release')
    call['params'][field] = value
    before = deepcopy(doc)
    if field == 'damageMultiplier' and value < 1:
        assert not validate_runtime_program(doc)['ok']
        with pytest.raises(ValueError):
            compile_runtime_program(doc)
    else:
        wire = compile_runtime_program(doc)
        assert entity(wire)['chargeRelease'][field] == value
        assert entity(wire)['chargeRelease'][field] != 1
        assert validate_runtime_wire(wire)['ok']
    assert doc == before


@pytest.mark.parametrize('field', ['chargeDamageMultiplier', 'knockbackMultiplier', 'speedMultiplier'])
@pytest.mark.parametrize('value', [1.0000000001, 0.9999999999])
def test_retained_charge_wire_keeps_float32_neutral_guard(field, value):
    wire = retained_wire('controller')
    entity(wire)['controller']['params'][field] = value
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)['ok']
    assert wire == before


@pytest.mark.parametrize('mutation', ['duration', 'mixed_coupled'])
@pytest.mark.parametrize('lane', ['independent', 'retained-wire'])
def test_charge_wire_rejects_pre_normalization_errors(mutation, lane):
    if lane == 'retained-wire':
        wire = retained_wire('controller')
        params = entity(wire)['controller']['params']
        if mutation == 'duration':
            params['chargeTicks'] = 700
        else:
            params['powerMultiplier'] = 2
    else:
        doc, _ = fixture('apply_projectile_charge_release')
        wire = compile_runtime_program(doc)
        wire.pop('runtimeContract')
        if mutation == 'duration':
            entity(wire)['charge']['durationTicks'] = 700
        else:
            entity(wire)['chargeRelease']['powerMultiplier'] = 2
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)['ok']
    assert wire == before
