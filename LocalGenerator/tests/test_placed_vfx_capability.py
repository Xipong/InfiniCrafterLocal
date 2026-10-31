"""Opt-in placed sources, real Author/compiler/Director/wire boundaries; offline."""
import copy
import json

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA
from infini_local.core.vfx.projection import _compile_manifest
from infini_local.core.vfx.surface import vfx_director_surface
from infini_local.core.vfx.validation import validate_vfx_director_output, validate_vfx_manifest_wire
from infini_local.pipelines.vfx.prompt import _prompt_packet
from test_dual_use_placeable_contract import _dual_use_placeable
from test_low_level_three_stage_pipeline import wire_transport
from test_placed_body_capability import placement


def authored():
    d = _dual_use_placeable()
    d['runtimeProgram']['calls'].append({'id':'placed_effects','fn':'placed_vfx',
        'params':{'placementCallId':'install_tile','minFrameY':0,'maxFrameY':35}})
    return d


def light_slot():
    return {'id':'placed_glow','entityId':'item','placementBindingId':'alternate_install',
        'event':'periodic','rendererKind':'nativeLight','anchor':'self','repeatEvery':1,
        'startTick':0,'light':{'intensity':.2},'color':{'r':255,'g':90,'b':20}}


def test_author_to_receipts_and_final_wire():
    d = authored()
    report = validate_runtime_program(d)
    assert report['ok'], report
    wire = compile_runtime_program(d)
    assert placement(wire)['placedVfx'] == {'minFrameY':0,'maxFrameY':35}
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'], authored_document=d, final_document=wire)['ok']
    assert 'placedVfx' not in placement(compile_runtime_program(_dual_use_placeable()))


def test_director_selector_reaches_final_manifest_and_read_only_surface():
    wire = compile_runtime_program(authored())
    raw = {'schema':VFX_DIRECTOR_SCHEMA, 'slots':[light_slot()]}
    report = validate_vfx_director_output(raw, wire)
    assert report['ok'], report
    wire['vfxManifest'] = _compile_manifest(wire, report['normalized'], 'placed_vfx_cpu_fixture')
    assert wire['vfxManifest']['slots'][0]['placementBindingId'] == 'alternate_install'
    assert validate_vfx_manifest_wire(wire)['ok'], validate_vfx_manifest_wire(wire)
    surface = vfx_director_surface(wire)
    assert surface['placementBindings'] == [{'id':'alternate_install','entityId':'item',
        'minFrameY':0,'maxFrameY':35}]
    assert _prompt_packet(wire, {}, {})['runtimeSurface']['placementBindings'] == surface['placementBindings']


@pytest.mark.parametrize('gate',[None,{}, {'minFrameY':36,'maxFrameY':35},
    {'minFrameY':True,'maxFrameY':35}, {'minFrameY':0,'maxFrameY':32768}])
def test_present_gate_strict_in_author_and_source_free_wire(gate):
    d=authored();d['runtimeProgram']['calls'][-1]['params']=({'placementCallId':'install_tile', **gate} if isinstance(gate,dict) else gate)
    assert not validate_runtime_program(d)['ok']
    wire=compile_runtime_program(authored());wire.pop('runtimeContract')
    placement(wire)['placedVfx']=gate
    assert not validate_runtime_wire(wire)['ok']


@pytest.mark.parametrize('change',[{'placementBindingId':None},{'placementBindingId':'primary_workbench'},
    {'entityId':'workbench_blade'},{'event':'on_use'},{'anchor':'owner'}, {'repeatEvery':0},
    {'rendererKind':'soundCue'}])
def test_selector_rejects_foreign_or_unconsumed_branches(change):
    wire=compile_runtime_program(authored());slot=light_slot();slot.update(change)
    raw={'schema':VFX_DIRECTOR_SCHEMA,'slots':[slot]}
    assert not validate_vfx_director_output(raw,wire)['ok']
    wire['vfxManifest']=_compile_manifest(wire,raw,'placed_negative')
    assert not validate_vfx_manifest_wire(wire)['ok']


