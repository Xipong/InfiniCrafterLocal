from prompt_packet_helpers import request_dossier, dossier_text
"""Model-visible ownership and actual field paths, without runtime design policy."""
import json
import pytest
from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_author_packet_names_real_fields_without_harness_instructions(monkeypatch, mode):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', mode)
    req, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'clarity', model_name='test-model')
    assert dossier_text(req) == user
    payload = json.loads(user)
    priority = ' '.join(payload['priorityHeader'])
    assert 'runtimeCapabilityContract.catalog.capabilities' in priority
    assert 'capabilityCatalog' not in priority
    assert 'There is no subsequent model or tool pass' not in priority
    assert 'Visual/VFX' not in priority
    assert 'runtimeProgram alone defines executable gameplay' in req['messages'][0]['content']
    cards = {row['fn']: row for row in payload['runtimeCapabilityContract']['catalog']['capabilities']}
    # Cadence belongs to stats, not use: the packet must not imply an absent param.
    use_meaning = cards['configure_item_use']['constructionMeaning']
    assert 'configure_item_stats.useTimeTicks' in use_meaning
    assert 'configure_item_stats.useAnimationTicks' in use_meaning
    assert 'useTimeTicks' not in cards['configure_item_use']['params']
    assert {'useTimeTicks', 'useAnimationTicks'} <= cards['configure_item_stats']['params'].keys()


def test_author_declares_only_static_app_contract_as_instruction_prefix(monkeypatch):
    from infini_local.core.llm_prompt_cache import instruction_segment_index
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    req, user, _ = author.build_initial_author_request({'name': 'user-owned-parent'}, {}, {}, {}, 'recipe', model_name='test-model')
    assert req['_infini_prompt_cache'] == {'instructionMessageIndex': 1}
    assert instruction_segment_index(req) == 1
    assert [row['role'] for row in req['messages']] == ['system', 'developer', 'user']
    static, dynamic = [row['content'] for row in req['messages'][1:]]
    assert set(json.loads(dynamic)) == {'recipeKey', 'parents', 'balanceCorridor', 'sourceWireUnits'}
    assert 'user-owned-parent' not in static
    assert {**json.loads(static), **json.loads(dynamic)} == json.loads(user)


def test_area_damage_card_scopes_direct_target_exclusion_in_author_and_repair(monkeypatch):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'area-clarity', model_name='test-model')
    catalog = json.loads(user)['runtimeCapabilityContract']['catalog']
    card = next(row for row in catalog['capabilities'] if row['fn'] == 'damage_area_on_event')
    # The event carries the exclusion target, not the projectile's hit history.
    for phrase in ('only for on_hit/on_crit', 'on_kill', 'ignore direct-target exclusion', 'previously hit NPC'):
        assert phrase in card['does']
    doc = build_capability_witness('damage_area_on_event')
    call = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'damage_area_on_event')
    del call['params']['radiusTiles']
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
    assert 'explicit card default' in guide['paramNotation']


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


