"""Explicit native fishing transactions, units and strict delivery boundaries."""
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from infini_local.core import provider_schema
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import binding_schema
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture


def source(input_name='primary_use'):
    doc = build_capability_witness('item_use')
    doc['runtimeProgram']['bindings'] = [{'id':'fish', 'input':input_name,
        'action':{'kind':'native_fishing', 'fishing':{'power':30,'castSpeed':60}}}]
    return doc


@pytest.mark.parametrize('input_name', ['primary_use','alternate_use'])
@pytest.mark.parametrize('use_style', ['swing','shoot'])
def test_native_fishing_exact_projection_without_pose_or_input_inference(input_name, use_style):
    doc=source(input_name)
    next(c for c in doc['runtimeProgram']['calls'] if c['fn']=='item_use')['params']['useStyle']=use_style
    before=deepcopy(doc)
    assert validate_runtime_program(doc)['ok']
    wire=compile_runtime_program(doc)
    assert validate_runtime_wire(wire)['ok']
    action=wire['runtimeProgram']['bindings'][0]['usePolicy']
    assert action == {'action':{'kind':'native_fishing','targetId':'item','fishing':{'power':30,'castSpeedPxPerTick':16}},'stackCost':0,'contactDamage':False}
    rows=wire['runtimeContract']['finalWireReceipts']
    assert audit_compiler_receipts(rows,authored_document=doc,final_document=wire)['ok']
    assert any(r.get('finalPath','').endswith('.action.fishing.castSpeedPxPerTick') and r['value']==16 for r in rows)
    bare=deepcopy(wire);bare.pop('runtimeContract')
    assert validate_runtime_wire(bare)['ok']
    assert doc==before
    explicit=deepcopy(doc)
    explicit['runtimeProgram']['bindings'][0].update(stackCost=0,contactDamage=False)
    explicit['runtimeProgram']['bindings'][0]['action']['targetId']='item'
    assert compile_runtime_program(explicit)['runtimeProgram']==wire['runtimeProgram']


@pytest.mark.parametrize('value', [None,{}, {'power':30},{'castSpeed':60}, {'power':0,'castSpeed':60},
    {'power':1001,'castSpeed':60}, {'power':True,'castSpeed':60}, {'power':30,'castSpeed':0},
    {'power':30,'castSpeed':241}, {'power':30,'castSpeed':1e-320}, {'power':30,'castSpeed':float('inf')},
    {'power':30,'castSpeed':60,'bobber':360}])
def test_invalid_or_missing_authored_fishing_is_not_completed(value):
    doc=source();doc['runtimeProgram']['bindings'][0]['action']['fishing']=value
    assert not validate_runtime_program(doc)['ok']
    with pytest.raises(ValueError):compile_runtime_program(doc)


@pytest.mark.parametrize('field,value', [('power',0),('power',1001),('power',True),('castSpeedPxPerTick',0),
    ('castSpeedPxPerTick',65),('castSpeedPxPerTick',1e-320),('castSpeedPxPerTick',float('nan'))])
def test_bare_wire_keeps_runtime_bounds(field,value):
    wire=compile_runtime_program(source());wire.pop('runtimeContract')
    wire['runtimeProgram']['bindings'][0]['usePolicy']['action']['fishing'][field]=value
    assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('mutation', ['missing','contact','stack','other-action','ammo-stack'])
def test_fishing_transaction_cannot_be_repurposed(mutation):
    doc=source();binding=doc['runtimeProgram']['bindings'][0]
    if mutation=='missing':binding['action'].pop('fishing')
    elif mutation=='contact':binding['contactDamage']=True
    elif mutation=='stack':binding['stackCost']=1
    elif mutation=='other-action':binding['action']['kind']='use_item_body'
    else:
        ammo=build_capability_witness('ammo_item')
        doc['runtimeProgram']['calls'] += [{**c,'id':'ammo_role'} for c in ammo['runtimeProgram']['calls'] if c['fn']=='ammo_item']
    report=validate_runtime_program(doc)
    assert not report['ok']
    if mutation=='ammo-stack':assert [e['code'] for e in report['errors']]==['binding_action_mismatch']


def test_strict_provider_binding_roundtrip_preserves_required_payload():
    local=binding_schema(); authored=source()['runtimeProgram']['bindings'][0]
    provider=provider_schema._provider_strict_projection(local)
    encoded=_encode_nullable_fixture(authored,local)
    assert Draft202012Validator(provider).is_valid(encoded)
    decoded=provider_schema.project_provider_nullable_optionals_to_local(encoded,local,
        response_format={'type':'json_schema','json_schema':{'schema':provider}})
    assert decoded==authored
    assert Draft202012Validator(local).is_valid(decoded)


@pytest.mark.parametrize('fish_input',['primary_use','alternate_use'])
def test_weapon_ammo_and_fishing_remain_distinct(fish_input):
    doc=build_capability_witness('weapon_ammo')
    for binding in doc['runtimeProgram']['bindings']:
        if binding['input']==fish_input:binding['input']='alternate_use' if fish_input=='primary_use' else 'primary_use'
    doc['runtimeProgram']['bindings'].append(source(fish_input)['runtimeProgram']['bindings'][0])
    assert validate_runtime_program(doc)['ok']
    wire=compile_runtime_program(doc)
    assert validate_runtime_wire(wire)['ok']
    assert wire['runtimeProgram']['weaponAmmo']
    fish=next(b for b in wire['runtimeProgram']['bindings'] if b['id']=='fish')
    assert fish['usePolicy']['action']['kind']=='native_fishing'


