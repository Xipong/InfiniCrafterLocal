"""Played RAW stays frozen: retired Author/wire refusals and current controls.

Fresh dependency/Repair controls explicitly compose independent components. These
are not retrofits of the A2/A3/A4 items or claims of final PNG-ready delivery.
"""
from suite_paths import TEST_ROOT
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

_FIXTURES = (TEST_ROOT / 'fixtures')
_CAPTURED = json.loads((_FIXTURES / 'played_a2_a3_a4_author.json').read_text())
CAPTURES = _CAPTURED
DOOR = 'g_90e0879b1756a18b'
PICK = 'g_fb3aca59f2dc1ac3'
SPEARS = tuple(key for key in CAPTURES if key not in (DOOR, PICK))


def call(doc, fn):
    return next(row for row in doc['runtimeProgram']['calls'] if row['fn'] == fn)


def release_witness(cursor=False):
    """Explicit future composition, deliberately separate from captured Author."""
    doc = build_capability_witness('move_straight')
    program = doc['runtimeProgram']
    target = next(row['target'] for row in program['calls'] if row['fn'] == 'move_straight')
    program['calls'].append({'id': 'explicit_return', 'fn': 'return_when', 'target': target,
        'params': {'onOwnerRelease': True, 'onTileCollision': False, 'passTilesOnReturn': False}})
    if cursor:
        program['calls'].append({'id': 'cursor_seek', 'fn': 'seek', 'target': target,
            'params': {'target': 'cursor', 'maxSpeed': 52.5, 'lerpPerUpdate': 1,
                       'limitSpeedToDistance': True, 'cursorLeashBlocks': 10, 'window': {'phase': 'outbound'}}})
    program['calls'].extend([
        {'id': 'return_seek', 'fn': 'seek', 'target': target,
         'params': {'target': 'owner_center', 'maxSpeed': 60, 'lerpPerUpdate': 1,
                    'limitSpeedToDistance': True, 'window': {'phase': 'returning'}}},
        {'id': 'return_arrival', 'fn': 'kill_on_arrival', 'target': target,
         'params': {'target': 'owner_center', 'radius': 1, 'window': {'phase': 'returning'}}},
    ])
    return doc


def _only_projectile_lane(doc, lane='primary_use'):
    program = doc['runtimeProgram']
    program['bindings'] = [dict(program['bindings'][0], input=lane)]
    program['calls'] = [row for row in program['calls'] if row['fn'] != 'place_tile']
    return doc


def _compile_receipts(doc):
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)['ok']
    for source in (doc, None):
        assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'],
                                      authored_document=source, final_document=wire)['ok']
    assert doc == before
    return wire


def test_a2_exact_door_refuses_retired_author_without_mutation():
    doc = deepcopy(CAPTURES[DOOR])
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    old = call(doc, 'move_flail_tether')
    index = doc['runtimeProgram']['calls'].index(old)
    assert any(row['code'] == 'unknown_capability' and row['path'] == f'$.runtimeProgram.calls[{index}].fn'
               for row in report['errors'])
    assert old['fn'] not in CAPABILITY_REGISTRY
    assert doc == before
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


@pytest.mark.parametrize('cursor', [False, True], ids=['return', 'cursor-seek-return'])
def test_release_repair_thaws_only_channel_not_motion_or_valid_siblings(cursor):
    doc = _only_projectile_lane(release_witness(cursor))
    before = deepcopy(doc)
    use = call(doc, 'item_use')
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    assert scope['fieldPermissions']['calls'] == [{'id': use['id'], 'paths': ['params.channel']}]
    hostile = deepcopy(use)
    hostile['params'].update(channel=True, autoReuse=not use['params']['autoReuse'])
    patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [hostile], 'note': 'exact channel'}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(doc)
    call(expected, 'item_use')['params']['channel'] = True
    assert audit['ok'] and audit['ignoredChanges']
    assert repaired == expected and doc == before
    wire = _compile_receipts(repaired)
    entity = next(e for e in wire['runtimeProgram']['entities'] if e['id'] == call(doc, 'return_when')['target'])
    assert entity['returnTrigger']['onOwnerRelease'] is True
    assert len(entity['seek']) == (2 if cursor else 1)
    assert entity['arrival']['action'] == 'kill'
    assert 'rotation' not in entity and 'controller' not in entity


@pytest.mark.parametrize('lane', ['primary_use', 'alternate_use'])
@pytest.mark.parametrize('channel', [False, True])
@pytest.mark.parametrize('cursor', [False, True])
def test_release_active_root_dependency_is_exact_target_and_input(lane, channel, cursor):
    doc = _only_projectile_lane(release_witness(cursor), lane)
    call(doc, 'item_use')['params']['channel'] = channel
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report['ok'] is channel, report
    assert doc == before
    if channel:
        _compile_receipts(doc)
    else:
        assert [row['code'] for row in report['errors']] == ['missing_item_capability_param']
        assert report['errors'][0]['allowed'] == ['item_use.channel=true']
        with pytest.raises(ValueError):
            compile_runtime_program(doc)