def test_immunity_is_one_required_typed_choice(monkeypatch):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'cooldown', model_name='test-model')
    cat = json.loads(user)['runtimeCapabilityContract']['catalog']
    params = next(c for c in cat['capabilities'] if c['fn'] == 'set_projectile_collision')['params']
    param = params['immunity']
    assert not param.get('optional', False)
    shape = param['shape']['oneOf']
    assert [branch['enum'] for branch in shape if branch.get('type') == 'string'] == [['owner_shared'], ['once_per_npc']]
    cooldown = next(branch['properties']['localCooldown'] for branch in shape if branch.get('type') == 'object')
    assert cooldown['minimum'] == 0 and cooldown['maximum'] == 600
    assert 'unscaled' in cooldown['description']
    assert 'localNpcHitCooldownEngineUnits' not in params and 'npcImmunityMode' not in params


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('fn,leaf,bad_value', [
    ('configure_item_stats', 'damage', True),
    ('set_projectile_lifetime', 'lifetimeTicks', 0),
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
    rules = ' '.join(dossier['rules'])
    assert 'preserve unchanged required fields and accepted optional values or absences' in rules
    assert 'not defaults or edit permissions' in rules
    assert 'omission means no change' in rules


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_binding_examples_keep_optional_rules_and_fixed_branch_omissions_in_actual_packet(monkeypatch, mode):
    from infini_local.core.runtime_authoring.capability_registry import STACK_COST_RULE
    from infini_local.core.runtime_authoring.program_schema import binding_schema

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', mode)
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'binding-guidance', model_name='test-model')
    catalog = json.loads(user)['runtimeCapabilityContract']['catalog']
    rule = catalog['fieldGuide']['stackCost']
    assert rule == STACK_COST_RULE  # The presentation must not replace this and lose optional chance semantics.
    shapes = catalog['fieldGuide']['rowShapes']
    assert 'Fixed binding literals may be explicit or omitted' in shapes
    assert 'place_item stackCost=1 and contactDamage=false' in shapes
    assert 'hold/equipped stackCost=0 and contactDamage=false' in shapes
    assert 'only with stackCost=1 outside placement' in rule
    assert 'omission retains the existing 100 percent debit' in rule
    assert 'effectGroupId is optional only for apply_item_effects' in catalog['fieldGuide']['rowShapes']
    for variant in binding_schema()['oneOf']:
        props = variant['properties']
        if 'stackConsumeChancePercent' in props:
            chance = props['stackConsumeChancePercent']
            assert 'stackConsumeChancePercent' not in variant['required']
            assert f"{chance['type']} {chance['minimum']}..{chance['maximum']}" in rule
    placement = next(row for row in catalog['bindingActions'] if row['action'] == 'place_item')
    assert 'Only accepted placement spends the stack' in placement['constructionMeaning']


def test_condition_card_describes_its_existing_union_and_placement_guide_matches_public_ids(monkeypatch):
    from dataclasses import replace
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'typed-guidance', model_name='test-model')
    catalog = json.loads(user)['runtimeCapabilityContract']['catalog']
    cards = {row['fn']: row for row in catalog['capabilities']}
    condition = cards['require_use_condition']['params']['condition']
    spec = CAPABILITY_REGISTRY['require_use_condition'].params['condition']
    assert condition['type'] == 'union'
    assert condition['shape'] == spec.schema() == replace(spec, kind='string').schema()
    assert {branch['type'] for branch in condition['shape']['oneOf']} == {'string', 'object'}
    doc = build_capability_witness('require_use_condition')
    next(row for row in doc['runtimeProgram']['calls'] if row['fn'] == 'require_use_condition')['params']['condition'] = 3
    dossier = author.build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=validate_runtime_program(doc))
    repair_card = next(row for row in dossier['existingBrokenCapabilityCards'] if row['fn'] == 'require_use_condition')
    assert repair_card['params']['condition']['type'] == 'union'
    assert repair_card['params']['condition']['shape'] == condition['shape']
    notation = catalog['fieldGuide']['paramNotation']
    assert 'tileId/wallId=-1 disables placement' not in notation
    for fn, key in [('configure_tile_placement', 'tileId'), ('configure_wall_placement', 'wallId')]:
        assert cards[fn]['params'][key]['min'] == 0
        assert f'{fn} selects {key}>=0' in notation


@pytest.mark.parametrize('fn', ['move_phase', 'move_expanding_wave'])
def test_movement_execution_meaning_reaches_initial_and_repair_cards(monkeypatch, fn):
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'movement-guidance', model_name='test-model')
    cards = {row['fn']: row for row in json.loads(user)['runtimeCapabilityContract']['catalog']['capabilities']}
    assert cards[fn]['does'] == CAPABILITY_REGISTRY[fn].prompt_card()['does']
    doc = build_capability_witness(fn)
    call = next(row for row in doc['runtimeProgram']['calls'] if row['fn'] == fn)
    del call['params'][next(name for name, spec in CAPABILITY_REGISTRY[fn].params.items() if spec.required)]
    dossier = author.build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=validate_runtime_program(doc))
    repair_card = next(row for row in dossier['existingBrokenCapabilityCards'] if row['fn'] == fn)
    assert repair_card['does'] == cards[fn]['does']


