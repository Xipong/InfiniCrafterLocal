"""Fresh late scaling, temporal composition, and frozen historical delivery."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def document(params):
    doc = build_capability_witness('scale_velocity')
    row = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'scale_velocity')
    row['params'] = params
    return doc, row


def window(start):
    return {'phase':'always','clock':'active','startDelay':start,'duration':1}


@pytest.mark.parametrize('multiplier', [0, .2, 1, 1.2])
def test_no_cap_is_absent_and_exact_multiplier_survives_provider_and_wire(multiplier):
    doc, _ = document({'scalePerUpdate':multiplier})
    wire = compile_runtime_program(doc)
    entity = next(e for e in wire['runtimeProgram']['entities'] if 'velocityScale' in e)
    assert entity['velocityScale'] == [{'multiplierPerUpdate':multiplier}]
    assert validate_runtime_wire(wire)['ok']
    wire.pop('runtimeContract')
    assert validate_runtime_wire(wire)['ok']
    schema = CAPABILITY_REGISTRY['scale_velocity'].provider_variant_schema()
    assert 'maxSpeed' not in schema['properties']['params']['required']


def test_acceleration_then_braking_has_independent_call_receipts_and_refuses_overlap():
    doc, first = document({'scalePerUpdate':1.1,'window':window(0)})
    second = deepcopy(first); second['id'] += '_brake'
    second['params'] = {'scalePerUpdate':.2,'maxSpeed':30,'window':window(1)}
    doc['runtimeProgram']['calls'].append(second)
    wire = compile_runtime_program(doc)
    entity = next(e for e in wire['runtimeProgram']['entities'] if 'velocityScale' in e)
    assert entity['velocityScale'][1]['maxSpeed'] == 8
    assert [r['window']['startDelayTicks'] for r in entity['velocityScale']] == [0,60]
    assert validate_runtime_wire(wire)['ok']
    for index, call in enumerate((first,second)):
        assert {r['callId'] for r in wire['runtimeContract']['finalWireReceipts'] if f'.velocityScale[{index}].' in r['finalPath']} == {call['id']}
    second['params']['window'] = window(0)
    assert not validate_runtime_program(doc)['ok']
    entity['velocityScale'][1]['window']['startDelayTicks'] = 0
    wire.pop('runtimeContract')
    assert not validate_runtime_wire(wire)['ok']


def test_distinct_return_phases_and_maximum_two_instances():
    doc, first = document({'scalePerUpdate':1.1,'window':{'phase':'outbound'}})
    second = deepcopy(first); second['id'] += '_return'; second['params'] = {'scalePerUpdate':.5,'window':{'phase':'returning'}}
    doc['runtimeProgram']['calls'] += [second, {'id':'return','target':first['target'],'fn':'return_when','params':{'afterSeconds':1}}]
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']
    third=deepcopy(second);third['id'] += '_third';doc['runtimeProgram']['calls'].append(third)
    assert not validate_runtime_program(doc)['ok']


@pytest.mark.parametrize('params', [{'scalePerUpdate':None},{'scalePerUpdate':False},{'scalePerUpdate':-.1},{'scalePerUpdate':1.21},{'scalePerUpdate':1,'maxSpeed':None},{'scalePerUpdate':1,'stage':'early'}])
def test_invalid_choices_never_default(params):
    doc, _ = document(params)
    assert not validate_runtime_program(doc)['ok']


@pytest.mark.parametrize('fn',['multiply_projectile_velocity','set_projectile_speed_modifier'])
def test_retired_item_envelope_refuses_but_saved_velocity_component_stays_readable(fn):
    wire=json.loads((Path(__file__).parent/'fixtures'/'velocity_compat'/f'{fn}.json').read_text())
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report['ok']
    assert any(e['path'] == '$.runtimeProgram.itemUse.releaseTiming' for e in report['errors'])
    assert not CAPABILITY_REGISTRY[fn].author_visible
    doc,row=document({"scalePerUpdate":1}); row["fn"]=fn
    assert not validate_runtime_program(doc)['ok']
    component = 'velocityRetention' if fn == 'multiply_projectile_velocity' else 'speedModifier'
    saved = next(e[component] for e in wire['runtimeProgram']['entities'] if component in e)
    current = compile_runtime_program(document({'scalePerUpdate': 1})[0])
    current.pop('runtimeContract')
    entity = next(e for e in current['runtimeProgram']['entities'] if 'velocityScale' in e)
    del entity['velocityScale']
    entity[component] = deepcopy(saved)
    assert validate_runtime_wire(current)['ok']
    assert entity[component] == saved and wire == before


def test_repair_bad_multiplier_does_not_insert_frozen_absent_cap_or_change_window():
    doc, row=document({'scalePerUpdate':-1,'window':window(0)})
    before=deepcopy(doc)
    scope=build_runtime_repair_scope(doc,validate_runtime_program(doc)['errors'])
    hostile=deepcopy(row);hostile['params'].update(scalePerUpdate=.5,maxSpeed=20,window=window(1))
    patch,audit=filter_repair_patch_scope(doc,{'callsUpsert':[hostile],'note':'repair'},scope)
    repaired=apply_repair_patch(doc,patch)
    target=next(c for c in repaired['runtimeProgram']['calls'] if c['id']==row['id'])
    assert target['params']=={'scalePerUpdate':.5,'window':window(0)}
    assert audit['ignoredChanges'] and doc==before
    assert validate_runtime_wire(compile_runtime_program(repaired))['ok']


def test_different_clocks_without_exclusive_phases_are_not_assumed_disjoint():
    doc, first = document({'scalePerUpdate':1.1,'window':window(0)})
    second=deepcopy(first); second['id'] += '_late'
    second['params']['window']={'phase':'always','clock':'since_return','startDelay':10,'duration':1}
    doc['runtimeProgram']['calls'] += [second, {'id':'return','fn':'return_when','target':first['target'],'params':{'afterSeconds':1}}]
    assert not validate_runtime_program(doc)['ok']


@pytest.mark.parametrize('bad', [True, '1', 1e-60, 1.0000000000000002])
def test_new_scaler_preserves_strict_numeric_and_non_neutral_consumer_domain(bad):
    doc,_=document({'scalePerUpdate':bad})
    assert not validate_runtime_program(doc)['ok']


@pytest.mark.parametrize('form', ['pair','window','intersection'])
def test_saved_speed_timing_forms_remain_strict(form):
    archived=json.loads((Path(__file__).parent/'fixtures'/'velocity_compat'/'set_projectile_speed_modifier.json').read_text())
    saved=next(e['speedModifier'] for e in archived['runtimeProgram']['entities'] if 'speedModifier' in e)
    wire=compile_runtime_program(document({'scalePerUpdate': 1})[0])
    wire.pop('runtimeContract')
    entity=next(e for e in wire['runtimeProgram']['entities'] if 'velocityScale' in e)
    del entity['velocityScale']
    speed=entity['speedModifier']=deepcopy(saved)
    speed.update(startDelayTicks=30,durationTicks=60)
    speed.pop('window',None)
    if form != 'pair': speed['window']={'phase':'always','clock':'active','startDelayTicks':15,'durationTicks':120}
    if form == 'window': speed.pop('startDelayTicks');speed.pop('durationTicks')
    assert validate_runtime_wire(wire)['ok']
    speed['startDelayTicks']=None
    assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('mutation',['unknown','cap_bool','cap_null','receipt_deleted','call_reused'])
def test_scale_delivery_rejects_malformed_or_forged_provenance(mutation):
    doc,row=document({'scalePerUpdate':.5,'maxSpeed':20})
    wire=compile_runtime_program(doc)
    entity=next(e for e in wire['runtimeProgram']['entities'] if 'velocityScale' in e)
    if mutation=='unknown': entity['velocityScale'][0]['stage']='early'
    elif mutation=='cap_bool': entity['velocityScale'][0]['maxSpeed']=True
    elif mutation=='cap_null': entity['velocityScale'][0]['maxSpeed']=None
    elif mutation=='receipt_deleted':
        wire['runtimeContract']['finalWireReceipts']=[r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('fn')!='scale_velocity']
    else:
        entity['velocityScale'].append(deepcopy(entity['velocityScale'][0]))
    assert not validate_runtime_wire(wire)['ok']


def test_new_storage_guard_is_declared_without_tightening_historical_collision():
    spec = CAPABILITY_REGISTRY['scale_velocity'].params['scalePerUpdate']
    assert spec.consumer_constraint()['nonzeroMustRemainNonzero'] is True
    assert spec.consumer_value_error(1e-60, wire_value=True) is not None
    old = CAPABILITY_REGISTRY['projectile_collision'].params['bounceSpeedRetention']
    assert not old.consumer_preserve_nonzero
    assert old.consumer_value_error(1e-60, wire_value=True) is None
    wire = json.loads((Path(__file__).parent / 'fixtures' / 'velocity_compat' / 'collision_tiny_retention.json').read_text())
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)['ok']
    wire.pop('runtimeContract')
    assert not validate_runtime_wire(wire)['ok']
    assert wire == {k: v for k, v in before.items() if k != 'runtimeContract'}
    doc = build_capability_witness('projectile_collision')
    row = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'projectile_collision')
    row['params'].update(bounceCount=1, bounceSpeedRetention=1e-60)
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']
    doc, _ = document({'scalePerUpdate':1})
    wire = compile_runtime_program(doc)
    wire.pop('runtimeContract')
    next(e for e in wire['runtimeProgram']['entities'] if 'velocityScale' in e)['velocityScale'][0]['multiplierPerUpdate'] = 1e-60
    assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('first_window', [window(0), None])
def test_overlap_repair_freezes_coefficients_cap_absence_and_function(first_window):
    first_params = {'scalePerUpdate':1.1}
    if first_window is not None:
        first_params['window'] = first_window
    doc, first = document(first_params)
    second = deepcopy(first)
    second['id'] += '_brake'
    second['params'] = {'scalePerUpdate':.9, 'window':window(0)}
    doc['runtimeProgram']['calls'].append(second)
    before = deepcopy(doc)
    errors = validate_runtime_program(doc)['errors']
    assert {e['code'] for e in errors} == {'overlapping_motion_windows'}
    scope = build_runtime_repair_scope(doc, errors)
    assert scope['fieldPermissions']['calls'] == [{'id':second['id'], 'paths':['params.window']}]
    hostile = deepcopy(second)
    hostile['params'].update(window=window(1), scalePerUpdate=.2, maxSpeed=40)
    first_hostile = deepcopy(first)
    first_hostile['params']['scalePerUpdate'] = .8
    patch, audit = filter_repair_patch_scope(doc, {'callsUpsert':[hostile, first_hostile], 'note':'window only'}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(before)
    next(c for c in expected['runtimeProgram']['calls'] if c['id'] == second['id'])['params']['window'] = window(1)
    assert repaired == expected and doc == before and audit['ignoredChanges']
    function_change = deepcopy(second)
    function_change['fn'] = 'rotate_sprite'
    function_change['params'] = {'mode':'velocity', 'window':window(1)}
    function_patch, function_audit = filter_repair_patch_scope(doc, {'callsUpsert':[function_change], 'note':'function stays frozen'}, scope)
    function_result = apply_repair_patch(doc, function_patch)
    kept = next(c for c in function_result['runtimeProgram']['calls'] if c['id'] == second['id'])
    assert kept['fn'] == second['fn'] and kept['params']['scalePerUpdate'] == .9
    assert 'maxSpeed' not in kept['params']
    assert function_audit['ignoredChanges']
    if first_window is not None:
        assert validate_runtime_wire(compile_runtime_program(repaired))['ok']
    else:
        assert not validate_runtime_program(repaired)['ok']
    # Explicitly removing the invalid second instance is also a narrow repair.
    patch, _ = filter_repair_patch_scope(doc, {'callIdsDelete':[second['id']], 'note':'remove overlapping instance'}, scope)
    repaired = apply_repair_patch(doc, patch)
    assert all(c['id'] != second['id'] for c in repaired['runtimeProgram']['calls'])
    assert validate_runtime_wire(compile_runtime_program(repaired))['ok']
