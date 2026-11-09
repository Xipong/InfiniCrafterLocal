"""Audit #251: provider trust, malformed selectors, graph and native ownership."""
from copy import deepcopy
import json

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author import request as author
from infini_local.pipelines.author import stage
from infini_local.qa.capability_witnesses import build_capability_witness
from repair_test_helpers import offline_builder


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('metadata', [
    {'id': 'g_collision'}, {'id': 1234}, {'recipeKey': 'other_recipe'},
    {'parentA': 'wrong_parent'}, {'parentB': 'wrong_parent'},
    {'debug': {'llmStageAccounting': {'gameplayRepairCalls': 1}}},
    {'debug': []}, {'schemaVersion': 1}, {'runtimeApiVersion': 'injected'},
    {'gameplay': {}}, {'sourceMode': 'cached'},
])
def test_provider_cannot_supply_engine_metadata(monkeypatch, mode, metadata):
    source = build_capability_witness('move_straight')
    source.update(metadata)
    offline_builder(monkeypatch, mode, lambda *a, **kw: {
        'choices': [{'message': {'content': json.dumps(source)}}]})
    for key in ('recipe_one', 'recipe_two'):
        with pytest.raises(PlannerUnavailable, match='engine-owned'):
            author.try_llm_plan({'name': 'Alpha'}, {'name': 'Beta'}, key)


def test_trusted_result_metadata_is_assigned_per_recipe(monkeypatch):
    source = build_capability_witness('move_straight')
    offline_builder(monkeypatch, 'json_object', lambda *a, **kw: {
        'choices': [{'message': {'content': json.dumps(source)}}]})
    results = [author.try_llm_plan({'name': 'Alpha'}, {'name': 'Beta'}, key)
               for key in ('recipe_one', 'recipe_two')]
    assert results[0]['id'] != results[1]['id']
    for key, result in zip(('recipe_one', 'recipe_two'), results):
        assert result['recipeKey'] == key
        assert (result['parentA'], result['parentB']) == ('Alpha', 'Beta')
        assert validate_runtime_wire(compile_runtime_program(result))['ok']
        assert result['debug']['llmStageAccounting']['gameplayAuthorCalls'] == 1


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('malformed', [[], {}, ['set_owner_control'], {'fn': 'set_owner_control'}])
def test_unhashable_fn_reaches_exact_single_gameplay_repair(monkeypatch, mode, malformed):
    source = build_capability_witness('set_owner_control')
    call = next(r for r in source['runtimeProgram']['calls'] if r['fn'] == 'set_owner_control')
    correction = deepcopy(call)
    call['fn'] = malformed
    requests = []
    def respond(request, **kwargs):
        requests.append(request)
        return {'choices': [{'message': {'content': json.dumps({
            'note': 'Restore the authored capability selector', 'callsUpsert': [correction]})}}]}
    offline_builder(monkeypatch, mode, respond)
    assert not strict_author_shape_report(source)['ok']
    report = validate_runtime_program(source)
    assert not report['ok'] and any(r['code'].startswith('shape_') for r in report['errors'])
    result = stage.compile_and_validate_authored_runtime(source, {}, {}, 'invalid_fn',
        run_stage=lambda label, fn, *a, **kw: fn(*a, **kw))
    assert len(requests) == 1 and requests[0]['_infini_stage'] == 'author_repair'
    assert validate_runtime_wire(result)['ok']
    assert result['debug']['gameplayRepairPatch']['callsUpsert'] == [correction]


def _chain(root, depth):
    template = build_capability_witness('move_straight')
    doc = build_capability_witness('accessory' if root == 'equipment' else 'move_straight')
    p = doc['runtimeProgram']
    p['entities'] = [{'id': 'item', 'kind': 'item_body'}]
    p['calls'] = [r for r in p['calls'] if 'target' not in r]
    use = next(r['params'] for r in p['calls'] if r['fn'] == 'item_use')
    use.update(hideUseGraphic=False, disableMeleeHitbox=False)
    if root != 'equipment':
        p['bindings'] = [{'id': 'use', 'input': 'primary_use', 'stackCost': 0,
            'contactDamage': True, 'action': {'kind': 'use_item_body'}}]
    p['primaryEntityId'] = 'item'
    count = depth + (root == 'projectile')
    for i in range(count):
        entity_id = f'child{i}'
        p['entities'].append({'id': entity_id, 'kind': 'free_projectile'})
        for original in template['runtimeProgram']['calls']:
            if 'target' not in original:
                continue
            row = deepcopy(original)
            row.update(id=f'c{i}_{row["id"]}', target=entity_id)
            p['calls'].append(row)
    if root == 'projectile':
        p['bindings'][0]['action'] = {'kind': 'spawn_entity', 'targetId': 'child0'}
        p['primaryEntityId'] = 'child0'
    for i in range(depth):
        source = f'child{i}' if root == 'projectile' else ('item' if i == 0 else f'child{i-1}')
        target = f'child{i+1}' if root == 'projectile' else f'child{i}'
        event = 'on_spawn' if source != 'item' else ({'everySeconds': 1} if root == 'equipment' else root)
        row = {'id': f'edge{i}', 'fn': 'spawn_on_event', 'params': {
            'when': event, 'entity': target, 'count': 1, 'spreadRadians': 0,
            'damageMultiplier': 1, 'delay': 0, 'damageBasis': 'authored_child', 'knockbackBasis': 'authored_child'}}
        row['target'] = source
        p['calls'].append(row)
    return doc


