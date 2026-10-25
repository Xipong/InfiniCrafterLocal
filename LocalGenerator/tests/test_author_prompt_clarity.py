
"""Model-visible ownership and actual field paths, without runtime design policy."""
import json
import pytest
from infini_local.core import llm_config
from infini_local.pipelines import llm_authoring_pipeline as author


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('fn,leaf,bad_value', [
    ('configure_item_stats', 'damage', True),
    ('set_projectile_lifetime', 'lifetimeSeconds', 0),
    ('move_straight', None, 'missing_entity'),
])
def test_actual_repair_call_guide_has_only_the_scoped_canonical_forms(monkeypatch, mode, fn, leaf, bad_value):
    from copy import deepcopy
    from infini_local.core.runtime_authoring.repair_scope import runtime_repair_schema_capabilities
    from infini_local.pipelines.author_item_contract import author_item_repair_response_schema
    from infini_local.qa.capability_witnesses import build_capability_witness
    from test_repair_gameplay_contract import _offline_gameplay_repair

    source = build_capability_witness(fn)
    broken = deepcopy(source)
    call = next(row for row in broken['runtimeProgram']['calls'] if row['fn'] == fn)
    correction = deepcopy(call)
    if leaf is None:
        call['target'] = bad_value
    else:
        call['params'][leaf] = bad_value
    patch = {'note': 'Correct only the invalid leaf', 'callsUpsert': [correction],
             'realizationReplacement': source['realization']}
    repaired, dossier = _offline_gameplay_repair(monkeypatch, broken, patch, mode)
    assert repaired['runtimeProgram'] == source['runtimeProgram']
    examples = dossier['requiredJsonShape']['callsUpsert']
    offered_forms = {frozenset(row) for row in examples}
    local = author_item_repair_response_schema(capability_names=runtime_repair_schema_capabilities(dossier['repairScope']))
    assert offered_forms == {frozenset(row['properties']) for row in local['properties']['callsUpsert']['items']['oneOf']}


@pytest.mark.parametrize('mode', ['off', 'json_object', 'json_schema'])
def test_balance_distinguishes_ammunition_contribution_from_autonomous_attack(monkeypatch, mode):
    from copy import deepcopy
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    source = {'name': 'Unnamed source', 'damage': 50, 'useTime': 10, 'ammo': 71,
              'consumable': True, 'value': 500,
              'ammoRaw': {'mode': 'this_item_is_ammo', 'ammoId': 71}}
    before = deepcopy(source)
    _, user, _ = author.build_initial_author_request(source, {}, 'ammo-economy', model_name='offline')
    payload = json.loads(user)
    assert payload['parents']['A']['packet'] == raw_parent_card_for_llm(source)
    assert payload['balanceCorridor']['parentDamage'] == [50, 0]
    assert payload['balanceCorridor']['parentUseTimeTicks'] == [10, None]
    assert source == before


@pytest.mark.parametrize('mode', ['off', 'json_object', 'json_schema'])
def test_ingredient_grounded_balance_prices_total_output_and_reusable_benefit(monkeypatch, mode):
    from copy import deepcopy
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    parents = ({'name': 'Source A', 'damage': 0, 'value': 100, 'rare': 0, 'consumable': True},
               {'name': 'Source B', 'damage': 0, 'value': 1, 'rare': 0, 'consumable': True})
    before = deepcopy(parents)
    request, user, _ = author.build_initial_author_request(*parents, 'ingredient-balance', model_name='offline')
    packet = json.loads(user)
    # Guidance is invariant: source fields are read, never used to select a
    # mechanics preset, invent a tier or rewrite the parents or authored params.
    renamed = tuple({**parent, 'name': 'Unrelated identity'} for parent in parents)
    other, _, _ = author.build_initial_author_request(*renamed, 'renamed', model_name='offline')
    assert request['messages'][:2] == other['messages'][:2]
    assert packet['parents'] == {label: {'packet': raw_parent_card_for_llm(parent)}
                                 for label, parent in zip(('A', 'B'), parents)}
    assert parents == before


def test_future_economy_guidance_does_not_thaw_valid_existing_effects_in_repair():
    from copy import deepcopy
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    source = build_capability_witness('apply_generated_buff_on_use')
    original = deepcopy(source)
    stats = next(c for c in source['runtimeProgram']['calls'] if c['fn'] == 'configure_item_stats')
    stats['params']['damage'] = True
    dossier = author.build_gameplay_repair_dossier(source, {}, {}, failure_report=validate_runtime_program(source))
    scope = dossier['repairScope']
    assert scope['fieldPermissions']['calls'] == [{'id': stats['id'], 'paths': ['params.damage']}]
    repaired_stats = deepcopy(stats)
    repaired_stats['params']['damage'] = next(c for c in original['runtimeProgram']['calls'] if c['fn'] == 'configure_item_stats')['params']['damage']
    effects = deepcopy(next(c for c in source['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use'))
    effects['params']['durationSeconds'] = (1) / 60
    filtered, audit = filter_repair_patch_scope(source, {'callsUpsert': [repaired_stats, effects], 'note': 'Only actual invalid leaf'}, scope)
    assert audit['ok'] and audit['ignoredChanges']
    result = apply_repair_patch(source, filtered)
    assert result == original and validate_runtime_program(result)['ok']
