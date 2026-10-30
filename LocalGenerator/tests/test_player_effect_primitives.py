"""Shared player mechanics through equipment, timed buffs and hit actions."""
from copy import deepcopy
import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts

CASES = [
    ('healCooldownOnHit', .5, 'healingPotionCooldownOnHitReductionTicks', 30),
    ('fishingPowerPoints', 17, 'fishingPowerPoints', 17),
    ('preventLineBreak', True, 'preventLineBreak', True),
    ('allowLavaFishing', True, 'allowLavaFishing', True),
    ('revealHookedCatch', True, 'revealHookedCatch', True),
    ('extraCrateChancePercent', 12, 'extraCrateChancePercent', 12),
    ('itemPickupRangeBlocks', 3, 'itemPickupRangePx', 48),
    ('heartPickupRangeBlocks', 4, 'heartPickupRangePx', 64),
    ('manaPickupRangeBlocks', 5, 'manaPickupRangePx', 80),
    ('coinPickupRangeBlocks', 6, 'coinPickupRangePx', 96),
    ('highlightDanger', True, 'highlightDanger', True),
    ('highlightCreatures', True, 'highlightCreatures', True),
    ('nightVision', True, 'nightVision', True),
    ('healCooldownReductionPercent', 17, 'healingPotionCooldownReductionPercent', 17),
    ('healCooldownReduction', .5, 'healingPotionCooldownReductionTicks', 30),
    ('manaPotionBelowPercent', 30, 'autoManaPotionBelowPercent', 30),
    ('hurtImmunityBonus', .5, 'hurtInvulnerabilityBonusTicks', 30),
]

def source(fn, effect):
    doc = build_capability_witness(fn)
    call = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == fn)
    if fn == 'apply_generated_buff_on_use':
        call['params'] = {'durationSeconds': 10, 'lightStrength': 0, 'lightColor': 'white'}
    elif fn == 'configure_accessory':
        call['params'] = {}
    call['params']['playerEffect'] = effect
    return doc, call

@pytest.mark.parametrize('fn', ['configure_accessory','configure_armor','apply_generated_buff_on_use'])
@pytest.mark.parametrize('name,value,wire_name,wire_value', CASES)
def test_shared_mechanic_exact_delivery_and_presence(fn, name, value, wire_name, wire_value):
    doc, _ = source(fn, {'condition': 'stationary', name: value})
    report = validate_runtime_program(doc)
    assert report['ok'], report
    wire = compile_runtime_program(doc)
    report = validate_runtime_wire(wire)
    assert report['ok'], report
    target = wire['gameplay']['generatedBuff'] if fn == 'apply_generated_buff_on_use' else wire['armor' if fn == 'configure_armor' else 'accessory']
    assert target['playerEffect'] == {'condition':'stationary', wire_name:wire_value}
    rows=wire['runtimeContract']['finalWireReceipts']
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)['ok']
    bare=deepcopy(wire); bare.pop('runtimeContract')
    assert validate_runtime_wire(bare)['ok']
    target['playerEffect'][wire_name] = None
    assert not validate_runtime_wire(wire)['ok']

@pytest.mark.parametrize('event', ['on_hit', 'on_crit'])
def test_half_second_cooldown_reduction_is_an_explicit_hit_action(event):
    doc=build_capability_witness('heal_owner_on_event')
    call=next(c for c in doc['runtimeProgram']['calls'] if c['fn']=='heal_owner_on_event')
    call.update(fn='reduce_heal_cooldown_on_event', params={'when':event,'seconds':.5})
    assert validate_runtime_program(doc)['ok']
    wire=compile_runtime_program(doc)
    report=validate_runtime_wire(wire)
    assert report['ok'], report
    action=next(e for entity in wire['runtimeProgram']['entities'] for e in entity.get('events',[]) if e['id']==call['id'])
    assert action['actionCode']==12 and action['cooldownReductionTicks']==30

@pytest.mark.parametrize('field', ['fishingInfo','weatherInfo','moonInfo','enemyInfo','speedInfo','oreInfo','rareCreatureInfo','killCountInfo'])
def test_information_progression_is_not_exposed(field):
    doc, call=source('configure_accessory', {'itemPickupRangeBlocks':1})
    call['params'][field]=True
    assert not validate_runtime_program(doc)['ok']

