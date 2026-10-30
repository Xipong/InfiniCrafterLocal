"""Independent charge channels, world-time orbit, and literal tile restitution."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def fixture(fn):
    doc = build_capability_witness(fn)
    call = next(c for c in doc['runtimeProgram']['calls'] if c['id'] == 'witness_call')
    if fn == 'charge':
        call['params']['releaseEffect'] = {'launchSpeed': 30}
    return doc, call


def entity(wire):
    return next(e for e in wire['runtimeProgram']['entities'] if e['id'] == 'witness_entity')


@pytest.mark.parametrize('updates', [1, 2, 6])
@pytest.mark.parametrize('rate', [-3.3, 0, 3.3])
def test_orbit_rate_projects_world_time_and_keeps_launch_speed_independent(updates, rate):
    doc, call = fixture('orbit')
    call['params']['radiansPerSecond'] = rate
    collision = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'projectile_collision')
    collision['params']['updatesPerTick'] = updates
    wire = compile_runtime_program(doc)
    projected = entity(wire)['orbit']['radiansPerUpdate']
    assert projected == pytest.approx(rate / (60 * updates))
    assert entity(wire)['orbit']['radiusPx'] == call['params']['radius'] * 16
    assert entity(wire)['spawn']['speedPxPerTick'] == pytest.approx(8 / updates)
    assert entity(wire)['collision']['tileCollide'] is True
    assert validate_runtime_wire(wire)['ok']
    rows = [r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
            and r['authoredPath'].endswith('.params.radiansPerSecond')]
    assert len(rows) == 1 and rows[0]['value'] == projected
    assert rows[0]['finalPath'].endswith('.orbit.radiansPerUpdate')


def test_charge_three_channels_project_without_coupling():
    doc, call = fixture('charge')
    call['params']['releaseEffect'].update(damageMultiplier=3, knockbackMultiplier=0.25, speedMultiplier=0.5)
    wire = compile_runtime_program(doc)
    params = entity(wire)['chargeRelease']
    assert params['damageMultiplier'] == 3 and params['knockbackMultiplier'] == 0.25 and params['speedMultiplier'] == 0.5
    assert validate_runtime_wire(wire)['ok']
    for source, target in [('damageMultiplier', 'damageMultiplier'), ('knockbackMultiplier', 'knockbackMultiplier'), ('speedMultiplier', 'speedMultiplier')]:
        receipt = next(r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('callId') == call['id']
                       and r['authoredPath'].endswith('.params.releaseEffect.' + source))
        assert receipt['finalPath'].endswith('.chargeRelease.' + target)
        assert receipt['value'] == call['params']['releaseEffect'][source]
    call['params']['releaseEffect']['powerMultiplier'] = call['params']['releaseEffect'].pop('damageMultiplier')
    assert not validate_runtime_program(doc)['ok']  # retired fresh spelling is not another design branch


@pytest.mark.parametrize('retention', [0, 0.5, 1])
def test_bounce_retention_and_declared_omission_have_exact_provenance(retention):
    doc, call = fixture('projectile_collision')
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
    ('orbit', 'radiansPerSecond', None), ('orbit', 'radiansPerSecond', True),
    ('orbit', 'radiansPerSecond', float('inf')),
    ('charge', 'damageMultiplier', 0.5), ('charge', 'speedMultiplier', 0),
    ('charge', 'knockbackMultiplier', -0.1),
    ('projectile_collision', 'bounceSpeedRetention', 1.01),
    ('projectile_collision', 'bounceSpeedRetention', None),
])
def test_invalid_present_choice_is_not_replaced(fn, key, value):
    doc, call = fixture(fn)
    params = call['params']['releaseEffect'] if fn == 'charge' else call['params']
    params[key] = value
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
    good, call = fixture('charge')
    call['params']['releaseEffect'].update(damageMultiplier=3, knockbackMultiplier=0.25, speedMultiplier=0.5)
    broken = deepcopy(good)
    bad = next(c for c in broken['runtimeProgram']['calls'] if c['id'] == call['id'])
    bad['params']['releaseEffect']['speedMultiplier'] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)['errors'])
    assert scope['fieldPermissions']['calls'] == [{'id': call['id'], 'paths': ['params.releaseEffect.speedMultiplier']}]
    hostile = deepcopy(call); hostile['params']['releaseEffect']['damageMultiplier'] = 4
    patch, audit = filter_repair_patch_scope(broken, {'callsUpsert': [hostile], 'note': 'one channel'}, scope)
    assert audit['ignoredChanges'] and apply_repair_patch(broken, patch) == good


@pytest.mark.parametrize('field', ['damageMultiplier', 'knockbackMultiplier', 'speedMultiplier'])
@pytest.mark.parametrize('value', [1.0000000001, 0.9999999999])
def test_independent_charge_preserves_native_double_precision_near_neutral(field, value):
    doc, call = fixture('charge')
    call['params']['releaseEffect'][field] = value
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
        doc, _ = fixture('charge')
        wire = compile_runtime_program(doc)
        wire.pop('runtimeContract')
        if mutation == 'duration':
            entity(wire)['charge']['durationTicks'] = 700
        else:
            entity(wire)['chargeRelease']['powerMultiplier'] = 2
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)['ok']
    assert wire == before
