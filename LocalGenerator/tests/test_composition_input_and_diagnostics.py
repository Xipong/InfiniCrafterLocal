from collections import Counter
from copy import deepcopy
import json

import pytest

from prompt_packet_helpers import request_dossier
from repair_test_helpers import offline_builder, provider_roundtrip, repair_with_response
from test_source_unit_guidance import _serialized_chat_request
from infini_local.pipelines import llm_authoring_pipeline as author

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def test_inherited_damage_warning_does_not_change_or_reject_harmless_child():
    doc = build_capability_witness('target_and_fire')
    call = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'target_and_fire')
    call['params']['damageBasis'] = 'live_parent'
    child = call['params']['shotEntity']
    doc['runtimeProgram']['calls'] = [c for c in doc['runtimeProgram']['calls'] if not (c.get('target') == child and c['fn'] == 'set_projectile_damage')]
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report['ok'], report
    assert any(w['code'] == 'inherited_damage_disabled' for w in report['warnings'])
    assert doc == before
    doc['runtimeProgram']['calls'].append({'id': 'enable_child_damage', 'target': child, 'fn': 'set_projectile_damage',
        'params': {'damage': 0, 'damageClass': 'generic', 'knockback': 0, 'ownerHitCheck': False}})
    assert not any(w['code'] == 'inherited_damage_disabled' for w in validate_runtime_program(doc)['warnings'])


@pytest.mark.parametrize('mode', ['json_schema', 'json_object'])
def test_author_packet_exposes_input_and_three_buff_activation_alternatives(monkeypatch, mode):
    import json
    from infini_local.core import llm_config
    from infini_local.pipelines import llm_authoring_pipeline as author
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    _, user, _ = author.build_initial_author_request({}, {}, 'composition', model_name='offline')
    cards = json.loads(user)['runtimeCapabilityContract']['catalog']['capabilities']
    buff = next(c for c in cards if c['fn'] == 'apply_generated_buff_on_use')
    text = json.dumps(buff)
    assert 'refresh_generated_effect_group_while_held' in text and 'apply_generated_buff_on_event' in text
    event = next(c for c in cards if c['fn'] == 'spawn_entity_on_event')
    assert 'useInput' in json.dumps(event) and 'both' in json.dumps(event)