def test_conditional_neutral_guidance_preserves_optional_contract(monkeypatch):
    from infini_local.core.runtime_authoring.capability_registry import visible_capabilities

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'neutral-guidance', model_name='test-model')
    catalog = json.loads(user)['runtimeCapabilityContract']['catalog']
    cards = {row['fn']: row for row in catalog['capabilities']}
    conditional = [(cap, name, spec) for cap in visible_capabilities() for name, spec in cap.params.items()
                   if spec.omission_condition is not None]
    assert conditional
    for cap, name, spec in conditional:
        assert not spec.required and cards[cap.name]['params'][name]['optional'] is True
        assert cards[cap.name]['params'][name]['omissionAllowedOnlyWhen'] == spec.omission_condition.card()


@pytest.mark.parametrize('mode', ['off', 'json_object', 'json_schema'])
def test_future_author_accounts_for_refreshable_utility_economy_without_item_router(monkeypatch, mode):
    from copy import deepcopy

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', mode)
    parent = {'name': 'Arbitrary object', 'damage': 4, 'useTime': 18, 'maxStack': 1}
    before = deepcopy(parent)
    first, user, _ = author.build_initial_author_request(parent, {}, {}, {}, 'future-economy', model_name='test-model')
    second, _, _ = author.build_initial_author_request({**parent, 'name': 'Different identity'}, {}, {}, {}, 'other-economy', model_name='test-model')
    payload = json.loads(user)
    rule = payload['requiredJsonShape']['concept']['coreMechanic']
    for meaning in ('effective uptime', 'free repeated refresh', 'duration is not a cooldown',
                    'recurring cost', 'supported mechanics', 'never invent'):
        assert meaning in rule
    assert '3 minutes' not in rule and '10800' not in rule
    # App guidance is static, parent facts stay complete and no host design is inserted.
    assert first['messages'][:2] == second['messages'][:2]
    assert parent == before
    assert 'cooldownTicks' not in payload['requiredJsonShape']['runtimeProgram']['bindings'][0]
    assert payload['runtimeCapabilityContract']['catalog']['capabilities']


def test_generated_utility_card_explains_real_refresh_stacking_and_spelunker_scope(monkeypatch):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    _, user, _ = author.build_initial_author_request({}, {}, {}, {}, 'utility-refresh', model_name='test-model')
    cards = {row['fn']: row for row in json.loads(user)['runtimeCapabilityContract']['catalog']['capabilities']}
    card = cards['apply_generated_buff_on_use']
    for meaning in ('identical effect', 'maximum remaining duration', 'distinct effects', 'indefinite uptime'):
        assert meaning in card['does']
    duration = card['params']['durationTicks']['meaning']
    assert 'one application' in duration and 'not a reuse cooldown' in duration
    sense = card['params']['oreSenseEnabled']['meaning']
    assert 'Spelunker' in sense and 'chests' in sense and 'life crystals' in sense and 'not a radius' in sense
    source = build_capability_witness('apply_generated_buff_on_use')
    buff = next(c for c in source['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use')
    del buff['params']['durationTicks']
    dossier = author.build_gameplay_repair_dossier(source, {}, {}, {}, {}, failure_report=validate_runtime_program(source))
    repair_card = next(c for c in dossier['existingBrokenCapabilityCards'] if c['fn'] == 'apply_generated_buff_on_use')
    assert repair_card['does'] == card['does']
    for leaf in ('durationTicks', 'oreSenseEnabled'):
        assert repair_card['params'][leaf]['meaning'] == card['params'][leaf]['meaning']


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
    dossier = author.build_gameplay_repair_dossier(source, {}, {}, {}, {}, failure_report=validate_runtime_program(source))
    scope = dossier['repairScope']
    assert scope['fieldPermissions']['calls'] == [{'id': stats['id'], 'paths': ['params.damage']}]
    repaired_stats = deepcopy(stats)
    repaired_stats['params']['damage'] = next(c for c in original['runtimeProgram']['calls'] if c['fn'] == 'configure_item_stats')['params']['damage']
    effects = deepcopy(next(c for c in source['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use'))
    effects['params']['durationTicks'] = 1
    filtered, audit = filter_repair_patch_scope(source, {'callsUpsert': [repaired_stats, effects], 'note': 'Only actual invalid leaf'}, scope)
    assert audit['ok'] and audit['ignoredChanges']
    result = apply_repair_patch(source, filtered)
    assert result == original and validate_runtime_program(result)['ok']