def test_absent_component_has_no_selectable_binding_and_old_manifest_bytes_unchanged():
    from vfx_material_fixtures import _legacy
    wire=compile_runtime_program(_dual_use_placeable());raw=_legacy(wire)
    old=_compile_manifest(wire,raw,'old')
    assert 'placementBindingId' not in json.dumps(old)
    selected={'schema':VFX_DIRECTOR_SCHEMA,'slots':[light_slot()]}
    assert not validate_vfx_director_output(selected,wire)['ok']
    assert not validate_vfx_director_output(raw,wire)['ok']
    wire['vfxManifest']=old
    before=copy.deepcopy(wire)
    assert validate_vfx_manifest_wire(wire)['ok']
    assert wire==before


def test_authored_reference_and_receipts_are_exact_and_repair_leaf_frozen():
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    d=authored();d['runtimeProgram']['calls'][-1]['params']['placementCallId']='wrong'
    scope=build_runtime_repair_scope(d,validate_runtime_program(d)['errors'])
    assert scope['nonRepairableErrors']==[]
    incoming=copy.deepcopy(d['runtimeProgram']['calls'][-1]);incoming['params'].update(placementCallId='install_tile',minFrameY=7,maxFrameY=8)
    filtered,audit=filter_repair_patch_scope(d,{'note':'reference only','callsUpsert':[incoming]},scope)
    repaired=apply_repair_patch(d,filtered)
    assert repaired['runtimeProgram']['calls'][-1]['params']=={'placementCallId':'install_tile','minFrameY':0,'maxFrameY':35}
    wire=compile_runtime_program(repaired)
    wire['runtimeContract']['finalWireReceipts'][:]=[r for r in wire['runtimeContract']['finalWireReceipts'] if r.get('fn')!='placed_vfx']
    assert not validate_runtime_wire(wire)['ok']


def test_real_director_and_repair_packets_freeze_sibling_selector_absence():
    import infini_local.core.vfx.contract as vfx_contract
    import infini_local.core.vfx.repair as vfx_repair
    import infini_local.core.vfx.validation as vfx_validation
    import infini_local.pipelines.vfx.prompt as vfx_prompt
    import infini_local.pipelines.vfx.stage as vfx_stage
    from vfx_material_fixtures import _sent
    wire=compile_runtime_program(authored());raw={'schema':VFX_DIRECTOR_SCHEMA,'slots':[light_slot()]}
    sibling=light_slot();sibling.pop('placementBindingId');sibling['id']='held_glow'
    raw['slots'].append(sibling)
    raw['slots'][0]['placementBindingId']='wrong'
    errors=vfx_validation.validate_vfx_director_output(raw,wire)['errors']
    scope=vfx_repair._build_vfx_repair_scope(raw,errors)
    assert scope['fieldPermissions']['slots']==[{'slotId':'placed_glow','paths':['placementBindingId']}]
    packet=vfx_prompt._prompt_packet(wire,{},{});sent=_sent(wire,False,packet)
    assert sent['runtimeSurface']['placementBindings'][0]['maxFrameY']==35
    captures=[]
    def capture(system,user,*args,**kwargs):
        captures.append(json.loads(kwargs['messages'][1]['content']));return {}
    vfx_stage._request(capture,packet,repair_errors=errors,previous=raw,repair_scope=scope)
    assert captures[0]['runtimeSurfaceReadOnly']['placementBindings']==sent['runtimeSurface']['placementBindings']
    attack=copy.deepcopy(raw['slots'][0]);attack.update(placementBindingId='alternate_install');attack['light']['intensity']=1
    sibling_attack=copy.deepcopy(sibling);sibling_attack['placementBindingId']='alternate_install'
    fixed=vfx_repair._apply_vfx_repair_patch(wire,raw,{'schema':vfx_contract.VFX_REPAIR_PATCH_SCHEMA,'note':'exact selector','slotsUpsert':[attack,sibling_attack]},scope)
    expected=copy.deepcopy(raw);expected['slots'][0]['placementBindingId']='alternate_install'
    assert fixed==expected
    assert vfx_validation.validate_vfx_director_output(fixed,wire)['ok']


