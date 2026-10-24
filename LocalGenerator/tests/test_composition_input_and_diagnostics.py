from copy import deepcopy

import pytest

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


def test_target_and_fire_composes_with_explicit_motion_and_speed_modifier():
    doc = build_capability_witness('target_and_fire')
    doc['runtimeProgram']['entities'][1]['kind'] = 'free_projectile'
    doc['runtimeProgram']['calls'].append({'id': 'firing_motion', 'fn': 'move_straight', 'target': 'witness_entity'})
    modifier = deepcopy(next(c for c in build_capability_witness('set_projectile_speed_modifier')['runtimeProgram']['calls']
                             if c['fn'] == 'set_projectile_speed_modifier'))
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
    assert entity['speedModifier']['speedMultiplierPerUpdate'] == .8


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
