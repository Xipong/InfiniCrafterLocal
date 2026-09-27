import copy

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program,
)
from infini_local.qa.capability_witnesses import build_capability_witness


def call(document, fn):
    return next(row for row in document['runtimeProgram']['calls'] if row['fn'] == fn)


def repair(document, **changes):
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)['errors'])
    patch = {'note': 'exact repair', 'realizationReplacement': copy.deepcopy(document['realization']), **changes}
    filtered, audit = filter_repair_patch_scope(document, patch, scope)
    assert audit['ok'], audit
    merged = apply_repair_patch(document, filtered)
    assert validate_runtime_program(merged)['ok'], validate_runtime_program(merged)
    assert compile_runtime_program(merged)
    return merged, audit, scope


def test_placement_reference_admits_binding_without_opening_siblings():
    document = build_capability_witness('configure_placeable')
    binding = next(row for row in document['runtimeProgram']['bindings'] if row['usePolicy']['action']['kind'] == 'place_item')
    candidate = copy.deepcopy(binding)
    binding['usePolicy']['action']['placementCallId'] = 'missing_placement'
    candidate['input'] = 'alternate_use' if binding['input'] == 'primary_use' else 'primary_use'
    merged, audit, scope = repair(document, bindingsUpsert=[candidate])
    actual = next(row for row in merged['runtimeProgram']['bindings'] if row['id'] == binding['id'])
    assert actual['input'] == binding['input']
    assert actual['usePolicy']['action']['placementCallId'] == candidate['usePolicy']['action']['placementCallId']
    assert scope['fieldPermissions']['bindings'] == [{'id': binding['id'], 'paths': ['usePolicy.action.placementCallId']}]
    assert audit['ignoredChanges']


def test_frozen_out_of_range_value_does_not_cancel_damage_repair():
    document = build_capability_witness('configure_item_stats')
    stats = call(document, 'configure_item_stats')
    stats['params']['damage'] = -1
    candidate = copy.deepcopy(stats)
    candidate['params'].update(damage=20, manaCost=-1)
    merged, audit, _ = repair(document, callsUpsert=[candidate])
    expected = dict(stats['params'], damage=20)
    assert call(merged, 'configure_item_stats')['params'] == expected
    assert audit['ignoredChanges']


@pytest.mark.parametrize('sparse', [False, True])
def test_inert_buff_does_not_reauthor_duration_or_unrelated_color(sparse):
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    document = build_capability_witness('apply_generated_buff_on_use')
    buff = call(document, 'apply_generated_buff_on_use')
    cap = CAPABILITY_REGISTRY[buff['fn']]
    for name, spec in cap.params.items():
        if name not in {'durationTicks', 'lightColor'}:
            if sparse and not spec.required:
                buff['params'].pop(name, None)
            else:
                buff['params'][name] = spec.neutral
    buff['params']['durationTicks'] = 60
    buff['params']['lightColor'] = 'blue'
    candidate = copy.deepcopy(buff)
    candidate['params'].update(oreSenseEnabled=True, durationTicks=21600, lightColor='red')
    merged, audit, scope = repair(document, callsUpsert=[candidate])
    assert call(merged, buff['fn'])['params'] == dict(buff['params'], oreSenseEnabled=True)
    permissions = next(row['paths'] for row in scope['fieldPermissions']['calls'] if row['id'] == buff['id'])
    assert 'params.durationTicks' not in permissions
    assert 'params.lightColor' not in permissions
    assert audit['ignoredChanges']


@pytest.mark.parametrize('light_strength', [0, 1])
def test_inert_accessory_only_admits_necessary_missing_color(light_strength):
    document = build_capability_witness('configure_accessory')
    accessory = call(document, 'configure_accessory')
    accessory['params'] = {}
    candidate = copy.deepcopy(accessory)
    candidate['params'] = {'defensePoints': 2, 'lightStrength': light_strength, 'lightColor': 'red'}
    merged, audit, _ = repair(document, callsUpsert=[candidate])
    params = call(merged, accessory['fn'])['params']
    assert ('lightColor' in params) is bool(light_strength)
    if light_strength:
        assert params['lightColor'] == 'red'
    else:
        assert any(row['path'].endswith('.lightColor') for row in audit['ignoredChanges'])