@pytest.mark.parametrize('mode', ['json_schema', 'json_object'])
def test_native_status_interoperability_and_frozen_repair_survive_registry_retirement(monkeypatch, mode):
    """Synthetic authored response, not a live-model quality claim or saved-item replay."""
    offline_builder(monkeypatch, mode, lambda *args, **kwargs: pytest.fail('unexpected model call'))
    parents = ({'name': 'Observed native contact status',
                'nativeContactHitStatusReference': {'effects': [{'buffId': 20, 'durationTicks': 210}]}},
               {'name': 'Observed second native status',
                'nativeContactHitStatusReference': {'effects': [{'buffId': 69, 'durationTicks': 90}]}})
    before = deepcopy(parents)
    request, _, _ = author.build_initial_author_request(*parents, 'native-status-interop', model_name='offline')
    sent = _serialized_chat_request(monkeypatch, request)
    packet = request_dossier(sent, declaration=request)
    cards = packet['runtimeCapabilityContract']['catalog']['capabilities']
    assert 'statusIdentityChoices' not in packet['runtimeCapabilityContract']
    for fn in ('apply_status_on_event', 'apply_vanilla_buff_on_use'):
        meaning = next(row for row in cards if row['fn'] == fn)['params']['buffId']['meaning']
        assert 'statusIdentityChoices' not in meaning
        assert 'generated' in meaning.lower()

    item = build_capability_witness('apply_status_on_event')
    item.pop('concept', None)
    item.pop('realization', None)
    status = next(c for c in item['runtimeProgram']['calls'] if c['fn'] == 'apply_status_on_event')
    status['params'].update(buffId=20, durationSeconds=3.5)
    item['runtimeProgram']['calls'].append({
        'id': 'explicit_defense_pressure', 'fn': 'apply_status_on_event', 'target': status['target'],
        'params': {'when': 'on_crit', 'buffId': 69, 'durationSeconds': 1.5},
    })
    requests = []

    def respond(author_request, **kwargs):
        from jsonschema import Draft202012Validator
        from infini_local.pipelines.author_item_contract import author_item_response_schema
        from test_codex_subscription_contract import _encode_nullable_fixture

        requests.append(deepcopy(author_request))
        payload = _encode_nullable_fixture(item, author_item_response_schema()) if mode == 'json_schema' else item
        if mode == 'json_schema':
            Draft202012Validator(author_request['response_format']['json_schema']['schema']).validate(payload)
        return {'choices': [{'message': {'content': json.dumps(payload)}}],
                '_debug': {'responseFormatType': mode}}

    offline_builder(monkeypatch, mode, respond)
    restored = author.try_llm_plan(*parents, 'explicit-status')
    assert len(requests) == 1 and restored is not None
    assert restored['runtimeProgram'] == item['runtimeProgram']
    assert 'statusIdentityChoices' not in request_dossier(
        _serialized_chat_request(monkeypatch, requests[0]), declaration=requests[0])['runtimeCapabilityContract']
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)['ok']
    effects = Counter((entity['id'], event['event'], event['buffId'], event['durationTicks'])
                      for entity in wire['runtimeProgram']['entities'] for event in entity['events'])
    assert effects == Counter([(status['target'], 'on_hit', 20, 210),
                               (status['target'], 'on_crit', 69, 90)])

    broken = deepcopy(item)
    broken_status = next(c for c in broken['runtimeProgram']['calls'] if c['id'] == status['id'])
    broken_status['params']['durationSeconds'] = 0
    assert not validate_runtime_program(broken)['ok']
    with pytest.raises(ValueError):
        compile_runtime_program(broken)
    # A useful correction plus a hostile, schema-valid sibling status edit:
    # retired ID vocabulary must not alter accepted native interoperability.
    candidate = deepcopy(status)
    candidate['params']['buffId'] = 69
    repaired, repair_request = repair_with_response(monkeypatch, broken, {
        'note': 'Restore only the invalid duration', 'callsUpsert': [candidate],
    }, mode, parents=parents)
    repair_sent = _serialized_chat_request(monkeypatch, repair_request)
    dossier = request_dossier(repair_sent, declaration=repair_request)
    assert 'runtimeCapabilityContract' not in dossier
    assert 'Compose buffs and debuffs' in dossier['runtimeExecutionTruth'].get('statusEffects', '')
    assert any('Compose buffs and debuffs' in row for row in packet['priorityHeader'])
    assert dossier['repairScope']['fieldPermissions']['calls'] == [
        {'id': status['id'], 'paths': ['params.durationSeconds']}]
    repair_card = next(row for row in dossier['existingBrokenCapabilityCards']
                       if row['fn'] == 'apply_status_on_event')
    assert repair_card['params']['buffId']['meaning'] == next(
        row for row in cards if row['fn'] == 'apply_status_on_event')['params']['buffId']['meaning']
    assert repaired['debug']['gameplayRepairFilterAudit']['ignoredChanges']
    repaired.pop('debug')
    assert repaired == item
    assert validate_runtime_wire(compile_runtime_program(repaired))['ok']
    assert parents == before


@pytest.mark.parametrize('mode', ['json_schema', 'json_object'])
def test_author_prioritizes_playable_composition_without_turning_advisory_into_a_gate(monkeypatch, mode):
    offline_builder(monkeypatch, mode, lambda *args, **kwargs: pytest.fail('unexpected model call'))
    request, _, _ = author.build_initial_author_request({}, {}, 'purposeful-composition', model_name='offline')
    packet = request_dossier(_serialized_chat_request(monkeypatch, request))
    guidance = ' '.join(packet['priorityHeader'])
    assert 'isolated target' in guidance
    assert 'secondary' in guidance and 'reachable' in guidance
    assert 'risk' in guidance and 'reward' in guidance
    assert 'player decisions' in guidance and 'call count' in guidance
    assert 'always-upgrade' in guidance and 'mandatory twist' in guidance
    assert packet['requiredJsonShape']['optionalAdvisory'] == ['concept', 'realization']
    # No concept/report is needed to execute an intentionally simple composition.
    item = build_capability_witness('move_straight')
    item.pop('concept', None)
    item.pop('realization', None)
    restored = provider_roundtrip(item, request['response_format'])
    assert restored == item
    assert validate_runtime_wire(compile_runtime_program(restored))['ok']