def test_new_registry_witness_and_native_bounds_surface():
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.qa.primitive_loss_audit import _placed_component_surface_audit
    d=build_capability_witness('placed_vfx')
    assert validate_runtime_program(d)['ok'],validate_runtime_program(d)
    assert validate_runtime_wire(compile_runtime_program(d))['ok']
    assert _placed_component_surface_audit('placed_vfx','RuntimePlacedVfxSpec',None)['ok']
    from infini_local.qa.primitive_loss_audit import structural_surface_audit
    assert structural_surface_audit().get('placedVfxStorage',{}).get('ok')




def test_actual_author_and_visual_repairs_preserve_independent_placed_components(wire_transport):
    import infini_local.pipelines.visual.contract as visual_contract
    import infini_local.pipelines.visual.request as visual_request
    from infini_local.pipelines.author import request as author
    from prompt_packet_helpers import request_dossier
    from test_low_level_three_stage_pipeline import _visual_kit
    responses,requests=wire_transport
    d=authored();responses.append(d)
    assert author.try_llm_plan({'name':'A'},{'name':'B'},'placed-offline') is not None
    wire=compile_runtime_program(d);kit=_visual_kit(wire)
    for repair in (False,True):
        responses.append(kit if not repair else {'schema':visual_contract.VISUAL_REPAIR_PATCH_SCHEMA,'note':'no-op'})
        visual_request._request_visual_kit(wire,{}, {}, **({'repair_errors':[],'previous':kit,'repair_scope':{}} if repair else {}))
        packet=request_dossier(requests[-1])
        assert packet['acceptedPresentationMechanicsReadOnly']['bindings']==wire['runtimeProgram']['bindings']
    broken=copy.deepcopy(d);broken['runtimeProgram']['calls'][-1]['params']['placementCallId']='wrong'
    patch=copy.deepcopy(broken['runtimeProgram']['calls'][-1]);patch['params'].update(placementCallId='install_tile',minFrameY=9,maxFrameY=10)
    responses.append({'note':'exact dependency','realizationReplacement':broken['realization'],'callsUpsert':[patch]})
    repaired=author.repair_author_item_after_failure(broken,{}, {},'placed-repair-offline',failure_report=validate_runtime_program(broken))
    packet=request_dossier(requests[-1])
    assert next(p for p in packet['repairScope']['fieldPermissions']['calls'] if p['id']=='placed_effects')['paths']==['params.placementCallId']
    assert placement(compile_runtime_program(repaired))['placedVfx']=={'minFrameY':0,'maxFrameY':35}


def test_independent_body_light_and_vfx_components_compose_without_new_defaults():
    from test_placed_body_capability import placed
    from test_placed_light_capability import lit
    d=placed();d['runtimeProgram']['calls'].extend([lit()['runtimeProgram']['calls'][-1],authored()['runtimeProgram']['calls'][-1]])
    wire=compile_runtime_program(d)
    assert set(placement(wire))=={'tileId','wallId','placeStyle','placedBody','placedLight','placedVfx'}
    assert validate_runtime_wire(wire)['ok']


def test_exported_vfx_schema_has_real_opt_in_sample_not_empty_selector_domain():
    import importlib.util
    from pathlib import Path

    from infini_local.core.schema_validation import strict_schema_errors
    path=Path(__file__).resolve().parents[2]/'tools/generate/export_contract_schemas.py'
    spec=importlib.util.spec_from_file_location('placed_schema_export',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    schema=next(json.loads(text) for path,text in module.render().items() if path.name=='vfx_runtime_events.schema.json')
    assert schema['properties']['slots']['items']['properties']['placementBindingId']['enum']==['alternate_install']
    assert strict_schema_errors({'schema':VFX_DIRECTOR_SCHEMA,'slots':[light_slot()]},schema)==[]