@pytest.mark.parametrize('mode',['json_object','json_schema'])
def test_fishing_leaf_repair_preserves_power_input_and_other_valid_fields(monkeypatch,mode):
    from repair_test_helpers import gameplay_repair, assert_repaired_source
    doc=source();doc['runtimeProgram']['bindings'][0]['action']['fishing']['castSpeed']=0
    candidate=deepcopy(doc['runtimeProgram']['bindings'][0])
    candidate['action']['fishing']={'power':999,'castSpeed':45}
    candidate['action']['targetId']='unrelated'
    expected=deepcopy(doc);expected['runtimeProgram']['bindings'][0]['action']['fishing']['castSpeed']=45
    repaired,dossier=gameplay_repair(monkeypatch,doc,{'bindingsUpsert':[candidate],'note':'repair invalid speed'},mode)
    assert_repaired_source(repaired,expected)
    assert dossier['repairScope']['fieldPermissions']['bindings']==[{'id':'fish','paths':['action.fishing.castSpeed']}]


def test_repair_candidates_preserve_authored_fishing_values_without_inventing_new_ones():
    from infini_local.core.runtime_authoring.repair.choices import _binding_repair_alternatives, _complete_binding_transactions
    doc=source();rows=doc['runtimeProgram'];row=deepcopy(rows['bindings'][0])
    row['action']['targetId']='item'
    choices=_binding_repair_alternatives(rows,row,input_mutable=True,action_mutable=False,target_mutable=False)
    assert {c['input'] for c in choices}=={'primary_use','alternate_use'}
    assert all(c['action']['fishing']=={'power':30,'castSpeed':60} for c in choices)
    assert _complete_binding_transactions(rows,input_name='primary_use',action_name='native_fishing',target_id='item')==[]


def test_bare_wire_rejects_fishing_payload_on_other_action_and_missing_payload():
    for mutation in ('other','missing','extra','stack','contact','ammo'):
        wire=compile_runtime_program(source());wire.pop('runtimeContract')
        policy=wire['runtimeProgram']['bindings'][0]['usePolicy'];action=policy['action']
        if mutation=='other':action['kind']='use_item_body'
        elif mutation=='missing':action.pop('fishing')
        elif mutation=='extra':action['fishing']['hiddenDefault']=1
        elif mutation=='stack':policy['stackCost']=1
        elif mutation=='contact':policy['contactDamage']=True
        else:wire['gameplay'].update(ammoCategory='arrow',ammoProjectileId=1,ammoShootSpeedPxPerTick=1,notAmmo=False)
        assert not validate_runtime_wire(wire)['ok'],mutation


def test_ammo_stack_conflict_has_explicit_repair_scope_without_editing_ammo():
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    doc=source();ammo=build_capability_witness('ammo_item')
    doc['runtimeProgram']['calls'] += [{**c,'id':'ammo_role'} for c in ammo['runtimeProgram']['calls'] if c['fn']=='ammo_item']
    report=validate_runtime_program(doc)
    scope=build_runtime_repair_scope(doc,report['errors'])
    assert all(r['llmRepairable'] for r in scope['repairRequirements'])
    candidate={'id':'fish','input':'primary_use','action':{'kind':'use_item_body'},'stackCost':0,'contactDamage':False}
    patch,audit=filter_repair_patch_scope(doc,{'note':'select a compatible action','bindingsUpsert':[candidate]},scope)
    repaired=apply_repair_patch(doc,patch)
    assert validate_runtime_program(repaired)['ok'],(scope,audit,repaired)
    assert repaired['runtimeProgram']['calls']==doc['runtimeProgram']['calls']


def test_non_use_fishing_is_rejected_without_rewriting_input():
    for input_name in ('hold','equipped'):
        doc=source(input_name);before=deepcopy(doc)
        assert not validate_runtime_program(doc)['ok']
        with pytest.raises(ValueError):compile_runtime_program(doc)
        assert doc==before
        wire=compile_runtime_program(source());wire.pop('runtimeContract')
        wire['runtimeProgram']['bindings'][0]['input']=input_name
        assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('mode',['json_object','json_schema'])
def test_actual_author_packet_exposes_required_fishing_payload_for_object_mode(monkeypatch,mode):
    import json
    from infini_local.pipelines.author.request import build_initial_author_request
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE',mode)
    request,payload,_=build_initial_author_request({'name':'Wood'},{'name':'Bait'},'fishing-test',model_name='audit-model')
    assert request['response_format']['type']==mode
    cards=json.loads(payload)['runtimeCapabilityContract']['catalog']['bindingActions']
    fish=next(c for c in cards if c['action']=='native_fishing')
    assert fish['inputs']==['primary_use','alternate_use']
    shape=fish['requiredPayload']['fishing']
    variants=[v for v in binding_schema()['oneOf'] if v['properties']['action']['properties']['kind'].get('const')=='native_fishing']
    assert {v['properties']['input']['const'] for v in variants}=={'primary_use','alternate_use'}
    assert all(shape==v['properties']['action']['properties']['fishing'] for v in variants)
    assert set(shape['required'])=={'power','castSpeed'}
    assert Draft202012Validator(shape).is_valid({'power':30,'castSpeed':60})
    assert not Draft202012Validator(shape).is_valid({'power':30})
