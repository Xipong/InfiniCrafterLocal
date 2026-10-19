"""Frozen played A2/A3/A4: future admission/projection, never saved-item rewrites.

Author fixture: exact JSON values from frozen prompt_trace.ndjson response lines
24 (A2), 67 (A3), 53/60/46/38/89 (A4), world 853355558; not truncated debug text.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


from captured_projectile_author import project_captured_world_units


_CAPTURED = json.loads((Path(__file__).with_name('fixtures') / 'played_a2_a3_a4_author.json').read_text())
CAPTURES = {key: project_captured_world_units(value) for key, value in _CAPTURED.items()}
DOOR = 'g_90e0879b1756a18b'
PICK = 'g_fb3aca59f2dc1ac3'
SPEARS = tuple(key for key in CAPTURES if key not in (DOOR, PICK))


def call(doc, fn):
    return next(row for row in doc['runtimeProgram']['calls'] if row['fn'] == fn)


def test_a2_exact_door_refuses_nonchannel_active_flail_without_mutation():
    doc = deepcopy(CAPTURES[DOOR])
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert [row['code'] for row in report['errors']] == ['missing_item_capability_param']
    assert report['errors'][0]['allowed'] == ['configure_item_use.channel=true']
    assert doc == before
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


def test_a2_repair_thaws_only_channel_not_movement_or_valid_siblings():
    doc = deepcopy(CAPTURES[DOOR])
    use = call(doc, 'configure_item_use')
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    assert scope['fieldPermissions']['calls'] == [{'id': use['id'], 'paths': ['params.channel']}]
    hostile = deepcopy(use)
    hostile['params'].update(channel=True, autoReuse=not use['params']['autoReuse'])
    patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [hostile], 'note': 'exact channel'}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(doc)
    call(expected, 'configure_item_use')['params']['channel'] = True
    assert audit['ok'] and audit['ignoredChanges']
    assert repaired == expected and doc == CAPTURES[DOOR]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)['ok']
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'],
                                   authored_document=repaired, final_document=wire)['ok']


@pytest.mark.parametrize('lane', ['primary_use', 'alternate_use'])
@pytest.mark.parametrize('channel', [False, True])
def test_a2_active_root_dependency_is_exact_target_and_input(lane, channel):
    doc = deepcopy(CAPTURES[DOOR])
    doc['runtimeProgram']['bindings'] = [doc['runtimeProgram']['bindings'][0]]
    doc['runtimeProgram']['calls'] = [row for row in doc['runtimeProgram']['calls']
                                    if row['fn'] != 'configure_tile_placement']
    doc['runtimeProgram']['bindings'][0]['input'] = lane
    call(doc, 'configure_item_use')['params']['channel'] = channel
    assert validate_runtime_program(doc)['ok'] is channel


def test_a2_passive_offhand_flail_can_use_owner_channel_without_item_channel_dependency():
    doc = deepcopy(CAPTURES[DOOR])
    program = doc['runtimeProgram']
    program['bindings'] = [dict(program['bindings'][0], input='hold')]
    program['calls'] = [row for row in program['calls'] if row['fn'] != 'configure_tile_placement']
    # Hold does not call native StartChanneling(Item). It may coexist with a
    # different active channel source; forcing this item's flag proves nothing.
    assert call(doc, 'configure_item_use')['params']['channel'] is False
    assert validate_runtime_program(doc)['ok']
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']


def test_a2_event_flail_preserves_owner_driven_composition_without_forcing_channel():
    doc = deepcopy(CAPTURES[DOOR])
    program = doc['runtimeProgram']
    body = next(row['id'] for row in program['entities'] if row['kind'] == 'item_body')
    target = call(doc, 'move_flail_tether')['target']
    program['primaryEntityId'] = body
    program['bindings'] = [{'id': 'body', 'input': 'primary_use',
                            'action': {'kind': 'use_item_body', 'targetId': body},
                            'stackCost': 0, 'contactDamage': False}]
    program['calls'] = [row for row in program['calls'] if row['fn'] != 'configure_tile_placement']
    program['calls'].append({'id': 'event_flail', 'fn': 'spawn_entity_on_event', 'target': body,
        'params': {'when': 'on_use', 'entity': target, 'count': 1, 'spreadRadians': 0,
                   'damageMultiplier': 1, 'delaySeconds': (0) / 60, 'damageBasis': 'authored_child',
                   'knockbackBasis': 'authored_child'}})
    assert call(doc, 'configure_item_use')['params']['channel'] is False
    assert validate_runtime_program(doc)['ok']
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']


@pytest.mark.parametrize('lane,expected', [('primary_use', False), ('hold', True)])
def test_a2_missing_movement_repair_filters_conditional_flail_by_actual_producer(lane, expected):
    doc = deepcopy(CAPTURES[DOOR])
    flail = call(doc, 'move_flail_tether')
    doc['runtimeProgram']['bindings'] = [dict(doc['runtimeProgram']['bindings'][0], input=lane)]
    doc['runtimeProgram']['calls'] = [row for row in doc['runtimeProgram']['calls']
                                    if row['fn'] not in ('move_flail_tether', 'configure_tile_placement')]
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    requirements = next(row for row in scope['repairRequirements'] if row['code'] == 'missing_movement_component')
    assert ('move_flail_tether' in requirements['requiredOneOfCapabilities']) is expected
    if expected:
        patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [flail], 'note': 'owner-driven movement'}, scope)
        repaired = apply_repair_patch(doc, patch)
        assert audit['ok'] and validate_runtime_program(repaired)['ok']
        assert call(repaired, 'configure_item_use')['params']['channel'] is False
        assert validate_runtime_wire(compile_runtime_program(repaired))['ok']


@pytest.mark.parametrize('invalid', [None, 1, 'true'])
def test_a2_channel_dependency_does_not_accept_truthy_or_null_values(invalid):
    doc = deepcopy(CAPTURES[DOOR])
    call(doc, 'configure_item_use')['params']['channel'] = invalid
    assert not validate_runtime_program(doc)['ok']



def yoyo_witness():
    doc = deepcopy(CAPTURES[DOOR])
    program = doc['runtimeProgram']
    program['bindings'] = [program['bindings'][0]]
    program['calls'] = [row for row in program['calls'] if row['fn'] != 'configure_tile_placement']
    movement = call(doc, 'move_flail_tether')
    movement['fn'] = 'move_yoyo_hover'
    movement['params'] = {'rangeTiles': 10, 'speedBlocksPerSecond': 52.5}
    return doc


@pytest.mark.parametrize('lane', ['primary_use', 'alternate_use'])
@pytest.mark.parametrize('channel', [False, True])
def test_active_yoyo_requires_explicit_native_channel(lane, channel):
    doc = yoyo_witness()
    doc['runtimeProgram']['bindings'][0]['input'] = lane
    call(doc, 'configure_item_use')['params']['channel'] = channel
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report['ok'] is channel
    assert doc == before
    if not channel:
        assert [row['code'] for row in report['errors']] == ['missing_item_capability_param']
        assert report['errors'][0]['allowed'] == ['configure_item_use.channel=true']
        with pytest.raises(ValueError):
            compile_runtime_program(doc)
    else:
        wire = compile_runtime_program(doc)
        assert validate_runtime_wire(wire)['ok']
        assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'],
                                       authored_document=doc, final_document=wire)['ok']


def test_yoyo_repair_thaws_only_explicit_channel_dependency():
    doc = yoyo_witness()
    before = deepcopy(doc)
    use = call(doc, 'configure_item_use')
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    assert scope['fieldPermissions']['calls'] == [{'id': use['id'], 'paths': ['params.channel']}]
    hostile = deepcopy(use)
    hostile['params'].update(channel=True, autoReuse=not use['params']['autoReuse'])
    patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [hostile], 'note': 'native channel'}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(doc)
    call(expected, 'configure_item_use')['params']['channel'] = True
    assert audit['ok'] and audit['ignoredChanges']
    assert repaired == expected and doc == before
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)['ok']
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'],
                                   authored_document=repaired, final_document=wire)['ok']


@pytest.mark.parametrize('producer', ['hold', 'event'])
def test_passive_and_event_yoyo_keep_existing_owner_channel_semantics(producer):
    doc = yoyo_witness()
    program = doc['runtimeProgram']
    if producer == 'hold':
        program['bindings'][0]['input'] = 'hold'
    else:
        body = next(row['id'] for row in program['entities'] if row['kind'] == 'item_body')
        target = call(doc, 'move_yoyo_hover')['target']
        program['primaryEntityId'] = body
        program['bindings'] = [{'id': 'body', 'input': 'primary_use',
                               'action': {'kind': 'use_item_body', 'targetId': body},
                               'stackCost': 0, 'contactDamage': False}]
        program['calls'].append({'id': 'event_yoyo', 'fn': 'spawn_entity_on_event', 'target': body,
            'params': {'when': 'on_use', 'entity': target, 'count': 1, 'spreadRadians': 0,
                       'damageMultiplier': 1, 'delaySeconds': (0) / 60, 'damageBasis': 'authored_child',
                       'knockbackBasis': 'authored_child'}})
    assert call(doc, 'configure_item_use')['params']['channel'] is False
    assert validate_runtime_program(doc)['ok']
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']


@pytest.mark.parametrize('lane,expected', [('primary_use', False), ('alternate_use', False), ('hold', True)])
def test_missing_movement_repair_filters_yoyo_by_exact_active_producer(lane, expected):
    doc = yoyo_witness()
    movement = call(doc, 'move_yoyo_hover')
    doc['runtimeProgram']['bindings'][0]['input'] = lane
    doc['runtimeProgram']['calls'].remove(movement)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    requirements = next(row for row in scope['repairRequirements'] if row['code'] == 'missing_movement_component')
    assert ('move_yoyo_hover' in requirements['requiredOneOfCapabilities']) is expected
    if expected:
        patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [movement], 'note': 'owner-driven movement'}, scope)
        repaired = apply_repair_patch(doc, patch)
        assert audit['ok'] and validate_runtime_program(repaired)['ok']
        assert call(repaired, 'configure_item_use')['params']['channel'] is False
        assert validate_runtime_wire(compile_runtime_program(repaired))['ok']


def test_a3_frozen_pick_primary_mining_and_alternate_recall_remain_authored():
    doc = deepcopy(CAPTURES[PICK])
    wire = compile_runtime_program(doc)
    assert validate_runtime_program(doc)['ok'] and validate_runtime_wire(wire)['ok']
    assert wire['gameplay']['pickPower'] == 35
    assert [row['usePolicy']['action']['kind'] for row in wire['runtimeProgram']['bindings']] == ['use_item_body', 'apply_item_effects']
    assert doc == CAPTURES[PICK]


@pytest.mark.parametrize('key', SPEARS)
def test_a4_five_exact_code19_compositions_keep_mechanics_with_truthful_live_aim_card(key):
    doc = deepcopy(CAPTURES[key])
    assert 'initial' in doc['realization']['description'].lower()
    wire = compile_runtime_program(doc)
    movement = next(row['movement'] for row in wire['runtimeProgram']['entities'] if row.get('movement', {}).get('code') == 19)
    assert movement['name'] == 'move_forward_then_retract'
    card = CAPABILITY_REGISTRY['move_forward_then_retract'].prompt_card()
    text = json.dumps(card).lower()
    assert 'live owner cursor' in text and 'every ai update' in text
    assert 'not a fixed initial' in text and 'not hand-attached' in text
    assert doc == CAPTURES[key]
