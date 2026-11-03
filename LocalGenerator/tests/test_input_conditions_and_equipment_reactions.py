from copy import deepcopy
import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


def test_two_input_gates_keep_independent_conditions_and_provenance():
    doc = build_capability_witness('use_condition')
    program = doc['runtimeProgram']
    call = next(c for c in program['calls'] if c['id'] == 'witness_call')
    call['params'] = {'input': 'primary_use', 'condition': 'not_wet'}
    alternate = deepcopy(program['bindings'][0]); alternate.update(id='alternate', input='alternate_use')
    program['bindings'].append(alternate)
    second = deepcopy(call); second.update(id='other_condition', params={'input': 'alternate_use', 'condition': {'lifeAtLeast': 50}})
    program['calls'].append(second)
    wire = compile_runtime_program(doc)
    assert wire['gameplay']['useConditions'] == [
        {'input': 'primary_use', 'useConditionMode': 'not_wet'},
        {'input': 'alternate_use', 'useConditionMode': 'life_above', 'useConditionMinLife': 50}]
    assert validate_runtime_wire(wire)['ok']
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'], authored_document=doc, final_document=wire)['ok']
    tampered = deepcopy(wire)
    tampered['gameplay']['useConditions'][1]['input'] = 'primary_use'
    for row in tampered['runtimeContract']['finalWireReceipts']:
        if row.get('callId') == 'other_condition' and row.get('finalPath', '').endswith('.input'):
            row['value'] = 'primary_use'
    assert not audit_compiler_receipts(tampered['runtimeContract']['finalWireReceipts'], authored_document=doc, final_document=tampered)['ok']
    program['calls'][-1]['params']['input'] = 'primary_use'
    assert not validate_runtime_program(doc)['ok']


def reaction(when):
    doc = build_capability_witness('accessory')
    event = deepcopy(next(c for c in build_capability_witness('damage_nearby_on_event')['runtimeProgram']['calls'] if c['id'] == 'witness_call'))
    event.update(id='reaction', target='item')
    event['params']['when'] = when
    doc['runtimeProgram']['calls'].append(event)
    return doc


@pytest.mark.parametrize('event', ['on_hurt', 'on_enemy_kill'])
def test_equipment_reaction_full_compile_wire_and_timer_provenance(event):
    doc = reaction({'on': event, 'cooldown': 1.5})
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    body = next(e for e in wire['runtimeProgram']['entities'] if e['kind'] == 'item_body')
    assert body['events'][0]['event'] == event
    assert body['events'][0]['reactionCooldownTicks'] == 90
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'], authored_document=doc, final_document=wire)['ok']
    del body['events'][0]['reactionCooldownTicks']
    assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('trigger', ['on_hurt','on_enemy_kill', {'on': 'on_hurt', 'cooldown': 0}, {'on': 'on_enemy_kill', 'cooldown': 61}])
def test_reactions_refuse_missing_or_invalid_explicit_cooldown(trigger):
    assert not validate_runtime_program(reaction(trigger))['ok']


def test_reaction_cannot_run_from_unbound_inventory_body():
    doc = reaction({'on': 'on_hurt', 'cooldown': 1})
    doc['runtimeProgram']['bindings'] = []
    assert not validate_runtime_program(doc)['ok']
