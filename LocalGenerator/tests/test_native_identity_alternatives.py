"""Actual discarded integration paths remain visible, without importing native AI."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.native_attack_behavior_view import (
    _identity_alternatives, known_identity_alternatives, project_attack_behavior,
)


def capture():
    return json.loads((Path(__file__).parent / 'fixtures/native_position_integration_capture.json').read_text())


def test_actual_native_excluded_paths_have_selfcontained_conditions_and_scope():
    original = capture()
    for entry in original['captures'].values():
        reference = {'source': 'read_only_native_attack_source', 'version': 1, **entry}
        before = copy.deepcopy(reference)
        projected = project_attack_behavior(reference)['positionIntegration']
        alternatives = projected['identityAlternatives']
        assert known_identity_alternatives(alternatives)
        assert 'not imported Author options' in alternatives['meaning']
        assert 'enclosing caller identity preservation is not proved' in projected['identitySelection']['scope']
        assert len(projected['predicates']) == 11 and len(projected['observations']) == 6
        cases = alternatives['cases']
        assert len(cases) == 8
        proved = [case for case in cases if case['effect'] == 'returns_without_method_state_changes']
        unresolved = [case for case in cases if case['effect'] == 'discarded_path_effect_unresolved']
        assert len(proved) == 5 and len(unresolved) == 3
        assert [case['whenAll'][0]['values'] for case in proved] == [
            [4, 38, 84, 148], [7], [440, 449, 606], [93], [540, 756, 818, 856, 961, 933],
        ]
        assert [case['whenAll'][1:] for case in proved] == [[],
            [{'field': 'Projectile.ai[0]', 'test': 'equals', 'value': 2}],
            [{'field': 'Projectile.ai[1]', 'test': 'equals', 'value': 1}],
            [{'field': 'Projectile.ai[0]', 'test': 'orderedLessThan', 'value': 0}], []]
        assert [case['whenAll'][-1]['test'] for case in unresolved] == ['notEquals', 'notEquals', 'notOrderedLessThan']
        assert sum(len(case['sourcePaths']) for case in cases) == 20
        assert reference == before


@pytest.mark.parametrize('mutation', ['effect_dict', 'effect_list', 'future', 'unknown_op', 'bad_successor', 'wrong_receiver', 'unknown_field', 'bool_version'])
def test_unrecognized_disclosure_is_literal_not_dropped_or_interpreted(mutation):
    source = capture()['captures']['itemA']['positionIntegration']['identitySelected']['identityAlternatives']
    condition = source['cases'][0]['allConditions'][0]
    if mutation == 'effect_dict': source['cases'][0]['effect'] = {'new': 'effect'}
    elif mutation == 'effect_list': source['cases'][0]['effect'] = ['new']
    elif mutation == 'future': source['future'] = 1
    elif mutation == 'unknown_op': condition['op'] = 'future'
    elif mutation == 'bad_successor': condition['chosenSuccessor'] = -123
    elif mutation == 'wrong_receiver': condition['inputs'][0] = 'ldfld(Projectile.type,other)'
    elif mutation == 'unknown_field': condition['inputs'][0] = 'ldfld(Projectile.damage,this)'
    else: source['version'] = True
    before = copy.deepcopy(source)
    result = _identity_alternatives(source)
    assert result == before and source == before
    assert not known_identity_alternatives(result)


@pytest.mark.parametrize('mutation', ['effect_dict', 'effect_list', 'test_dict', 'test_list', 'future', 'paths', 'bool_value'])
def test_projected_disclosure_unknown_schema_does_not_authorize_stage_omission(mutation):
    source = capture()['captures']['itemA']['positionIntegration']['identitySelected']['identityAlternatives']
    result = _identity_alternatives(source)
    if mutation.startswith('effect_'): result['cases'][0]['effect'] = {} if mutation.endswith('dict') else []
    elif mutation.startswith('test_'): result['cases'][0]['whenAll'][0]['test'] = {} if mutation.endswith('dict') else []
    elif mutation == 'future': result['cases'][0]['future'] = 1
    elif mutation == 'paths': result['cases'][0]['sourcePaths'] = [[]]
    else: result['cases'][0]['whenAll'][0]['values'][0] = True
    assert not known_identity_alternatives(result)


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_actual_author_request_keeps_other_identity_choices_visible(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    parents = [{'directProjectileRaw': {'type': entry['identityPredicates']['Projectile.type'],
               'attackReference': {'source': 'read_only_native_attack_source', 'version': 1, **entry}}}
               for entry in capture()['captures'].values()]
    request, _, _ = build_initial_author_request(*parents, 'alternative-discovery', model_name='offline')
    packet = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    for label in ('A', 'B'):
        integration = packet['parents'][label]['packet']['raw']['directProjectile']['attackReference']['positionIntegration']
        assert known_identity_alternatives(integration['identityAlternatives'])
        assert len(integration['identityAlternatives']['cases']) == 8
        assert 'not imported Author options' in integration['identityAlternatives']['meaning']
        assert 'enclosing caller identity preservation is not proved' in integration['identitySelection']['scope']
