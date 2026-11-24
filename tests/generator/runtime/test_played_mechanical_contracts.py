"""Current projectile producers and frozen owner-release repair."""
from copy import deepcopy

import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

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


@pytest.mark.parametrize('lane,channel,cursor', [
    ('primary_use', False, False),
    ('primary_use', True, True),
    ('alternate_use', False, True),
    ('alternate_use', True, False),
])
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
def test_missing_movement_repairs_the_declared_producer(lane):
    doc = _only_projectile_lane(build_capability_witness('move_straight'), lane)
    movement = call(doc, 'move_straight')
    target = movement['target']
    doc['runtimeProgram']['calls'].remove(movement)
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)['errors'])
    requirement = next(row for row in scope['repairRequirements'] if row['code'] == 'missing_movement_component')
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