@pytest.mark.parametrize('root', ['on_use', 'on_hit', 'equipment', 'projectile'])
@pytest.mark.parametrize('depth', [3, 4])
def test_author_depth_matches_native_all_root_graph(root, depth):
    doc = _chain(root, depth)
    assert strict_author_shape_report(doc)['ok']
    report = validate_runtime_program(doc)
    assert report['stats']['spawnGraphDepth'] == depth
    if depth == 3:
        assert report['ok'], report['errors']
        assert validate_runtime_wire(compile_runtime_program(doc))['ok']
    else:
        assert {r['code'] for r in report['errors']} == {'child_depth_budget'}


def _controlled(primary, params):
    doc = build_capability_witness('set_owner_control')
    if not primary:
        doc['runtimeProgram']['primaryEntityId'] = 'item'
        next(r['params'] for r in doc['runtimeProgram']['calls'] if r['fn'] == 'item_use')['hideUseGraphic'] = False
    next(r for r in doc['runtimeProgram']['calls'] if r['fn'] == 'set_owner_control')['params'] = params
    return doc


@pytest.mark.parametrize('params', [
    {'claimHeldProjectile': True}, {'animation': 'keep_alive'}, {'animation': 'match_lifetime'},
    {'lifetime': 'keep_alive'}, {'requireHeldItem': True}, {'requireItemAnimation': True},
])
@pytest.mark.parametrize('primary', [False, True])
def test_held_and_animation_ownership_is_primary_only(primary, params):
    doc = _controlled(primary, params)
    unsupported = not primary and ('claimHeldProjectile' in params or 'animation' in params)
    report = validate_runtime_program(doc)
    assert report['ok'] is not unsupported, report
    if unsupported:
        assert {r['code'] for r in report['errors']} == {'incompatible_param_variant'}
        # Wire input from an external writer must be rejected independently too.
        wire = compile_runtime_program(_controlled(True, params))
        wire.pop('runtimeContract')
        wire['runtimeProgram']['primaryEntityId'] = 'item'
        wire['runtimeProgram']['primaryOwner'] = 'item_body'
        wire['runtimeProgram']['itemUse']['hideUseGraphic'] = False
        wire_report = validate_runtime_wire(wire)
        assert 'incompatible_param_variant' in {r['code'] for r in wire_report['errors']}
        assert any('.ownerControl.' in r['path'] for r in wire_report['errors'])
    else:
        assert validate_runtime_wire(compile_runtime_program(doc))['ok']


@pytest.mark.parametrize('witness', ['move_straight', 'accessory', 'equipment_damage_bonus'])
@pytest.mark.parametrize('malformed', [[], {}])
def test_each_capability_position_retains_structural_diagnostics(witness, malformed):
    source = build_capability_witness(witness)
    for index in range(len(source['runtimeProgram']['calls'])):
        candidate = deepcopy(source)
        candidate['runtimeProgram']['calls'][index]['fn'] = malformed
        report = validate_runtime_program(candidate)
        assert not report['ok']
        assert any(r['path'].startswith(f'$.runtimeProgram.calls[{index}]')
                   and r['code'].startswith('shape_') for r in report['errors'])


@pytest.mark.parametrize('root', ['on_use', 'on_hit', 'equipment', 'projectile'])
def test_final_wire_rejects_the_fourth_edge_independently(root):
    wire = compile_runtime_program(_chain(root, 3))
    wire.pop('runtimeContract')  # Delivery DTOs legitimately carry no internal provenance.
    entities = wire['runtimeProgram']['entities']
    child = deepcopy(entities[-1])
    child['id'] = 'overflow_child'
    entities.append(child)
    event = deepcopy(entities[-3]['events'][0])
    event.update(id='overflow_edge', entityId='overflow_child')
    entities[-2]['events'] = [event]
    report = validate_runtime_wire(wire)
    assert 'entity_graph_depth_exceeded' in {r['code'] for r in report['errors']}


def test_secondary_owner_repair_keeps_liveness_and_valid_guards_frozen(monkeypatch):
    source = _controlled(False, {'claimHeldProjectile': True, 'animation': 'keep_alive',
                                'requireHeldItem': True, 'lifetime': 'keep_alive'})
    control = next(r for r in source['runtimeProgram']['calls'] if r['fn'] == 'set_owner_control')
    correction = deepcopy(control)
    correction['params'].update(claimHeldProjectile=False, animation='none')
    attempted = deepcopy(correction)
    attempted['params'].update(requireHeldItem=False, lifetime='authored')
    requests = []
    def respond(request, **kwargs):
        requests.append(request)
        return {'choices': [{'message': {'content': json.dumps({
            'note': 'Keep secondary liveness, remove only unsupported owner writers', 'callsUpsert': [attempted]})}}]}
    offline_builder(monkeypatch, 'json_object', respond)
    result = stage.compile_and_validate_authored_runtime(source, {}, {}, 'secondary_control',
        run_stage=lambda label, fn, *a, **kw: fn(*a, **kw))
    assert len(requests) == 1
    assert result['debug']['gameplayRepairPatch']['callsUpsert'] == [correction]
    assert result['debug']['gameplayRepairFilterAudit']['ignoredChanges']
    assert validate_runtime_wire(result)['ok']