@pytest.mark.parametrize('cursor', [False, True])
@pytest.mark.parametrize('producer', ['hold', 'event'])
def test_passive_and_event_release_keep_owner_channel_semantics_without_item_channel(producer, cursor):
    doc = _only_projectile_lane(release_witness(cursor))
    program = doc['runtimeProgram']
    if producer == 'hold':
        program['bindings'][0]['input'] = 'hold'
    else:
        body = next(row['id'] for row in program['entities'] if row['kind'] == 'item_body')
        target = call(doc, 'return_when')['target']
        program['primaryEntityId'] = body
        program['bindings'] = [{'id': 'body', 'input': 'primary_use',
                               'action': {'kind': 'use_item_body', 'targetId': body},
                               'stackCost': 0, 'contactDamage': False}]
        program['calls'].append({'id': 'event_release', 'fn': 'spawn_on_event', 'target': body,
            'params': {'when': 'on_use', 'entity': target, 'count': 1, 'spreadRadians': 0,
                       'damageMultiplier': 1, 'delay': 0, 'damageBasis': 'authored_child',
                       'knockbackBasis': 'authored_child'}})
    assert call(doc, 'item_use')['params']['channel'] is False
    assert validate_runtime_program(doc)['ok'], validate_runtime_program(doc)
    _compile_receipts(doc)


@pytest.mark.parametrize('lane', ['primary_use', 'alternate_use', 'hold'])
@pytest.mark.parametrize('retired', ['move_flail_tether', 'move_yoyo_hover'])
def test_missing_movement_repair_never_offers_retired_author_for_any_producer(lane, retired):
    doc = _only_projectile_lane(build_capability_witness('move_straight'), lane)
    movement = call(doc, 'move_straight')
    target = movement['target']
    doc['runtimeProgram']['calls'].remove(movement)
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    requirement = next(row for row in scope['repairRequirements'] if row['code'] == 'missing_movement_component')
    assert retired not in requirement['requiredOneOfCapabilities']
    assert 'move_straight' in requirement['requiredOneOfCapabilities']
    assert scope['create']['calls']['allowedTargetIds'] == [target]
    replacement = {'id': 'new_motion', 'fn': 'move_straight', 'target': target, 'params': {}}
    patch, audit = filter_repair_patch_scope(doc, {'callsUpsert': [replacement], 'note': 'explicit motion'}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(doc)
    expected['runtimeProgram']['calls'].append(replacement)
    assert audit['ok'] and repaired == expected and doc == before
    assert call(repaired, 'item_use')['params']['channel'] is False
    _compile_receipts(repaired)


@pytest.mark.parametrize('invalid', [None, 1, 'true'])
def test_channel_dependency_does_not_accept_truthy_or_null_values(invalid):
    doc = _only_projectile_lane(release_witness())
    call(doc, 'item_use')['params']['channel'] = invalid
    before = deepcopy(doc)
    assert not validate_runtime_program(doc)['ok'] and doc == before


def test_a3_archived_pick_is_not_imported_as_current_author():
    doc = deepcopy(CAPTURES[PICK])
    before = deepcopy(doc)
    assert not validate_runtime_program(doc)['ok']
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before


@pytest.mark.parametrize('key', SPEARS)
def test_a4_exact_code19_author_is_retired_without_rewriting_captured_mechanics_or_advice(key):
    doc = deepcopy(CAPTURES[key])
    before = deepcopy(doc)
    assert 'initial' in doc['realization']['description'].lower()
    movement = call(doc, 'move_forward_then_retract')
    report = validate_runtime_program(doc)
    index = doc['runtimeProgram']['calls'].index(movement)
    assert any(e['code'] == 'unknown_capability' and e['path'] == f'$.runtimeProgram.calls[{index}].fn' for e in report['errors'])
    assert movement['fn'] not in CAPABILITY_REGISTRY
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before == CAPTURES[key]


@pytest.mark.parametrize('case_id,code', [('door_on_chain', 16), ('umbrella_grenade', 17), ('shield_and_disc', 19)])
def test_saved_motion_programs_are_refused_without_recompiling_retired_author(case_id, code):
    path = _FIXTURES / 'runtime_program_v5_seed_corpus.json'
    raw = path.read_bytes()
    row = next(c for c in json.loads(raw)['cases'] if c['caseId'] == case_id)
    full = row['expectedDeliveryWire']
    before = deepcopy(full)
    assert hashlib.sha256(json.dumps(full, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == row['expectedDeliveryWireSha256']
    # Exact archived envelope has the independently retired tooltip root. Do not
    # call it final-delivery GREEN or change the archive to hide that refusal.
    assert not validate_runtime_wire(full)['ok']
    # Isolate the retired movement in an admitted current envelope: it still refuses.
    from infini_local.qa.capability_witnesses import build_capability_witness
    program_control = compile_runtime_program(build_capability_witness('move_straight'))
    program_control.pop('runtimeContract')
    saved_movement = next(e['movement'] for e in full['runtimeProgram']['entities']
                          if e.get('movement', {}).get('code') == code)
    current_body = next(e for e in program_control['runtimeProgram']['entities'] if 'movement' in e)
    current_body['movement'] = deepcopy(saved_movement)
    assert not validate_runtime_wire(program_control)['ok']
    assert any(e.get('movement', {}).get('code') == code for e in full['runtimeProgram']['entities'])
    assert full == before and path.read_bytes() == raw


@pytest.mark.parametrize('channel', [False, True])
def test_retired_yoyo_author_refusal_is_independent_of_explicit_channel(channel):
    doc = _only_projectile_lane(build_capability_witness('move_straight'))
    old = call(doc, 'move_straight')
    old.update(fn='move_yoyo_hover', params={'range': 10, 'speedBlocksPerSecond': 52.5})
    call(doc, 'item_use')['params']['channel'] = channel
    before = deepcopy(doc)
    index = doc['runtimeProgram']['calls'].index(old)
    report = validate_runtime_program(doc)
    assert any(e['code'] == 'unknown_capability' and e['path'] == f'$.runtimeProgram.calls[{index}].fn'
               for e in report['errors'])
    assert 'move_yoyo_hover' not in CAPABILITY_REGISTRY
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before