def test_frozen_cross_field_binding_value_does_not_cancel_reference_repair():
    document = build_capability_witness('configure_placeable')
    binding = next(row for row in document['runtimeProgram']['bindings'] if row['usePolicy']['action']['kind'] == 'place_item')
    candidate = copy.deepcopy(binding)
    binding['usePolicy']['action']['placementCallId'] = 'missing_placement'
    candidate['usePolicy'].update(stackCost=0, contactDamage=True)
    merged, audit, _ = repair(document, bindingsUpsert=[candidate])
    actual = next(row for row in merged['runtimeProgram']['bindings'] if row['id'] == binding['id'])
    assert actual['usePolicy']['stackCost'] == 1
    assert actual['usePolicy']['contactDamage'] is False
    assert len(audit['ignoredChanges']) == 2


@pytest.mark.parametrize('mutation', ['type', 'null', 'unknown_key', 'union', 'null_row', 'boolean_as_integer'])
def test_malformed_frozen_patch_is_rejected_before_filter(mutation):
    from infini_local.core.runtime_authoring.program_schema import strict_repair_structure_report
    document = build_capability_witness('configure_item_stats')
    stats = call(document, 'configure_item_stats')
    stats['params']['damage'] = -1
    candidate = copy.deepcopy(stats)
    candidate['params']['damage'] = 20
    if mutation == 'type':
        candidate['params']['manaCost'] = 'bad'
    elif mutation == 'null':
        candidate['params']['manaCost'] = None
    elif mutation == 'unknown_key':
        candidate['params']['unknown'] = None
    elif mutation == 'union':
        candidate['fn'] = 'not_registered'
    elif mutation == 'boolean_as_integer':
        candidate['params']['manaCost'] = False
    elif mutation == 'null_row':
        candidate = None
    patch = {'note': 'repair', 'realizationReplacement': document['realization'], 'callsUpsert': [candidate]}
    assert not strict_repair_structure_report(patch)['ok']
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)['errors'])
    _, audit = filter_repair_patch_scope(document, patch, scope)
    assert not audit['ok']
    assert not audit['acceptedPaths']


def test_in_scope_out_of_range_value_remains_strict_after_merge():
    from infini_local.core.runtime_authoring.program_schema import strict_repair_structure_report
    document = build_capability_witness('configure_item_stats')
    stats = call(document, 'configure_item_stats')
    stats['params']['damage'] = -1
    candidate = copy.deepcopy(stats)
    candidate['params']['damage'] = -2
    patch = {'note': 'repair', 'realizationReplacement': document['realization'], 'callsUpsert': [candidate]}
    assert strict_repair_structure_report(patch)['ok']
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)['errors'])
    _, audit = filter_repair_patch_scope(document, patch, scope)
    assert not audit['ok']


def test_inert_accessory_can_be_deleted_without_reauthoring():
    document = build_capability_witness('configure_accessory')
    armor = copy.deepcopy(call(build_capability_witness('configure_armor'), 'configure_armor'))
    armor['id'] = 'remaining_armor'
    document['runtimeProgram']['calls'].append(armor)
    accessory = call(document, 'configure_accessory')
    accessory['params'] = {}
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)['errors'])
    assert accessory['id'] in scope['deletable']['callIds']
    patch = {'note': 'remove inert call', 'realizationReplacement': document['realization'], 'callIdsDelete': [accessory['id']]}
    filtered, audit = filter_repair_patch_scope(document, patch, scope)
    assert audit['ok'], audit
    assert filtered['callIdsDelete'] == [accessory['id']]