@pytest.mark.parametrize('effect', [
    {'condition':'always'}, {'condition':'stationary'},
    {'condition':'stationary','fishingPowerPoints':0,'preventLineBreak':False},
])
def test_accessory_requires_a_real_leaf_effect_beyond_component_condition(effect):
    doc, _ = source('configure_accessory', effect)
    report = validate_runtime_program(doc)
    assert not report['ok']
    assert any(row['code']=='inert_component' for row in report['errors'])
    effect = {**effect, 'fishingPowerPoints':1}
    doc, _ = source('configure_accessory', effect)
    assert validate_runtime_wire(compile_runtime_program(doc))['ok']

@pytest.mark.parametrize('fn', ['configure_accessory', 'configure_armor', 'apply_generated_buff_on_use'])
def test_omitted_condition_has_exact_neutral_receipt_without_mutating_author(fn):
    doc, call = source(fn, {'heartPickupRangeBlocks': 3})
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    explicit = deepcopy(doc)
    next(c for c in explicit['runtimeProgram']['calls'] if c['id']==call['id'])['params']['playerEffect']['condition']='always'
    expected = compile_runtime_program(explicit)
    assert wire['runtimeProgram'] == expected['runtimeProgram']
    section = 'gameplay' if fn == 'apply_generated_buff_on_use' else 'armor' if fn=='configure_armor' else 'accessory'
    assert wire[section] == expected[section]
    rows=wire['runtimeContract']['finalWireReceipts']
    assert any(r.get('callId')==call['id'] and r.get('status')=='declared_neutral_omission'
               and r['finalPath'].endswith('.playerEffect.condition') and r['value']=='always' for r in rows)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)['ok']
    assert validate_runtime_wire(wire)['ok']
    assert doc == before

@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('fn', ['configure_accessory', 'configure_armor', 'apply_generated_buff_on_use'])
def test_actual_author_and_repair_packets_keep_numeric_mechanics_and_frozen_siblings(monkeypatch, mode, fn):
    from infini_local.pipelines import llm_authoring_pipeline as author
    from prompt_packet_helpers import request_dossier
    from test_source_unit_guidance import _offline, _serialized_chat_request
    from repair_test_helpers import provider_roundtrip, repair_with_response
    from infini_local.core import llm_config
    getattr(_offline, '__wrapped__')(monkeypatch)
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    doc, call = source(fn, {'condition':'stationary','healCooldownOnHit':.5,'heartPickupRangeBlocks':3})
    request, _, _ = author.build_initial_author_request({}, {}, 'player-effect-packet', model_name='offline')
    sent = _serialized_chat_request(monkeypatch, request)
    card = next(c for c in request_dossier(sent, declaration=request)['runtimeCapabilityContract']['catalog']['capabilities'] if c['fn']==fn)
    assert card['params']['playerEffect']['typeRef']=='player_effect'
    public = {k:doc[k] for k in ('name','category','runtimeProgram')}
    assert provider_roundtrip(public, sent['response_format']) == public
    expected = deepcopy(doc)
    call['params']['playerEffect']['healCooldownOnHit'] = None
    hostile = deepcopy(call)
    hostile['params']['playerEffect'].update(condition='always', healCooldownOnHit=.5, heartPickupRangeBlocks=40)
    repaired, repair_request = repair_with_response(monkeypatch, doc, {'note':'repair one numeric mechanic', 'callsUpsert':[hostile]}, mode)
    permissions=request_dossier(repair_request)['repairScope']['fieldPermissions']['calls']
    assert permissions==[{'id':call['id'],'paths':['params.playerEffect.healCooldownOnHit']}]
    actual=next(c for c in repaired['runtimeProgram']['calls'] if c['id']==call['id'])
    wanted=next(c for c in expected['runtimeProgram']['calls'] if c['id']==call['id'])
    assert actual['params']==wanted['params']
    assert repaired['debug']['gameplayRepairFilterAudit']['ignoredChanges']
    assert validate_runtime_wire(compile_runtime_program(repaired))['ok']