@pytest.mark.parametrize('mode', ['json_schema', 'json_object'])
def test_ammo_balance_guidance_separates_damage_from_projectile_conversion(monkeypatch, mode):
    offline_builder(monkeypatch, mode, lambda *args, **kwargs: pytest.fail('unexpected model call'))
    source = {'name': 'Observed ammo context', 'ammoRaw': {
        'mode': 'weapon_uses_ammo', 'playerInventoryAmmoRaw': [{'type': 40, 'damage': 5, 'stack': 9}],
        'projectileSemanticsReference': {'ammoProjectileRelation': 'replaced'},
    }}
    before = deepcopy(source)
    request, _, _ = author.build_initial_author_request(source, {}, 'ammo-balance-guidance', model_name='offline')
    packet = request_dossier(_serialized_chat_request(monkeypatch, request), declaration=request)
    meaning = packet['requiredJsonShape']['concept']['coreMechanic']
    assert 'Projectile replacement does not remove ammunition damage' in meaning
    assert 'weapon-ammo configurations separately' in meaning
    assert 'fallback examples do not prove possession or progression' in meaning
    assert 'strongest' in meaning and 'average' in meaning
    ammo = packet['parents']['A']['packet']['raw']['ammo']
    assert ammo['playerInventoryAmmoRaw'][0]['damage'] == 5
    assert 'stack' not in ammo['playerInventoryAmmoRaw'][0]
    assert source == before


def test_target_and_fire_composes_with_explicit_motion_and_speed_modifier():
    doc = build_capability_witness('target_and_fire')
    doc['runtimeProgram']['entities'][1]['kind'] = 'free_projectile'
    doc['runtimeProgram']['calls'].append({'id': 'firing_motion', 'fn': 'move_straight', 'target': 'witness_entity'})
    modifier = deepcopy(next(c for c in build_capability_witness('scale_projectile_velocity')['runtimeProgram']['calls']
                             if c['fn'] == 'scale_projectile_velocity'))
    modifier['id'] = 'firing_speed'
    doc['runtimeProgram']['calls'].append(modifier)
    assert validate_runtime_program(doc)['ok'], validate_runtime_program(doc)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    wire.pop('runtimeContract')
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    entity = next(e for e in wire['runtimeProgram']['entities'] if e['id'] == 'witness_entity')
    assert entity['movement']['name'] == 'move_straight'
    assert entity['controller']['name'] == 'target_and_fire'
    assert entity['velocityScale'][0]['multiplierPerUpdate'] == modifier['params']['multiplierPerUpdate']


def test_mobile_firing_requires_explicit_motion_without_inventing_stationary_behavior():
    doc = build_capability_witness('target_and_fire')
    doc['runtimeProgram']['entities'][1]['kind'] = 'free_projectile'
    assert not validate_runtime_program(doc)['ok']
    doc['runtimeProgram']['calls'].append({'id': 'moving_fire', 'fn': 'move_straight', 'target': 'witness_entity'})
    wire = compile_runtime_program(doc)
    wire.pop('runtimeContract')
    entity = next(e for e in wire['runtimeProgram']['entities'] if e['id'] == 'witness_entity')
    assert validate_runtime_wire(wire)['ok']
    del entity['movement']
    assert not validate_runtime_wire(wire)['ok']


def test_independent_beam_geometry_does_not_warn_away_or_rewrite_authored_motion():
    doc = build_capability_witness('set_projectile_beam_geometry')
    motion = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'move_straight')
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report['ok'], report
    assert not any(w['code'] == 'motion_owned_by_beam' for w in report['warnings'])
    wire = compile_runtime_program(doc)
    assert doc == before
    entity = next(e for e in wire['runtimeProgram']['entities'] if e['id'] == motion['target'])
    assert entity['movement']['name'] == 'move_straight'
    assert 'beamGeometry' in entity and 'aim' in entity
    assert 'controller' not in entity and 'ownerControl' not in entity
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    wire.pop('runtimeContract')
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
