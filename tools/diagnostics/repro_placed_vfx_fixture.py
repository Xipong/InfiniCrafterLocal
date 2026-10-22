"""Reproduce the checked-in final-wire CPU fixture; never calls inference/images/network.

Run with the workspace Python, PYTHONPATH=LocalGenerator, INFINI_SKIP_CONFIG_FILE=1.
Only --write updates the repo fixture. Temporary deterministic QA pixels are not art.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'LocalGenerator' / 'tests'))
from test_placed_vfx_capability import authored, light_slot
from test_low_level_three_stage_pipeline import _visual_kit
from vfx_material_fixtures import _with_asset
from test_vfx_material_admission_contracts import _library_particle
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines.visual_generation_pipeline import _apply_kit
from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png, synthetic_no_image_execution_control
from infini_local.storage.world_storage import sanitize_recipe_for_delivery, is_deliverable_recipe_payload


def build_fixture():
    source=authored()
    next(c for c in source['runtimeProgram']['calls'] if c['id']=='install_tile')['params']['tileId']=1
    data=compile_runtime_program(source)
    data.update(id='placed_vfx_cpu_fixture',schemaVersion=5,runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,sourceMode='offline_contract_fixture')
    data=_apply_kit(data,_visual_kit(data))
    raw=_with_asset(data)
    slot=raw['slots'][0]
    slot.update(id='left_flame',entityId='item',event='periodic',placementBindingId='alternate_install',startTick=0,repeatEvery=2)
    slot['element'].update(attachment='source',offsetForwardPx=-8,offsetSidePx=-12,speedMinPxPerTick=0,speedMaxPxPerTick=0)
    right=copy.deepcopy(slot);right['id']='right_flame';right['element']['offsetForwardPx']=8
    library=_library_particle(data)['slots'][0]
    library.update(entityId='item',event='periodic',placementBindingId='alternate_install',startTick=0,repeatEvery=3)
    raw['slots'].extend([right,library,light_slot()])
    data=vfx.attach_vfx_manifest(data,'placed-vfx-cpu-fixture',llm_director=lambda *_a,**_kw:raw)
    with tempfile.TemporaryDirectory(prefix='placed-vfx-') as directory:
        from infini_local.pipelines import visual_delivery_gate as gate
        prior_sprite_dir=gate.SPRITE_DIR;gate.SPRITE_DIR=Path(directory)
        try:
            fixture=write_no_image_fixture_png(Path(directory)/'synthetic.png')
            hydrate_no_image_fixture_assets(data,fixture)
            data=synthetic_no_image_execution_control(data,fixture)
            assert data['visual']['spriteStatus']=='generated', data.get('debug',{}).get('noImageExecutionControl')
            assert all(a['spriteStatus']=='generated' for a in data['vfxManifest']['assets'])
            assert is_deliverable_recipe_payload(data,check_assets=False)
            delivered=sanitize_recipe_for_delivery(data)
            evidence=data['debug']['noImageExecutionControl']
            delivered['debug']={'placedVfxCpuFixture':{'kind':evidence['kind'],'synthetic':True,'realImageGeneration':False,
                'fixtureSha256':evidence['fixture']['sha256']}}
        finally: gate.SPRITE_DIR=prior_sprite_dir
    # Native network/storage DTO uses portable filenames. No runtime dependency
    # on scratch/artifact paths or actual fixture art is claimed by this CPU probe.
    def portable(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key.endswith(('Path','Url')) and isinstance(value,str) and value:
                    node[key]=Path(value).name if not key.endswith('Url') else ''
                else: portable(value)
        elif isinstance(node,list):
            for value in node: portable(value)
    portable(delivered)
    assert validate_runtime_wire(delivered)['ok'],validate_runtime_wire(delivered)
    assert vfx.validate_vfx_manifest_wire(delivered)['ok']
    return delivered


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    data=build_fixture();target=ROOT/'LocalGenerator/tests/fixtures/placed_vfx_final_wire.json'
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if args.write: target.write_text(encoded,encoding='utf-8')
    else:
        assert json.loads(target.read_text(encoding='utf-8'))==data,'fixture drift: rerun --write deliberately'
    print('Author -> compiler/receipts -> Visual -> VFX Director -> final delivery -> strict wire: PASS')
    print(target)
