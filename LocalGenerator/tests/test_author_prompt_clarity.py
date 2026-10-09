"""Model-visible ownership and actual field paths, without runtime design policy."""
import json
import pytest
from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_author_packet_names_real_fields_without_harness_instructions(monkeypatch, mode):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', mode)
    req, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'clarity', model_name='test-model')
    assert req['messages'][1]['content'] == user
    payload = json.loads(user)
    priority = ' '.join(payload['priorityHeader'])
    assert 'runtimeCapabilityContract.catalog.capabilities' in priority
    assert 'capabilityCatalog' not in priority
    assert 'There is no subsequent model or tool pass' not in priority
    assert 'Visual/VFX' not in priority
    assert 'runtimeProgram must explicitly implement the gameplay you describe' in priority
    cards = {row['fn']: row for row in payload['runtimeCapabilityContract']['catalog']['capabilities']}
    # Cadence belongs to stats, not use: the packet must not imply an absent param.
    use_meaning = cards['configure_item_use']['constructionMeaning']
    assert 'configure_item_stats.useTimeTicks' in use_meaning
    assert 'configure_item_stats.useAnimationTicks' in use_meaning
    assert 'useTimeTicks' not in cards['configure_item_use']['params']
    assert {'useTimeTicks', 'useAnimationTicks'} <= cards['configure_item_stats']['params'].keys()


def test_author_declares_only_static_app_contract_as_instruction_prefix(monkeypatch):
    from infini_local.core.llm_prompt_cache import static_instruction_prefix_parts
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    req, user, _ = author.build_initial_author_request({'name': 'user-owned-parent'}, {}, {}, {}, 'recipe', model_name='test-model')
    assert req['_infini_prompt_cache'].get('staticInstructionPrefix') is True
    parts = static_instruction_prefix_parts(req)
    assert parts is not None
    index, static, dynamic = parts
    assert index == 1
    assert set(json.loads(dynamic)) == {'recipeKey', 'parents', 'balanceCorridor'}
    assert 'user-owned-parent' not in static
    assert {**json.loads(static), **json.loads(dynamic)} == json.loads(user)


def test_area_damage_card_scopes_direct_target_exclusion_in_author_and_repair(monkeypatch):
    from infini_local.core.runtime_authoring import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'area-clarity', model_name='test-model')
    catalog = json.loads(user)['runtimeCapabilityContract']['catalog']
    card = next(row for row in catalog['capabilities'] if row['fn'] == 'damage_area_on_event')
    # The event carries the exclusion target, not the projectile's hit history.
    for phrase in ('on_hit/on_crit', 'on_kill', 'no direct target', 'previously hit NPC'):
        assert phrase in card['does']
    doc = build_capability_witness('damage_area_on_event')
    call = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'damage_area_on_event')
    del call['params']['radiusPx']
    report = validate_runtime_program(doc)
    assert not report['ok']
    dossier = author.build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=report)
    repair_card = next(c for c in dossier['existingBrokenCapabilityCards'] if c['fn'] == call['fn'])
    assert repair_card['does'] == card['does']


def test_author_guidance_is_local_and_report_coverage_is_authored_not_potential(monkeypatch):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'local-task', model_name='test-model')
    payload = json.loads(user)
    shape = payload['requiredJsonShape']
    assert 'Repair' not in json.dumps(shape)
    assert 'VFX' not in json.dumps(shape)
    # No undefined cross-dimensional host score masquerading as a usable budget.
    assert 'powerBudget' not in payload['balanceCorridor']
    rule = payload['diagnosticReport']['selfEvaluation']
    assert 'authored event actions' in rule
    assert 'without a subscribed action' in rule
    assert 'group' in rule
    guide = payload['runtimeCapabilityContract']['catalog']['fieldGuide']
    assert 'Neutral values are not defaults' not in guide['sourceValues']
    assert 'explicit card default' in guide['sourceValues']


def test_primary_and_projectile_lifecycle_card_explains_choice_not_invented_fields(monkeypatch):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'lifecycle', model_name='test-model')
    payload = json.loads(user)
    rule = payload['runtimeProgramInvariants']['primaryEntityOwnership']['primaryRule']
    assert 'configure_item_use.hideUseGraphic=true' in rule
    assert 'does not create' in rule
    assert 'requires explicitly authored lifecycle/held ownership' not in rule
    cat = payload['runtimeCapabilityContract']['catalog']
    free = next(c for c in cat['entityKinds'] if c['kind'] == 'free_projectile')['constructionMeaning']
    assert 'Each use spawns' not in free
    assert 'admitted' in free and 'hold' in free
    kill = next(c for c in cat['events'] if c['event'] == 'on_kill')['constructionMeaning']
    assert 'return-to-owner' in kill
    from infini_local.pipelines.llm_authoring_prompt import realization_execution_truth_for_llm
    assert 'return-to-owner' in realization_execution_truth_for_llm()['terminationEvents']
    bounce = next(c for c in cat['capabilities'] if c['fn'] == 'set_projectile_collision')['params']['bounceCount']['meaning']
    for fn in ('move_boomerang', 'move_returning_glaive', 'move_flail_tether'):
        assert fn in bounce


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_author_system_suffix_does_not_explain_other_model_tasks(monkeypatch, mode):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', mode)
    _, _, system = author.build_initial_author_request({}, {}, {}, {}, 'local-system', model_name='test-model')
    assert 'Repair' not in system
    assert 'realizationReplacement' not in system
    assert "this stage's" not in system
    if mode == 'json_schema':
        assert 'null' in system and 'unknown keys' in system


def test_required_inactive_cooldown_is_not_mistaken_for_optional(monkeypatch):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'cooldown', model_name='test-model')
    cat = json.loads(user)['runtimeCapabilityContract']['catalog']
    param = next(c for c in cat['capabilities'] if c['fn'] == 'set_projectile_collision')['params']['localNpcHitCooldownEngineUnits']
    assert not param.get('optional', False)
    assert 'Required in both immunity modes' in param['meaning']
    assert 'ignored in owner mode' in param['meaning']
